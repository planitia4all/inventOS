"""SQLite FTS5 기반 통합 검색.

제목만이 아니라 발명번호, 원본 메모, 발명 내용(정리된 내용/핵심 원리 등),
태그, 첨부파일 이름, 실험 기록, AI 검토 결과까지 한 번에 검색한다.

색인은 완벽한 실시간 트리거 대신, 의미 있는 변경이 있을 때마다
`reindex_invention()`을 명시적으로 호출하는 방식으로 유지한다 — 발명
내용이 여러 테이블(태그, 첨부파일, 실험, AI 결과 등)에 걸쳐 있어서 SQL
트리거만으로는 깔끔하게 표현하기 어렵고, 로컬 단일 사용자 프로그램
규모에서는 이 편이 더 단순하고 디버깅하기 쉽다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class SearchIndexReport:
    """검색 색인 점검 결과 (설정 화면 '검색 색인 검사 및 다시 만들기')."""

    total_inventions: int = 0
    indexed_count: int = 0
    missing_ids: list[str] = field(default_factory=list)  # 발명은 있는데 색인이 없음
    orphaned_ids: list[str] = field(default_factory=list)  # 색인은 있는데 발명이 없음(고아)
    stale_ids: list[str] = field(default_factory=list)  # 색인된 제목이 현재와 다름(오래됨)

    @property
    def is_healthy(self) -> bool:
        return not (self.missing_ids or self.orphaned_ids or self.stale_ids)


FTS_TABLE = "invention_search_index"

# FTS5 가상 테이블은 ALTER TABLE로 컬럼을 추가할 수 없다. 이 목록이 실제
# 테이블 컬럼과 다르면(예: 예전 버전 DB) 테이블을 통째로 다시 만들고
# 색인을 재구축한다 — `ensure_index_table()`/`_ensure_search_index()` 참고.
_FTS_COLUMNS = [
    "invention_id",
    "invention_no",
    "title",
    "original_idea",
    "content_text",
    "tags",
    "attachment_names",
    "experiment_text",
    "ai_results_text",
]

# Invention의 텍스트 본문 필드 (제목/원본과는 별도로 색인한다)
CONTENT_FIELDS = (
    "technical_field",
    "refined_content",
    "problem_to_solve",
    "conventional_method",
    "conventional_problems",
    "core_principle",
    "key_components",
    "operating_principle",
    "differentiation",
    "expected_effects",
    "technical_barriers",
    "applicable_industries",
    "implementation_method",
    "experiment_notes",
    "review_notes",
)

# 실험 기록(Experiment)에서 색인할 필드
_EXPERIMENT_FIELDS = ("conditions", "results", "failure_reason", "improvement_ideas")


def _fts_columns(conn) -> set[str]:
    try:
        rows = conn.execute(text(f"PRAGMA table_info({FTS_TABLE})")).fetchall()
    except OperationalError:
        return set()
    return {row[1] for row in rows}


def ensure_index_table(engine: Engine) -> None:
    with engine.begin() as conn:
        existing_columns = _fts_columns(conn)
        if existing_columns and not set(_FTS_COLUMNS).issubset(existing_columns):
            # 예전 스키마(컬럼이 더 적음) — 통째로 다시 만든다. 실제 데이터는
            # migrations.py의 `_ensure_search_index()`가 rebuild_all()로 채운다.
            conn.execute(text(f"DROP TABLE IF EXISTS {FTS_TABLE}"))
            existing_columns = set()

        if not existing_columns:
            column_defs = [
                f"{col} UNINDEXED" if col == "invention_id" else col
                for col in _FTS_COLUMNS
            ]
            columns_sql = ",\n                    ".join(column_defs)
            conn.execute(
                text(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5(
                    {columns_sql}
                    )
                    """
                )
            )


def _sanitize_tokens(query: str) -> list[str]:
    """FTS5 MATCH 구문에 안전하게 넣을 수 있도록 토큰을 정리한다."""
    tokens = []
    for raw in (query or "").split():
        cleaned = "".join(ch for ch in raw if ch.isalnum())
        if cleaned:
            tokens.append(cleaned)
    return tokens


