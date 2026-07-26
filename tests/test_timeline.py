"""Timeline(발전 이력) 자동 기록 검증."""
from __future__ import annotations

from src.attachments.service import AttachmentService
from src.config.settings import Settings
from src.experiments.schemas import ExperimentInput
from src.experiments.service import ExperimentService
from src.inventions.schemas import InventionInput, QuickIdeaInput
from src.inventions.service import InventionService
from src.patents.schemas import ComparisonInput, ManualPatentInput
from src.patents.service import PatentService


def test_creating_invention_logs_created_event(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="타임라인 테스트"))

    events = service.list_timeline(inv.id)
    assert [e.event_type for e in events] == ["created"]


def test_original_idea_edit_logs_event(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="원본"))
    service.update_original_idea(inv.id, "고친 원본")

    types = [e.event_type for e in service.list_timeline(inv.id)]
    assert types == ["created", "original_revised"]


def test_status_change_via_update_fields_logs_event(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="상태 변경 테스트"))
    service.update_fields(inv.id, status="실험 중")

    events = service.list_timeline(inv.id)
    status_events = [e for e in events if e.event_type == "status_changed"]
    assert len(status_events) == 1
    assert "실험 중" in status_events[0].description


def test_content_group_save_logs_content_updated(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="내용 채우기 테스트"))
    service.update_fields(inv.id, problem_to_solve="문제", core_principle="원리")

    types = [e.event_type for e in service.list_timeline(inv.id)]
    assert "content_updated" in types


def test_update_with_same_status_does_not_log_duplicate(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="테스트"))
    service.update_fields(inv.id, status=inv.status)

    events = [e for e in service.list_timeline(inv.id) if e.event_type == "status_changed"]
    assert events == []


def test_archive_and_unarchive_logs_events(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="보관 테스트"))
    service.set_archived(inv.id, True)
    service.set_archived(inv.id, False)

    types = [e.event_type for e in service.list_timeline(inv.id)]
    assert types == ["created", "archived", "unarchived"]


def test_timeline_is_chronological(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="순서 테스트"))
    service.update_original_idea(inv.id, "수정1")
    service.update_fields(inv.id, status="검토 중")

    events = service.list_timeline(inv.id)
    timestamps = [e.occurred_at for e in events]
    assert timestamps == sorted(timestamps)


def test_create_with_full_input_logs_single_created_event(db_session):
    service = InventionService(db_session)
    inv = service.create(InventionInput(title="발명", original_idea="본문"))
    types = [e.event_type for e in service.list_timeline(inv.id)]
    assert types == ["created"]


def test_tags_changed_logs_event(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="태그 테스트"))
    service.set_tags(inv.id, ["배터리", "AI"])

    types = [e.event_type for e in service.list_timeline(inv.id)]
    assert "tags_changed" in types


def test_setting_same_tags_does_not_log_duplicate(db_session):
    service = InventionService(db_session)
    inv = service.quick_create(QuickIdeaInput(memo="태그 중복 테스트", keywords=["배터리"]))
    service.set_tags(inv.id, ["배터리"])

    types = [e.event_type for e in service.list_timeline(inv.id)]
    assert types.count("tags_changed") == 0


def test_experiment_update_and_delete_log_events(db_session):
    inv_service = InventionService(db_session)
    inv = inv_service.quick_create(QuickIdeaInput(memo="실험 타임라인 테스트"))
    exp_service = ExperimentService(db_session)
    exp = exp_service.create(inv.id, ExperimentInput(results="1차 결과"))
    exp_service.update(exp.id, ExperimentInput(results="수정된 결과"))
    exp_service.delete(exp.id)

    types = [e.event_type for e in inv_service.list_timeline(inv.id)]
    assert "experiment_updated" in types
    assert "experiment_deleted" in types


def test_attachment_removed_logs_event(db_session, tmp_path):
    inv_service = InventionService(db_session)
    inv = inv_service.quick_create(QuickIdeaInput(memo="첨부 타임라인 테스트"))
    att_service = AttachmentService(db_session, settings=Settings(data_dir=tmp_path))
    att = att_service.save(inv.id, "photo.png", b"fake-bytes")
    att_service.delete(att)

    types = [e.event_type for e in inv_service.list_timeline(inv.id)]
    assert "attachment_removed" in types


def test_patent_comparison_update_and_unlink_log_events(db_session):
    inv_service = InventionService(db_session)
    inv = inv_service.quick_create(QuickIdeaInput(memo="특허 타임라인 테스트"))
    patent_service = PatentService(db_session)
    link = patent_service.register_manual(
        inv.id,
        ManualPatentInput(title="선행특허", publication_number="KR10-2020-0000001"),
    )
    patent_service.update_comparison(link.id, ComparisonInput(similarities="유사함"))
    patent_service.delete_link(link.id)

    types = [e.event_type for e in inv_service.list_timeline(inv.id)]
    assert "prior_art_updated" in types
    assert "prior_art_unlinked" in types
