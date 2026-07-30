"""ConversationImport 테이블 추가 마이그레이션 + 트랜잭션 + 중복 검사.

기존 0.4.0 DB를 열었을 때 발명 데이터를 하나도 잃지 않고 새 테이블만
생기는지 확인한다. 새 테이블도 스키마 변경이므로 **백업이 먼저**
만들어져야 한다 — 예전에는 `create_all()`이 `run_migrations()`보다 먼저
불려서, 테이블이 생기는 마이그레이션에서는 백업이 만들어지기 전에
스키마가 이미 바뀌어 있었다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.conversations.service import ConversationImportService
from src.database.migrations import MigrationBackupError, run_migrations
from src.database.models import Base, ConversationImport
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService

RAW = "그래핀 섬유 관통 배치 대화 원문. " * 20

# 0.4.0-rc.1 시점의 inventions 테이블 (conversation_imports가 없던 때).
_V040_SCHEMA = """
CREATE TABLE inventions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    invention_no VARCHAR(32) NOT NULL UNIQUE,
    title VARCHAR(500) NOT NULL,
    technical_field VARCHAR(200),
    original_idea TEXT NOT NULL,
    refined_content TEXT,
    problem_to_solve TEXT,
    conventional_method TEXT,
    conventional_problems TEXT,
    core_principle TEXT,
    key_components TEXT,
    operating_principle TEXT,
    differentiation TEXT,
    expected_effects TEXT,
    technical_barriers TEXT,
    applicable_industries TEXT,
    implementation_method TEXT,
    experiment_notes TEXT,
    review_notes TEXT,
    keywords JSON,
    inventor_name VARCHAR(200),
    status VARCHAR(50),
    is_favorite BOOLEAN,
    is_archived BOOLEAN,
    deleted_at DATETIME,
    parent_invention_id VARCHAR(36),
    derivation_reason VARCHAR(200),
    source_experiment_id VARCHAR(36),
    owner_id VARCHAR(100),
    created_at DATETIME,
    updated_at DATETIME,
    version INTEGER
)
"""


def _v040_db(tmp_path):
    """conversation_imports가 없는 기존 DB를 만든다 (create_all을 부르지 않는다)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'v040.db'}")
    with engine.begin() as conn:
        conn.execute(text(_V040_SCHEMA))
        conn.execute(
            text(
                "INSERT INTO inventions "
                "(id, invention_no, title, original_idea, status, version) "
                "VALUES ('inv-1', 'INV-2026-00001', '기존 발명', "
                "'기존 발명의 원본 메모', '아이디어', 1)"
            )
        )
    return engine


# ---------------------------------------------------------------------------
# 신규 DB
# ---------------------------------------------------------------------------


def test_fresh_db_gets_the_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")

    run_migrations(engine)

    assert "conversation_imports" in inspect(engine).get_table_names()


def test_fresh_db_needs_no_backup(tmp_path):
    """백업할 기존 데이터가 없으면 백업 파일을 만들지 않는다."""
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")

    run_migrations(engine)

    assert list(tmp_path.glob("fresh_backup_*.db")) == []


# ---------------------------------------------------------------------------
# 기존 0.4.0 DB
# ---------------------------------------------------------------------------


def test_existing_db_gets_the_table(tmp_path):
    engine = _v040_db(tmp_path)

    run_migrations(engine)

    assert "conversation_imports" in inspect(engine).get_table_names()


def test_existing_db_is_backed_up_before_the_table_is_created(tmp_path):
    engine = _v040_db(tmp_path)

    run_migrations(engine)

    backups = list(tmp_path.glob("v040_backup_*.db"))
    assert len(backups) == 1
    # 백업본은 마이그레이션 **전** 상태여야 한다.
    backup_engine = create_engine(f"sqlite:///{backups[0]}")
    assert "conversation_imports" not in inspect(backup_engine).get_table_names()


