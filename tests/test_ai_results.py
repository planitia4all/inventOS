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


def test_create_draft_stores_model_and_input_snapshot(db_session):
    invention = make_invention(db_session)
    draft = AIResultService(db_session).create_draft(
        invention.id,
        "summary",
        "정리된 내용",
        provider="anthropic",
        model="claude-sonnet-5",
        input_snapshot="발명 제목: 테스트\n최초 아이디어: 원본은 절대 바뀌면 안 된다",
    )

    assert draft.provider == "anthropic"
    assert draft.model == "claude-sonnet-5"
    assert "원본은 절대 바뀌면 안 된다" in draft.input_snapshot
    assert draft.status == "생성됨"


def test_apply_with_target_fields_writes_all_selected_fields(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "여러 필드에 반영될 내용")

    service.apply(draft.id, target_fields=["problem_to_solve", "core_principle"])

    refreshed = InventionService(db_session).get(invention.id)
    assert refreshed.problem_to_solve == "여러 필드에 반영될 내용"
    assert refreshed.core_principle == "여러 필드에 반영될 내용"


def test_apply_records_applied_fields_list(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "내용")

    applied = service.apply(draft.id, target_fields=["problem_to_solve", "differentiation"])

    assert applied.applied_fields == ["problem_to_solve", "differentiation"]
    assert applied.applied_to_field == "problem_to_solve"
    assert applied.status == "반영됨"


def test_apply_creates_revision_before_applying(db_session):
    invention = make_invention(db_session)
    InventionService(db_session).update_fields(invention.id, refined_content="적용 전 내용")
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "새 내용")

    assert InventionService(db_session).list_revisions(invention.id) == []
    service.apply(draft.id)

    revisions = InventionService(db_session).list_revisions(invention.id)
    assert len(revisions) == 1
    assert revisions[0].snapshot_json["refined_content"] == "적용 전 내용"


def test_apply_timeline_mentions_kind_and_fields(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "내용")
    service.apply(draft.id, target_fields=["problem_to_solve"])

    events = InventionService(db_session).list_timeline(invention.id)
    applied_event = next(e for e in events if e.event_type == "ai_result_applied")
    assert "아이디어 정리" in applied_event.description
    assert "해결하려는 문제" in applied_event.description
    assert applied_event.meta_json["applied_fields"] == ["problem_to_solve"]


def test_rerunning_same_kind_keeps_both_results(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    first = service.create_draft(invention.id, "summary", "1차 결과")
    second = service.create_draft(invention.id, "summary", "2차 결과")

    results = service.list_for_invention(invention.id)
    assert {r.id for r in results} == {first.id, second.id}
    assert first.id != second.id


def test_archive_marks_status_without_applying(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "보관될 내용")

    archived = service.archive(draft.id)

    assert archived.status == "보관됨"
    assert archived.applied_at is None
    refreshed = InventionService(db_session).get(invention.id)
    assert not (refreshed.refined_content or "").strip()
    assert draft.id not in [r.id for r in service.list_pending(invention.id)]


def test_discard_is_soft_delete_hidden_from_default_list(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "삭제될 내용")
    service.discard(draft.id)

    assert service.list_for_invention(invention.id) == []
    all_results = service.list_for_invention(invention.id, include_deleted=True)
    assert [r.status for r in all_results] == ["삭제됨"]


def test_create_draft_stores_structured_content_and_parse_error(db_session):
    invention = make_invention(db_session)
    structured = {"problem": "구조화된 문제 설명", "patent_keywords": ["A", "B"]}
    draft = AIResultService(db_session).create_draft(
        invention.id,
        "problem_extraction",
        "렌더링된 텍스트",
        structured_content=structured,
        parse_error="일부 항목이 누락되었습니다",
    )

    assert draft.structured_content == structured
    assert draft.parse_error == "일부 항목이 누락되었습니다"


def test_apply_uses_structured_value_for_matching_field(db_session):
    """일부만 반영할 때, 구조화된 응답이 있으면 해당 필드에 정확히 맞는
    값만 반영되고 관련 없는 다른 항목의 텍스트가 섞이지 않아야 한다."""
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    structured = {
        "problem": "정확한 문제 설명",
        "core_idea": "정확한 핵심 아이디어",
    }
    draft = service.create_draft(
        invention.id,
        "summary",
        "AI 결과 전체 렌더링 텍스트(문제+핵심아이디어 다 섞여 있음)",
        structured_content=structured,
    )

    service.apply(draft.id, target_fields=["problem_to_solve", "core_principle"])

    refreshed = InventionService(db_session).get(invention.id)
    assert refreshed.problem_to_solve == "정확한 문제 설명"
    assert refreshed.core_principle == "정확한 핵심 아이디어"


def test_apply_falls_back_to_full_content_when_structured_field_empty(db_session):
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(
        invention.id,
        "summary",
        "전체 내용으로 대체됨",
        structured_content={"problem": ""},  # 이 필드는 비어 있음
    )

    service.apply(draft.id, target_fields=["problem_to_solve"])

    refreshed = InventionService(db_session).get(invention.id)
    assert refreshed.problem_to_solve == "전체 내용으로 대체됨"


def test_apply_without_structured_content_uses_full_content(db_session):
    """Mock/파싱 실패 등으로 structured_content가 없어도 기존처럼 동작해야 한다."""
    invention = make_invention(db_session)
    service = AIResultService(db_session)
    draft = service.create_draft(invention.id, "summary", "구조화 없는 결과")

    service.apply(draft.id, target_fields=["problem_to_solve", "core_principle"])

    refreshed = InventionService(db_session).get(invention.id)
    assert refreshed.problem_to_solve == "구조화 없는 결과"
    assert refreshed.core_principle == "구조화 없는 결과"
