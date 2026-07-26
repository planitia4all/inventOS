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


def test_save_rejects_oversized_file(db_session, tmp_path):
    from src.attachments.service import MAX_ATTACHMENT_SIZE_BYTES

    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    oversized = b"x" * (MAX_ATTACHMENT_SIZE_BYTES + 1)
    with pytest.raises(AttachmentError):
        service.save(invention.id, "huge.png", oversized)


def test_save_accepts_file_at_size_limit(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    att = service.save(invention.id, "ok.png", b"x" * 10)
    assert att.original_filename == "ok.png"


def test_korean_and_long_filenames_do_not_affect_storage(db_session, tmp_path):
    """원본 파일명은 DB에만 저장되고, 실제 파일 경로는 항상 UUID를
    사용하므로 한글/긴 파일명이 파일시스템 문제를 일으키지 않는다."""
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    long_korean_name = ("실험결과_" * 30) + ".png"
    att = service.save(invention.id, long_korean_name, b"fake-bytes")

    assert att.original_filename == long_korean_name
    path = service.resolve_path(att)
    assert path.exists()
    # 실제 저장 파일명은 원본 파일명과 무관한 UUID 기반이다.
    assert path.name != long_korean_name


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


def test_check_integrity_reports_healthy_when_all_consistent(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    service.save(invention.id, "photo.png", b"unique-bytes-1")

    report = service.check_integrity()

    assert report.is_healthy
    assert report.missing_files == []
    assert report.orphaned_files == []


def test_check_integrity_detects_missing_file(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    attachment = service.save(invention.id, "photo.png", b"will-be-deleted")
    service.resolve_path(attachment).unlink()  # DB 행은 남기고 실제 파일만 지운다

    report = service.check_integrity()

    assert not report.is_healthy
    assert [m["id"] for m in report.missing_files] == [attachment.id]


def test_check_integrity_detects_orphaned_file(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    service.save(invention.id, "photo.png", b"tracked-bytes")

    orphan_dir = service.settings.attachments_dir / invention.id
    orphan_dir.mkdir(parents=True, exist_ok=True)
    (orphan_dir / "untracked-file.png").write_bytes(b"nobody-points-to-me")

    report = service.check_integrity()

    assert not report.is_healthy
    assert any("untracked-file.png" in path for path in report.orphaned_files)


def test_check_integrity_detects_zero_byte_file(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    attachment = service.save(invention.id, "photo.png", b"")

    report = service.check_integrity()

    assert not report.is_healthy
    assert [z["id"] for z in report.zero_byte_files] == [attachment.id]


def test_check_integrity_detects_duplicate_content(db_session, tmp_path):
    invention = make_invention(db_session)
    service = make_service(db_session, tmp_path)
    first = service.save(invention.id, "photo1.png", b"same-bytes-twice")
    second = service.save(invention.id, "photo2.png", b"same-bytes-twice")

    report = service.check_integrity()

    assert not report.is_healthy
    assert len(report.duplicate_groups) == 1
    group_ids = {item["id"] for item in report.duplicate_groups[0]}
    assert group_ids == {first.id, second.id}
