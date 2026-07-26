"""기존 DB에 컬럼을 덧붙이는 마이그레이션 검증.

이미 아이디어를 기록해 둔 사용자의 DB를 열었을 때, 데이터가 남아 있는 채로
새 컬럼만 추가되어야 한다.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from src.database.migrations import run_migrations

# Sprint 1 시절의 옛 스키마 (새 컬럼이 없는 상태)
_OLD_SCHEMA = """
CREATE TABLE inventions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    invention_no VARCHAR(32) NOT NULL UNIQUE,
    title VARCHAR(500) NOT NULL,
    technical_field VARCHAR(200),
    original_idea TEXT NOT NULL,
    problem_to_solve TEXT,
    conventional_method TEXT,
    conventional_problems TEXT,
    core_principle TEXT,
    expected_effects TEXT,
    technical_barriers TEXT,
    applicable_industries TEXT,
    keywords JSON,
    inventor_name VARCHAR(200),
    status VARCHAR(50),
    is_archived BOOLEAN,
    created_at DATETIME,
    updated_at DATETIME,
    version INTEGER
)
"""

_NEW_COLUMNS = {
    "refined_content",
    "key_components",
    "operating_principle",
    "differentiation",
    "implementation_method",
    "experiment_notes",
    "review_notes",
    "is_favorite",
    "parent_invention_id",
    "owner_id",
}


def _old_db(tmp_path):
    """실제 앱 흐름을 흉내낸다: 옛 `inventions` 테이블이 이미 있는 상태에서
    `Base.metadata.create_all()`을 실행하면(=init_engine이 항상 먼저 하는 일),
    `inventions`는 그대로 두고 그 사이에 새로 생긴 테이블(tags, invention_tags,
    experiments 등)만 만들어진다. 그다음에 `run_migrations()`가 컬럼을 보충한다.
    """
    from src.database.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text(_OLD_SCHEMA))
        conn.execute(
            text(
                "INSERT INTO inventions "
                "(id, invention_no, title, original_idea, status, version) "
                "VALUES ('id-1', 'INV-2026-000001', '옛 발명', '옛 아이디어 본문', "
                "'아이디어', 1)"
            )
        )
    Base.metadata.create_all(engine)
    return engine


def test_migration_adds_missing_columns(tmp_path):
    engine = _old_db(tmp_path)

    applied = run_migrations(engine)

    columns = {c["name"] for c in inspect(engine).get_columns("inventions")}
    assert _NEW_COLUMNS.issubset(columns)
    assert len(applied) == len(_NEW_COLUMNS)


def test_migration_preserves_existing_rows(tmp_path):
    engine = _old_db(tmp_path)

    run_migrations(engine)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT title, original_idea, is_favorite FROM inventions WHERE id='id-1'")
        ).one()
    assert row.title == "옛 발명"
    assert row.original_idea == "옛 아이디어 본문"
    # 새 컬럼은 기본값으로 채워진다
    assert not row.is_favorite


def test_migration_is_idempotent(tmp_path):
    engine = _old_db(tmp_path)

    first = run_migrations(engine)
    second = run_migrations(engine)

    assert first
    assert second == []


def test_migration_noop_on_fresh_schema(tmp_path):
    """create_all이 최신 스키마로 만든 DB에서는 추가할 것이 없어야 한다."""
    from src.database.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)

    assert run_migrations(engine) == []


def test_migration_remaps_legacy_status_values(tmp_path):
    engine = _old_db(tmp_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO inventions "
                "(id, invention_no, title, original_idea, status, version) "
                "VALUES ('id-2', 'INV-2026-00002', '예전 상태값', '본문', "
                "'출원 검토', 1)"
            )
        )

    run_migrations(engine)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM inventions WHERE id='id-2'")
        ).one()
    assert row.status == "특허 검토"


def _fresh_engine_with_invention(tmp_path, db_name: str, invention_id: str, keywords: list[str]):
    from sqlalchemy.orm import sessionmaker

    from src.database.models import Base, Invention

    engine = create_engine(f"sqlite:///{tmp_path / db_name}")
    Base.metadata.create_all(engine)

    session = sessionmaker(bind=engine)()
    try:
        session.add(
            Invention(
                id=invention_id,
                invention_no=f"INV-2026-{invention_id}",
                title="태그 이전 테스트",
                original_idea="본문",
                status="아이디어",
                version=1,
                keywords=keywords,
            )
        )
        session.commit()
    finally:
        session.close()
    return engine


def test_migration_backfills_tags_from_keywords_json(tmp_path):
    engine = _fresh_engine_with_invention(
        tmp_path, "fresh.db", "id-3", ["Battery", "Robot"]
    )

    run_migrations(engine)

    with engine.connect() as conn:
        names = {
            row.name
            for row in conn.execute(
                text(
                    "SELECT t.name FROM tags t "
                    "JOIN invention_tags it ON it.tag_id = t.id "
                    "WHERE it.invention_id = 'id-3'"
                )
            )
        }
    assert names == {"Battery", "Robot"}


def test_migration_backfill_is_idempotent(tmp_path):
    engine = _fresh_engine_with_invention(tmp_path, "fresh.db", "id-4", ["AI"])

    run_migrations(engine)
    run_migrations(engine)

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM invention_tags WHERE invention_id='id-4'")
        ).scalar()
    assert count == 1