class SearchIndexService:
    def __init__(self, session: Session):
        self.session = session

    def reindex_invention(self, invention_id: str) -> bool:
        """이 발명의 색인을 최신 내용으로 다시 만든다.

        관계(`invention.attachments` 등)를 그대로 쓰지 않고 매번 직접
        조회한다 — 같은 세션 안에서 관계가 한 번이라도 지연 로딩되어
        캐시된 뒤에는, FK만 직접 설정하고 flush한 자식 레코드(예: 새
        첨부파일)가 추가돼도 이미 로딩된 컬렉션이 자동으로 갱신되지
        않기 때문이다 (SQLAlchemy의 일반적인 동작). 직접 쿼리하면 항상
        flush된 최신 상태를 본다.

        검색 색인은 발명/실험/첨부파일/AI 결과로부터 다시 만들 수 있는
        파생 데이터다 — 실제 쓰기(DELETE+INSERT)는 SAVEPOINT로 감싸서,
        색인 테이블이 손상되는 등 이 부분만 실패해도 호출한 쪽이 이미
        진행 중인 핵심 데이터 저장(발명 내용 수정 등)까지 함께 롤백되지
        않는다. 실패하면 로그만 남기고 `False`를 반환한다 — 설정 화면의
        "검색 색인 검사 및 다시 만들기"로 나중에 복구할 수 있다.
        """
        from src.database.models import (
            Attachment,
            Experiment,
            Invention,
            InventionAIResult,
            InventionTag,
            Tag,
        )

        invention = self.session.get(Invention, invention_id)
        if invention is None:
            return self.remove(invention_id)

        content_text = " ".join(
            filter(None, (getattr(invention, f) for f in CONTENT_FIELDS))
        )
        tag_names = " ".join(
            name
            for (name,) in self.session.query(Tag.name)
            .join(InventionTag, InventionTag.tag_id == Tag.id)
            .filter(InventionTag.invention_id == invention_id)
            .all()
        )
        attachment_names = " ".join(
            name
            for (name,) in self.session.query(Attachment.original_filename)
            .filter(Attachment.invention_id == invention_id)
            .all()
        )
        experiment_rows = (
            self.session.query(*(getattr(Experiment, f) for f in _EXPERIMENT_FIELDS))
            .filter(Experiment.invention_id == invention_id)
            .all()
        )
        experiment_text = " ".join(
            value for row in experiment_rows for value in row if value
        )
        # 삭제된(소프트 삭제) AI 결과는 검색에서 제외한다.
        ai_results_text = " ".join(
            content
            for (content,) in self.session.query(InventionAIResult.content)
            .filter(
                InventionAIResult.invention_id == invention_id,
                InventionAIResult.status != "삭제됨",
            )
            .all()
            if content
        )

        try:
            with self.session.begin_nested():
                self._delete_index_rows(invention_id)
                self.session.execute(
                    text(
                        f"""
                        INSERT INTO {FTS_TABLE}
                            (invention_id, invention_no, title, original_idea, content_text,
                             tags, attachment_names, experiment_text, ai_results_text)
                        VALUES (:invention_id, :invention_no, :title, :original_idea, :content_text,
                                :tags, :attachment_names, :experiment_text, :ai_results_text)
                        """
                    ),
                    {
                        "invention_id": invention.id,
                        "invention_no": invention.invention_no,
                        "title": invention.title,
                        "original_idea": invention.original_idea,
                        "content_text": content_text,
                        "tags": tag_names,
                        "attachment_names": attachment_names,
                        "experiment_text": experiment_text,
                        "ai_results_text": ai_results_text,
                    },
                )
        except SQLAlchemyError as exc:
            logger.warning(
                "검색 색인 갱신에 실패했습니다(핵심 저장에는 영향 없음, invention_id=%s): %s",
                invention_id,
                exc,
            )
            return False
        return True

    def remove(self, invention_id: str) -> bool:
        """SAVEPOINT로 감싸서, 색인 삭제 실패가 호출한 쪽의 핵심 트랜잭션을
        함께 롤백시키지 않도록 한다 (reindex_invention과 같은 이유)."""
        try:
            with self.session.begin_nested():
                self._delete_index_rows(invention_id)
        except SQLAlchemyError as exc:
            logger.warning(
                "검색 색인 삭제에 실패했습니다(핵심 저장에는 영향 없음, invention_id=%s): %s",
                invention_id,
                exc,
            )
            return False
        return True

    def _delete_index_rows(self, invention_id: str) -> None:
        self.session.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE invention_id = :invention_id"),
            {"invention_id": invention_id},
        )

    def rebuild_all(self) -> int:
        """모든 발명의 색인을 처음부터 다시 만든다. 마이그레이션/복구용."""
        from src.database.models import Invention

        self.session.execute(text(f"DELETE FROM {FTS_TABLE}"))
        count = 0
        for invention in self.session.query(Invention):
            self.reindex_invention(invention.id)
            count += 1
        return count

    def check_integrity(self) -> SearchIndexReport:
        """색인이 비어 있지 않아도(발명 100개 중 95개만 색인됨 등) 부분
        손상을 잡아낸다. 앱 시작 때마다 돌리기엔 무겁지만, 설정 화면에서
        사용자가 필요할 때 눌러 점검+복구할 수 있게 한다."""
        from src.database.models import Invention

        invention_rows = {
            inv_id: title for inv_id, title in self.session.query(Invention.id, Invention.title)
        }
        indexed_rows = {
            row[0]: row[1]
            for row in self.session.execute(
                text(f"SELECT invention_id, title FROM {FTS_TABLE}")
            )
        }

        invention_ids = set(invention_rows)
        indexed_ids = set(indexed_rows)

        missing = sorted(invention_ids - indexed_ids)
        orphaned = sorted(indexed_ids - invention_ids)
        stale = sorted(
            inv_id
            for inv_id in invention_ids & indexed_ids
            if invention_rows[inv_id] != indexed_rows[inv_id]
        )

        return SearchIndexReport(
            total_inventions=len(invention_ids),
            indexed_count=len(indexed_ids),
            missing_ids=missing,
            orphaned_ids=orphaned,
            stale_ids=stale,
        )

    def search(self, query: str, limit: int = 50) -> list[str]:
        """검색어와 일치하는 발명 id를 관련도 순으로 반환한다.

        FTS5 쿼리 자체가 예기치 않게 실패해도(예: 색인이 손상된 경우)
        예외를 밖으로 던지지 않는다 — 호출한 쪽(`InventionService.search`)이
        빈 결과를 받으면 LIKE 기반 검색으로 안전하게 대체한다.
        """
        tokens = _sanitize_tokens(query)
        if not tokens:
            return []

        match_expr = " ".join(f'{token}*' for token in tokens)
        try:
            rows = self.session.execute(
                text(
                    f"""
                    SELECT invention_id FROM {FTS_TABLE}
                    WHERE {FTS_TABLE} MATCH :match_expr
                    ORDER BY rank
                    LIMIT :limit
                    """
                ),
                {"match_expr": match_expr, "limit": limit},
            )
            return [row[0] for row in rows]
        except OperationalError as exc:
            logger.warning("FTS 검색에 실패해 기본 검색으로 대체합니다: %s", exc)
            return []
