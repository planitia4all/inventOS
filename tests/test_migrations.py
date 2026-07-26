"""기존 DB에 컬럼을 덧붙이는 마이그레이션 검증.

이미 아이디어를 기록해 둔 사용자의 DB를 열었을 때, 데이터가 남아 있는 채로
새 컬럼만 추가되어야 한다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from src.database.migrations import MigrationBackupError, run_migrations

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
    "derivation_reason",
    "source_experiment_id",
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


def test_migration_upgrades_old_fts_schema_and_rebuilds(tmp_path):
    """예전(컬럼이 더 적은) FTS5 색인 테이블이 있는 DB를 열면, 테이블을
    새 스키마로 다시 만들고 기존 발명들로 색인을 재구축해야 한다."""
    from src.database.models import Base, Invention

    engine = create_engine(f"sqlite:///{tmp_path / 'old_fts.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # search/fts.py가 예전에 썼던 5개 컬럼짜리 스키마를 흉내낸다.
        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE invention_search_index USING fts5(
                    invention_id UNINDEXED, title, original_idea,
                    content_text, tags, attachment_names
                )
                """
            )
        )

    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=engine)()
    try:
        session.add(
            Invention(
                id="id-5",
                invention_no="INV-2026-00005",
                title="예전 색인 테스트",
                original_idea="본문",
                status="아이디어",
                version=1,
            )
        )
        session.commit()
    finally:
        session.close()

    run_migrations(engine)

    columns = {
        row[1] for row in engine.connect().execute(text("PRAGMA table_info(invention_search_index)"))
    }
    assert {"invention_no", "experiment_text", "ai_results_text"}.issubset(columns)

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT invention_id FROM invention_search_index "
                "WHERE invention_search_index MATCH '예전'"
            )
        ).first()
    assert row is not None
    assert row[0] == "id-5"


def test_migration_backs_up_db_file_before_altering_schema(tmp_path):
    engine = _old_db(tmp_path)

    run_migrations(engine)

    backups = list(tmp_path.glob("old_backup_*.db"))
    assert len(backups) == 1
    # 백업본에는 마이그레이션 이전 원본 데이터가 그대로 들어 있어야 한다.
    from sqlalchemy import create_engine as _create_engine

    backup_engine = _create_engine(f"sqlite:///{backups[0]}")
    with backup_engine.connect() as conn:
        row = conn.execute(text("SELECT title FROM inventions WHERE id='id-1'")).one()
    assert row.title == "옛 발명"


def test_migration_does_not_backup_when_schema_already_current(tmp_path):
    from src.database.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)

    run_migrations(engine)

    assert list(tmp_path.glob("fresh_backup_*.db")) == []


def test_migration_backup_is_only_created_once_across_repeated_runs(tmp_path):
    engine = _old_db(tmp_path)

    run_migrations(engine)  # 스키마가 바뀌므로 백업 1개 생성
    run_migrations(engine)  # 이미 최신 스키마이므로 추가 백업 없음

    backups = list(tmp_path.glob("old_backup_*.db"))
    assert len(backups) == 1


def test_migration_aborts_when_backup_fails_on_existing_db(tmp_path, monkeypatch):
    """기존 데이터가 있는 DB인데 백업이 실패하면(디스크 꽉 참 등), 안전망 없이
    스키마를 바꾸지 않고 마이그레이션 자체를 중단해야 한다."""
    import shutil

    engine = _old_db(tmp_path)

    def failing_copy(*args, **kwargs):
        raise OSError("디스크 공간 부족(시뮬레이션)")

    monkeypatch.setattr(shutil, "copy2", failing_copy)

    with pytest.raises(MigrationBackupError):
        run_migrations(engine)

    # 백업이 실패했으니 스키마도 바뀌지 않아야 한다 (컬럼이 추가되지 않음).
    inspector = inspect(engine)
    present = {col["name"] for col in inspector.get_columns("inventions")}
    assert "refined_content" not in present


def test_migration_backup_filenames_do_not_collide_within_same_second(tmp_path, monkeypatch):
    """같은 초 안에 두 번 백업해도 파일명이 겹쳐 서로 덮어쓰지 않아야 한다."""
    from src.database.migrations import _unique_backup_path

    db_path = tmp_path / "old.db"
    db_path.write_bytes(b"fake")

    first = _unique_backup_path(db_path)
    first.write_bytes(b"backup-1")
    second = _unique_backup_path(db_path)

    assert first != second
    assert not second.exists()
