"""AI 결과 독립 객체 검증.

원본을 수정하지 않고, 사용자가 '적용'을 눌러야만 발명 내용에 반영된다.
"""
from __future__ import annotations

import pytest

from src.ai.results_service import AIResultService
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService


def make_invention(session):
    return InventionService(session).quick_create(
        QuickIdeaInput(memo="원본은 절대 바뀌면 안 된다")
    )


def test_create_draft_does_not_touch_invention(db_session):
    invention = make_invention(db_session)
    original_idea = invention.original_idea

    AIResultService(db_session).create_draft(
        invention.id, "summary", "AI가 정리한 요약입니다."
    )

    refreshed = InventionService(db_session).get(invention.id)
    assert refreshed.original_idea == original_idea
    assert not (refreshed.refined_content or "").strip()


def test_draft_is_pending_until_applied(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "정리된 내용")

    pending = service.list_pending(invention.id)
    assert [p.id for p in pending] == [draft.id]
    assert draft.applied_at is None
    assert draft.applied_to_field is None


def test_apply_copies_content_into_default_field(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "정리된 내용")

    applied = service.apply(draft.id)

    assert applied.applied_at is not None
    assert applied.applied_to_field == "refined_content"
    refreshed = InventionService(db_session).get(invention.id)
    assert refreshed.refined_content == "정리된 내용"


def test_apply_with_explicit_target_field(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "improvement", "개선안 텍스트")

    service.apply(draft.id, target_field="expected_effects")

    refreshed = InventionService(db_session).get(invention.id)
    assert refreshed.expected_effects == "개선안 텍스트"


def test_apply_appends_to_existing_content(db_session):
    invention = make_invention(db_session)
    InventionService(db_session).update_fields(
        invention.id, refined_content="기존 내용"
    )
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "새 내용")
    service.apply(draft.id)

    refreshed = InventionService(db_session).get(invention.id)
    assert "기존 내용" in refreshed.refined_content
    assert "새 내용" in refreshed.refined_content


def test_applied_draft_no_longer_pending(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "내용")
    service.apply(draft.id)

    assert service.list_pending(invention.id) == []


def test_apply_logs_timeline_event(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "내용")
    service.apply(draft.id)

    types = [e.event_type for e in InventionService(db_session).list_timeline(invention.id)]
    assert "ai_result_applied" in types


def test_discard_removes_draft_without_applying(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "버릴 내용")
    service.discard(draft.id)

    assert service.list_for_invention(invention.id) == []
    refreshed = InventionService(db_session).get(invention.id)
    assert not (refreshed.refined_content or "").strip()


def test_apply_unknown_draft_raises(db_session):
    with pytest.raises(LookupError):
        AIResultService(db_session).apply("no-such-id")
