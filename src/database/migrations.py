"""경량 스키마/데이터 마이그레이션.

SQLAlchemy의 `create_all`은 없는 테이블만 만들고 기존 테이블에 추가된
컬럼은 반영하지 않는다. 기존 사용자의 발명 데이터를 지우지 않고 컬럼만
덧붙이기 위해, SQLite의 `ALTER TABLE ... ADD COLUMN`으로 누락된 컬럼을
채워 넣는다. 이 파일은 두 가지 일을 한다:

1. 스키마 마이그레이션 — 컬럼 추가만 수행한다. 삭제·타입 변경은 하지
   않는다(데이터 손실 방지). 이미 있는 컬럼은 건너뛰므로 여러 번 실행해도
   안전하다.
2. 데이터 마이그레이션 — 예전 상태값을 새 상태값으로 옮기고, 예전
   keywords(JSON 문자열 배열) 컬럼의 내용을 새 Tag/InventionTag 테이블로
   옮겨 담는다. 둘 다 여러 번 실행해도 같은 결과가 나오도록(멱등하게) 짰다.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# 테이블별로 나중에 추가된 컬럼과 SQLite 타입 정의
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "inventions": {
        "refined_content": "TEXT",
        "key_components": "TEXT",
        "operating_principle": "TEXT",
        "differentiation": "TEXT",
        "implementation_method": "TEXT",
        "experiment_notes": "TEXT",
        "review_notes": "TEXT",
        "is_favorite": "BOOLEAN DEFAULT 0",
        "parent_invention_id": "VARCHAR(36)",
        "owner_id": "VARCHAR(100)",
        "derivation_reason": "VARCHAR(200)",
        "source_experiment_id": "VARCHAR(36)",
    },
    "attachments": {
        "experiment_id": "VARCHAR(36)",
        "category": "VARCHAR(30) DEFAULT '기타'",
    },
    "invention_ai_results": {
        "model": "VARCHAR(100)",
        "input_snapshot": "TEXT",
        "applied_fields": "JSON",
        "status": "VARCHAR(20) DEFAULT '생성됨'",
        "structured_content": "JSON",
        "parse_error": "TEXT",
    },
}


def run_migrations(engine: Engine) -> list[str]:
    """누락된 컬럼/테이블을 추가하고, 예전 데이터를 새 구조로 옮긴다.

    반환값은 실제로 추가한 컬럼 이름 목록이다 (데이터 마이그레이션은
    포함하지 않는다 — 그건 로그로만 남긴다).
    """
    if _needs_column_migration(engine):
        _backup_db_file(engine)
    applied = _add_missing_columns(engine)
    _remap_legacy_status_values(engine)
    _backfill_tags_from_keywords(engine)
    _backfill_ai_result_status(engine)
    _ensure_search_index(engine)
    return applied


def _needs_column_migration(engine: Engine) -> bool:
    """실제로 ALTER TABLE이 필요한지 미리 확인한다 (백업 여부 판단용)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table, columns in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue
        present = {col["name"] for col in inspector.get_columns(table)}
        if set(columns) - present:
            return True
    return False


def _backup_db_file(engine: Engine) -> Path | None:
    """스키마를 바꾸기 전에 SQLite 파일을 통째로 복사해 둔다.

    새 DB(파일이 아직 없거나 비어 있음)나 in-memory DB에서는 아무 일도
    하지 않는다 — 백업할 기존 데이터가 없기 때문이다. 백업 자체가
    실패해도(디스크 꽉 참 등) 마이그레이션을 막지는 않는다 — 로그만 남긴다.
    """
    try:
        url = engine.url
        if url.get_backend_name() != "sqlite" or not url.database:
            return None
        db_path = Path(url.database)
        if db_path.name == ":memory:" or not db_path.exists() or db_path.stat().st_size == 0:
            return None

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = db_path.with_name(f"{db_path.stem}_backup_{timestamp}{db_path.suffix}")
        shutil.copy2(db_path, backup_path)
        logger.info("스키마 변경 전 DB를 백업했습니다: %s", backup_path)
        return backup_path
    except OSError as exc:
        logger.warning("Migration 전 DB 백업에 실패했습니다 (계속 진행합니다): %s", exc)
        return None


