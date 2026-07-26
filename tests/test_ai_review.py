"""'AI로 검토하기' 12종 검토 정의 + Provider 검증."""
from __future__ import annotations

from src.ai.mock_provider import MockAIProvider
from src.ai.review import (
    PARTIAL_APPLY_FIELDS,
    PROMPT_INSTRUCTIONS,
    REVIEW_DEFAULT_FIELD,
    REVIEW_GROUPS,
    REVIEW_KIND_LABELS,
    build_context,
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


def test_mock_provider_review_invention_returns_text_for_every_kind():
    provider = MockAIProvider()
    invention = make_invention()
    for kind in REVIEW_KIND_LABELS:
        result = provider.review_invention(invention, kind)
        assert isinstance(result, str)
        assert result.strip()
        assert REVIEW_KIND_LABELS[kind] in result


def test_mock_provider_review_invention_does_not_mutate_invention():
    provider = MockAIProvider()
    invention = make_invention()
    original_idea = invention.original_idea
    provider.review_invention(invention, "summary")
    assert invention.original_idea == original_idea
