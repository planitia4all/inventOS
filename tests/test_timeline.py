"""Timeline(발전 이력) 자동 기록 검증."""
from __future__ import annotations

from src.inventions.schemas import InventionInput, QuickIdeaInput
from src.inventions.service import InventionService


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