def test_existing_invention_data_is_preserved(tmp_path):
    engine = _v040_db(tmp_path)

    run_migrations(engine)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT title, original_idea FROM inventions WHERE id='inv-1'")
        ).one()
    assert row.title == "기존 발명"
    assert row.original_idea == "기존 발명의 원본 메모"


def test_existing_tables_are_not_rewritten(tmp_path):
    """SQLite에서 테이블 재작성은 데이터 손실 위험이 크다 — 하지 않는다."""
    engine = _v040_db(tmp_path)
    with engine.connect() as conn:
        before = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE name='inventions'")
        ).scalar()

    run_migrations(engine)

    with engine.connect() as conn:
        after = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE name='inventions'")
        ).scalar()
    assert before == after


def test_indexes_and_unique_constraint_are_created(tmp_path):
    engine = _v040_db(tmp_path)

    run_migrations(engine)

    inspector = inspect(engine)
    index_names = {ix["name"] for ix in inspector.get_indexes("conversation_imports")}
    assert {
        "ix_conversation_import_invention_hash",
        "ix_conversation_import_hash",
        "ix_conversation_import_invention_deleted",
        "ix_conversation_import_previous",
    } <= index_names

    unique_names = {
        uc["name"] for uc in inspector.get_unique_constraints("conversation_imports")
    }
    assert "uq_conversation_import_seq" in unique_names


def test_migration_is_idempotent(tmp_path):
    engine = _v040_db(tmp_path)

    run_migrations(engine)
    run_migrations(engine)  # 두 번 돌려도 같은 결과

    assert "conversation_imports" in inspect(engine).get_table_names()
    assert len(list(tmp_path.glob("v040_backup_*.db"))) == 1


def test_migration_aborts_when_backup_fails(tmp_path, monkeypatch):
    """백업이 실패하면 안전망 없이 스키마를 바꾸지 않는다."""
    import src.database.migrations as migrations_module

    engine = _v040_db(tmp_path)
    monkeypatch.setattr(
        migrations_module, "backup_to_file", lambda db_path, dest_path: False
    )

    with pytest.raises(MigrationBackupError):
        run_migrations(engine)

    assert "conversation_imports" not in inspect(engine).get_table_names()


def test_data_can_be_written_right_after_migration(tmp_path):
    engine = _v040_db(tmp_path)
    run_migrations(engine)

    session = sessionmaker(bind=engine)()
    try:
        record = ConversationImportService(session).create("inv-1", RAW)
        session.commit()
        assert record.sequence_no == 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 트랜잭션 원자성
# ---------------------------------------------------------------------------


def test_rollback_leaves_no_partial_row(db_session):
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    service.create(invention.id, RAW)

    db_session.rollback()

    assert db_session.query(ConversationImport).count() == 0


def test_failure_after_create_rolls_back_everything(db_session):
    """저장 도중 실패하면 대화도 발명도 남지 않아야 한다."""
    service_session = db_session
    try:
        invention = InventionService(service_session).quick_create(
            QuickIdeaInput(memo="실패할 발명")
        )
        ConversationImportService(service_session).create(invention.id, RAW)
        raise RuntimeError("저장 도중 실패")
    except RuntimeError:
        service_session.rollback()

    assert service_session.query(ConversationImport).count() == 0


def test_partial_analysis_json_is_not_left_behind(db_session):
    """분석 결과 저장이 중간에 실패하면 예전 JSON이 그대로 남아야 한다."""
    from src.conversations.analysis_schema import AnalysisItem, load_analysis

    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    record = service.create(invention.id, RAW)

    first = load_analysis(None)
    first.set_items(
        "new_elements", [AnalysisItem(item_id="keep", text="처음 제안", change_type="new")]
    )
    service.update_analysis(record.id, first)
    db_session.commit()
    saved = record.analysis_json

    second = load_analysis(None)
    second.set_items(
        "new_elements", [AnalysisItem(item_id="lost", text="쓰다 만 제안", change_type="new")]
    )
    service.update_analysis(record.id, second)
    db_session.rollback()

    db_session.expire_all()
    assert service.get(record.id).analysis_json == saved