def _add_missing_columns(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    applied: list[str] = []
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                # create_all이 최신 스키마로 새로 만들었으므로 손댈 것이 없다.
                continue

            present = {col["name"] for col in inspector.get_columns(table)}
            for column_name, column_type in columns.items():
                if column_name in present:
                    continue
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")
                )
                applied.append(f"{table}.{column_name}")
                logger.info("마이그레이션: %s.%s 컬럼을 추가했습니다.", table, column_name)

    return applied


# 예전 상태값 → 새 6종 상태값(Idea/Reviewing/Experiment/Patent/Development/Archived)
_STATUS_REMAP = {
    "선행기술 조사 중": "검토 중",
    "차별화 검토 중": "검토 중",
    "시험 검토 중": "실험 중",
    "보류": "검토 중",
    "출원 검토": "특허 검토",
    "완료": "개발 중",
}


def _remap_legacy_status_values(engine: Engine) -> None:
    inspector = inspect(engine)
    if "inventions" not in set(inspector.get_table_names()):
        return

    with engine.begin() as conn:
        for old_value, new_value in _STATUS_REMAP.items():
            conn.execute(
                text("UPDATE inventions SET status = :new WHERE status = :old"),
                {"new": new_value, "old": old_value},
            )


def _backfill_tags_from_keywords(engine: Engine) -> None:
    """예전 `inventions.keywords` JSON 배열을 Tag/InventionTag 테이블로 옮긴다.

    이미 옮겨진 조합은 건너뛰므로 여러 번 실행해도 중복 태그가 생기지 않는다.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not {"inventions", "tags", "invention_tags"}.issubset(tables):
        return

    # 순환 import를 피하려고 함수 안에서 지연 import한다.
    from src.database.models import Invention
    from src.tags.service import TagService

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session: Session = session_factory()
    try:
        stmt = select(Invention)
        for invention in session.scalars(stmt):
            raw_keywords = invention.keywords
            if isinstance(raw_keywords, str):
                try:
                    raw_keywords = json.loads(raw_keywords)
                except ValueError:
                    raw_keywords = []
            if not raw_keywords:
                continue
            TagService(session).add_tags(invention.id, raw_keywords)
        session.commit()
    finally:
        session.close()


def _backfill_ai_result_status(engine: Engine) -> None:
    """예전 InventionAIResult 행에 status/applied_fields를 채워 넣는다.

    이 컬럼들이 생기기 전에 만들어진 행은 status가 NULL이거나(구버전 ALTER
    직후) applied_fields가 비어 있을 수 있다. 여러 번 실행해도 안전하도록
    이미 채워진 행은 건드리지 않는다.
    """
    inspector = inspect(engine)
    if "invention_ai_results" not in set(inspector.get_table_names()):
        return

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session: Session = session_factory()
    try:
        from src.database.models import InventionAIResult

        changed = False
        for result in session.scalars(select(InventionAIResult)):
            if not result.status:
                result.status = "반영됨" if result.applied_at else "생성됨"
                changed = True
            if not result.applied_fields and result.applied_to_field:
                result.applied_fields = [result.applied_to_field]
                changed = True
        if changed:
            session.commit()
    finally:
        session.close()


def _ensure_search_index(engine: Engine) -> None:
    """FTS5 검색 색인 테이블을 만들고, 비어 있으면 기존 발명들로 채운다."""
    from src.search.fts import FTS_TABLE, SearchIndexService, ensure_index_table

    ensure_index_table(engine)

    inspector = inspect(engine)
    if "inventions" not in set(inspector.get_table_names()):
        return

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session: Session = session_factory()
    try:
        indexed_count = session.execute(
            text(f"SELECT COUNT(*) FROM {FTS_TABLE}")
        ).scalar()
        invention_count = session.execute(
            text("SELECT COUNT(*) FROM inventions")
        ).scalar()
        if indexed_count == 0 and invention_count > 0:
            SearchIndexService(session).rebuild_all()
            session.commit()
            logger.info("검색 색인을 처음부터 다시 만들었습니다 (%d건).", invention_count)
    finally:
        session.close()
