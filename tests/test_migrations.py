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
}


def _old_db(tmp_path):
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