def test_sequence_contention_does_not_break_the_outer_transaction(db_session):
    """회차 충돌 재시도(SAVEPOINT)가 바깥 트랜잭션을 깨뜨리면 안 된다."""
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    service.create(invention.id, RAW)

    calls = {"n": 0}
    real = service.repo.next_sequence_no

    def flaky(invention_id: str) -> int:
        calls["n"] += 1
        return 1 if calls["n"] == 1 else real(invention_id)

    service.repo.next_sequence_no = flaky
    service.create(invention.id, RAW + "2")
    db_session.commit()

    assert [r.sequence_no for r in service.list_for_invention(invention.id)] == [1, 2]


# ---------------------------------------------------------------------------
# 원문 중복 검사 (§6.4)
# ---------------------------------------------------------------------------


def test_same_content_in_the_same_invention_is_flagged(db_session):
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    service.create(invention.id, RAW)

    check = service.check_duplicate(invention.id, RAW)

    assert check.result == "exact_duplicate_same_invention"
    assert check.is_duplicate is True


def test_same_content_in_another_invention_is_flagged_differently(db_session):
    first = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명 A"))
    second = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명 B"))
    service = ConversationImportService(db_session)
    service.create(first.id, RAW)

    check = service.check_duplicate(second.id, RAW)

    assert check.result == "exact_duplicate_other_invention"
    assert check.other_invention


def test_new_content_is_not_flagged(db_session):
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    service.create(invention.id, RAW)

    check = service.check_duplicate(invention.id, "완전히 다른 대화 내용. " * 20)

    assert check.result == "new"
    assert check.is_duplicate is False


def test_whitespace_only_difference_counts_as_duplicate(db_session):
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    service.create(invention.id, RAW)

    check = service.check_duplicate(invention.id, RAW.replace(" ", "  ") + "\n\n")

    assert check.result == "exact_duplicate_same_invention"


def test_duplicate_is_a_warning_not_a_hard_block(db_session):
    """사용자가 같은 원문을 일부러 다시 넣을 수 있다 — DB가 막지 않는다."""
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    service.create(invention.id, RAW)

    second = service.create(invention.id, RAW)
    db_session.commit()

    assert second.sequence_no == 2
    assert second.raw_content_hash == service.get(second.id).raw_content_hash


def test_soft_deleted_duplicates_are_ignored(db_session):
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    record = service.create(invention.id, RAW)
    service.soft_delete(record.id)

    assert service.check_duplicate(invention.id, RAW).result == "new"


# ---------------------------------------------------------------------------
# 발명 삭제와의 관계 (§13)
# ---------------------------------------------------------------------------


def test_soft_deleting_the_invention_keeps_its_conversations(db_session):
    """발명을 휴지통에 넣는 것은 대화에 아무 영향이 없다."""
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    record = service.create(invention.id, RAW)

    InventionService(db_session).delete(invention.id)
    db_session.commit()

    assert service.get(record.id) is not None


def test_purging_the_invention_removes_its_conversations(db_session):
    """영구 삭제는 되돌릴 수 없는 작업이라 대화도 함께 사라진다."""
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    record = service.create(invention.id, RAW)
    db_session.commit()

    InventionService(db_session).purge(invention.id)
    db_session.commit()

    assert service.get(record.id) is None


def test_conversation_rows_are_never_orphaned(db_session):
    """FK에 ON DELETE 절이 없으므로, 발명만 지우려 하면 DB가 막는다."""
    from sqlalchemy.exc import IntegrityError

    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    ConversationImportService(db_session).create(invention.id, RAW)
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM inventions WHERE id = :id"), {"id": invention.id}
        )
