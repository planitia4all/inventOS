"""첨부파일 서비스 검증: 종류 분류, 확장자, 실험 연결."""
from __future__ import annotations

import pytest

from src.attachments.service import (
    AttachmentError,
    AttachmentService,
    attachment_kind,
    default_category,
)
from src.config.settings import Settings
from src.experiments.schemas import ExperimentInput
from src.experiments.service import ExperimentService
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService


def make_invention(session):
    return InventionService(session).quick_create(QuickIdeaInput(memo="첨부 테스트용"))


def make_service(db_session, tmp_path) -> AttachmentService:
    return AttachmentService(db_session, settings=Settings(data_dir=tmp_path))


def test_default_category_by_extension():
    assert default_category("photo.png") == "사진"
    assert default_category("memo.wav") == "음성"
    assert default_category("clip.mp4") == "동영상"
    assert default_category("spec.pdf") == "참고자료"
    assert default_category("unknown.xyz") == "기타"


def test_attachment_kind_recognizes_video():
    assert attachment_kind("clip.mp4") == "video"
    assert attachment_kind("clip.mov") == "video"


def test_save_infers_category_when_not_given(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    att = service.save(invention.id, "photo.png", b"fake-bytes")
    assert att.category == "사진"


def test_save_respects_explicit_category(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    att = service.save(invention.id, "diagram.png", b"fake-bytes", category="도면")
    assert att.category == "도면"


def test_save_rejects_disallowed_extension(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    with pytest.raises(AttachmentError):
        service.save(invention.id, "virus.exe", b"x")


def test_save_video_extension_allowed(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    att = service.save(invention.id, "clip.mp4", b"fake-bytes")
    assert att.category == "동영상"


def test_save_links_attachment_to_experiment(db_session, tmp_path):
    invention = make_invention(db_session)
    experiment = ExperimentService(db_session).create(
        invention.id, ExperimentInput(results="1차 시험")
    )
    service = make_service(db_session, tmp_path)
    att = service.save(
        invention.id,
        "result.jpg",
        b"fake-bytes",
        category="실험 자료",
        experiment_id=experiment.id,
    )

    assert att.experiment_id == experiment.id
    assert [a.id for a in service.list_for_experiment(experiment.id)] == [att.id]


def test_save_logs_timeline_event(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    service.save(invention.id, "photo.png", b"fake-bytes")

    types = [e.event_type for e in InventionService(db_session).list_timeline(invention.id)]
    assert "attachment_added" in types


def test_copy_to_invention_creates_independent_file(db_session, tmp_path):
    parent = make_invention(db_session)
    child = InventionService(db_session).quick_create(QuickIdeaInput(memo="파생 아이디어"))
    service = make_service(db_session, tmp_path)
    original = service.save(parent.id, "photo.png", b"original-bytes", category="사진")

    copied = service.copy_to_invention(original, child.id)

    assert copied.invention_id == child.id
    assert copied.original_filename == "photo.png"
    assert copied.category == "사진"
    assert copied.id != original.id
    assert service.resolve_path(copied).read_bytes() == b"original-bytes"
    # 원본 파일은 그대로 남아 있다 (복사이지 이동이 아니다).
    assert service.resolve_path(original).exists()
