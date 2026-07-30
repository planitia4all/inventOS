"""SQLite FK 제약이 실제로 켜져 있는지, ORM이 아니라 DB 레벨에서 검증.

`PRAGMA foreign_keys`는 SQLite에서 기본적으로 꺼져 있다. ORM 레벨 테스트
(예: test_invention_relations.py)만으로는 "SQLAlchemy가 맞게 처리했다"만
증명할 뿐, "DB 자체가 제약을 강제하는지"는 증명하지 못한다. 이 파일은
raw SQL로 직접 확인한다.
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from src.attachments.service import AttachmentService
from src.config.settings import Settings
from src.database.models import Base
from src.experiments.schemas import ExperimentInput
from src.experiments.service import ExperimentService
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService
from src.search.fts import ensure_index_table


def test_pragma_foreign_keys_is_on_for_new_connections(db_session):
    value = db_session.execute(text("PRAGMA foreign_keys")).scalar()
    assert value == 1


def test_raw_insert_with_nonexistent_invention_id_is_rejected(db_session):
    """FK 제약이 실제로 강제되고 있는지를 직접 증명한다 — ORM을 거치지 않고
    존재하지 않는 invention_id로 실험 기록을 넣으면 DB가 거부해야 한다."""
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO experiments (id, invention_id, created_at, updated_at) "
                "VALUES ('exp-orphan', 'no-such-invention-id', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        db_session.flush()
    db_session.rollback()


def test_deleting_parent_nulls_child_fk_at_db_level(db_session):
    """ORM이 아니라 실제 커밋된 DB 행을 직접 조회해 부모를 영구 삭제(purge)한
    뒤 자식의 parent_invention_id가 정말 NULL인지 확인한다.

    (참고: InventionService.delete()는 소프트 삭제(휴지통 이동)로, 자식
    관계를 건드리지 않는다 — 실제 하드 삭제는 purge()다.)
    """
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="부모 아이디어"))
    child = service.create_child(parent.id, QuickIdeaInput(memo="자식 아이디어"))
    db_session.commit()

    service.purge(parent.id)
    db_session.commit()

    row = db_session.execute(
        text("SELECT parent_invention_id FROM inventions WHERE id = :id"),
        {"id": child.id},
    ).one()
    assert row[0] is None


def test_deleting_experiment_with_attachment_nulls_experiment_id(tmp_path, db_session):
    """실험에 딸린 첨부파일이 있는 상태에서 그 실험을 지워도 FK 위반 없이
    성공해야 하고, 첨부파일 자체는 남되 experiment_id만 NULL이 되어야 한다."""
    settings = Settings(data_dir=tmp_path)
    invention_service = InventionService(db_session)
    invention = invention_service.quick_create(QuickIdeaInput(memo="실험 있는 아이디어"))

    experiment = ExperimentService(db_session).create(
        invention.id, ExperimentInput(results="1차 실험 결과")
    )
    attachment = AttachmentService(db_session, settings=settings).save(
        invention.id, "실험사진.png", b"fake-image-bytes", experiment_id=experiment.id
    )
    db_session.commit()

    ExperimentService(db_session).delete(experiment.id)
    db_session.commit()

    row = db_session.execute(
        text("SELECT experiment_id FROM attachments WHERE id = :id"),
        {"id": attachment.id},
    ).one()
    assert row[0] is None


def test_orm_nullify_works_even_on_pre_existing_db_without_ondelete_clause(tmp_path):
    """`ondelete="SET NULL"`은 새로 만드는 테이블에만 적용된다 — SQLite는
    ALTER TABLE로 기존 FK 제약을 못 바꾸므로, 이 코드 변경 전에 이미 만들어진
    사용자 DB의 실제 컬럼 정의에는 이 절이 없다. 그런 "예전" DB에서도 PRAGMA
    foreign_keys=ON 상태로 실험/부모 삭제가 여전히 안전한지 직접 확인한다 —
    SQLAlchemy가 관계를 통해 자식을 미리 NULL로 갱신한 뒤 삭제하기 때문에,
    DB에 선언된 ON DELETE 절과 무관하게 항상 안전해야 한다."""
    engine = create_engine(f"sqlite:///{tmp_path / 'pre_existing.db'}")
    with engine.begin() as conn:
        # `sorted_tables`(FK 의존성 위상정렬)를 쓰지 않고 이름순으로 만든다.
        # inventions ↔ experiments가 서로를 참조해서(Invention.source_experiment_id,
        # Experiment.invention_id) 위상정렬이 불가능하고, SQLAlchemy가
        # "unresolvable cycles" 경고를 낸다. SQLite는 CREATE TABLE 시점에
        # 아직 없는 테이블을 FK로 가리켜도 허용하므로 순서가 필요 없다.
        for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
            ddl = str(CreateTable(table).compile(engine))
            ddl = re.sub(
                r"\s+ON DELETE (SET NULL|SET DEFAULT|CASCADE|RESTRICT|NO ACTION)", "", ddl
            )
            conn.execute(text(ddl))
    ensure_index_table(engine)

    session = sessionmaker(bind=engine)()
    try:
        attachments_ddl = session.execute(
            text("SELECT sql FROM sqlite_master WHERE name='attachments'")
        ).scalar()
        assert "ON DELETE" not in attachments_ddl  # 정말 "예전 스키마"인지 확인

        settings = Settings(data_dir=tmp_path)
        invention = InventionService(session).quick_create(QuickIdeaInput(memo="예전 DB 발명"))
        experiment = ExperimentService(session).create(
            invention.id, ExperimentInput(results="예전 실험")
        )
        attachment = AttachmentService(session, settings=settings).save(
            invention.id, "예전사진.png", b"fake", experiment_id=experiment.id
        )
        session.commit()

        ExperimentService(session).delete(experiment.id)
        session.commit()
        row = session.execute(
            text("SELECT experiment_id FROM attachments WHERE id = :id"), {"id": attachment.id}
        ).one()
        assert row[0] is None

        parent = InventionService(session).quick_create(QuickIdeaInput(memo="예전 부모"))
        child = InventionService(session).create_child(parent.id, QuickIdeaInput(memo="예전 자식"))
        session.commit()

        InventionService(session).purge(parent.id)
        session.commit()
        row = session.execute(
            text("SELECT parent_invention_id FROM inventions WHERE id = :id"), {"id": child.id}
        ).one()
        assert row[0] is None
    finally:
        session.close()


def test_foreign_keys_enabled_on_fresh_file_engine(tmp_path):
    """실제 앱처럼 파일 기반 엔진을 새로 만들어도(테스트 fixture가 아니라)
    연결마다 PRAGMA가 켜지는지 확인한다."""
    engine = create_engine(f"sqlite:///{tmp_path / 'fk_check.db'}")
    Base.metadata.create_all(engine)
    ensure_index_table(engine)
    session = sessionmaker(bind=engine)()
    try:
        assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1
    finally:
        session.close()
