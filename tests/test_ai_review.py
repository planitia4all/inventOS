"""'AI로 검토하기' 12종 검토 정의 + Provider 검증."""
from __future__ import annotations

from src.ai.mock_provider import MockAIProvider
from src.ai.review import (
    PARTIAL_APPLY_FIELDS,
    PROMPT_INSTRUCTIONS,
    REVIEW_DEFAULT_FIELD,
    REVIEW_GROUPS,
    REVIEW_KIND_LABELS,
    STRUCTURED_FIELD_MAP,
    InventionReviewResult,
    apply_structured_value,
    build_context,
    coerce_review_result,
    render_review_result,
)
from src.database.models import Invention


def make_invention() -> Invention:
    return Invention(
        invention_no="INV-2026-00001",
        title="그래핀 발열체 세퍼레이터 접합",
        original_idea="그래핀 발열체를 이용해 세퍼레이터를 접합하는 방식",
        core_principle="국소 가열로 접합면을 녹인다",
    )


def test_review_groups_cover_twelve_kinds_in_three_groups():
    assert len(REVIEW_GROUPS) == 3
    all_kinds = [kind for _, items in REVIEW_GROUPS for kind, _ in items]
    assert len(all_kinds) == 12
    assert len(set(all_kinds)) == 12  # 중복 없음


def test_every_kind_has_a_label_default_field_and_prompt():
    for kind in REVIEW_KIND_LABELS:
        assert kind in REVIEW_DEFAULT_FIELD
        assert kind in PROMPT_INSTRUCTIONS


def test_partial_apply_fields_are_valid_invention_fields():
    invention = make_invention()
    for field, _label in PARTIAL_APPLY_FIELDS:
        assert hasattr(invention, field)


def test_build_context_includes_title_and_original_idea():
    context = build_context(make_invention())
    assert "그래핀 발열체 세퍼레이터 접합" in context
    assert "세퍼레이터를 접합하는 방식" in context
    assert "국소 가열로 접합면을 녹인다" in context


def test_mock_provider_review_invention_returns_structured_result_for_every_kind():
    provider = MockAIProvider()
    invention = make_invention()
    for kind in REVIEW_KIND_LABELS:
        result = provider.review_invention(invention, kind)
        assert isinstance(result, InventionReviewResult)
        assert result.raw_text.strip()
        assert REVIEW_KIND_LABELS[kind] in result.raw_text
        assert result.parse_error is None


def test_mock_provider_patent_search_terms_fills_keywords():
    provider = MockAIProvider()
    invention = make_invention()
    result = provider.review_invention(invention, "patent_search_terms")
    assert result.patent_keywords


def test_mock_provider_review_invention_does_not_mutate_invention():
    provider = MockAIProvider()
    invention = make_invention()
    original_idea = invention.original_idea
    provider.review_invention(invention, "summary")
    assert invention.original_idea == original_idea


def test_render_review_result_uses_findings_when_present():
    result = InventionReviewResult(findings="핵심 요약 문장")
    assert "핵심 요약 문장" in render_review_result(result)


def test_render_review_result_falls_back_to_raw_text_when_empty():
    result = InventionReviewResult(raw_text="AI가 준 원문")
    assert render_review_result(result) == "AI가 준 원문"


def test_coerce_review_result_handles_non_dict_gracefully():
    result = coerce_review_result("이건 JSON이 아니라 그냥 문자열입니다", "원문 그대로")
    assert result.parse_error is not None
    assert result.raw_text == "원문 그대로"
    assert result.findings == "원문 그대로"


def test_coerce_review_result_fills_missing_keys_with_defaults():
    partial = {"problem": "문제 설명", "findings": "요약"}
    result = coerce_review_result(partial, "원문")
    assert result.problem == "문제 설명"
    assert result.core_idea == ""
    assert result.patent_keywords == []
    assert result.parse_error is not None  # 누락된 키가 있었음을 알려준다


def test_coerce_review_result_accepts_full_valid_response():
    full = {
        "problem": "문제",
        "existing_method": "기존 방식",
        "limitations": "한계",
        "core_idea": "핵심",
        "working_principle": "원리",
        "differentiation": "차별점",
        "expected_effects": "효과",
        "implementation": "구현",
        "experiment_plan": "실험계획",
        "patent_keywords": ["키워드1", "키워드2"],
        "findings": "결론",
    }
    result = coerce_review_result(full, "원문")
    assert result.parse_error is None
    assert result.patent_keywords == ["키워드1", "키워드2"]


def test_apply_structured_value_returns_matching_field():
    structured = {"problem": "해결할 문제입니다"}
    assert apply_structured_value(structured, "problem_to_solve") == "해결할 문제입니다"


def test_apply_structured_value_returns_empty_when_missing():
    assert apply_structured_value(None, "problem_to_solve") == ""
    assert apply_structured_value({}, "problem_to_solve") == ""


def test_apply_structured_value_review_notes_falls_back_to_patent_keywords():
    structured = {"findings": "", "patent_keywords": ["세퍼레이터", "그래핀"]}
    assert apply_structured_value(structured, "review_notes") == "세퍼레이터, 그래핀"


def test_structured_field_map_covers_all_partial_apply_fields():
    for field, _label in PARTIAL_APPLY_FIELDS:
        assert field in STRUCTURED_FIELD_MAP
