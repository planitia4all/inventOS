"""AI 키가 없을 때 사용하는 결정론적 Mock Provider.

실제 AI를 호출하지 않으며, 발명/특허 텍스트에서 단순 규칙으로
결과를 만들어 UI 흐름을 테스트할 수 있게 한다.
"""
from __future__ import annotations

import re

from src.ai.base import PatentComparisonDraft, SearchTerms
from src.ai.review import PROMPT_INSTRUCTIONS, REVIEW_KIND_LABELS
from src.database.models import Invention, PatentDocument

_STOPWORDS = {"the", "a", "an", "of", "and", "or", "to", "for", "is", "with", "in", "on"}


def _extract_keywords(text: str, limit: int = 6) -> list[str]:
    tokens = re.findall(r"[A-Za-z가-힣]{2,}", text or "")
    seen: list[str] = []
    for token in tokens:
        low = token.lower()
        if low in _STOPWORDS:
            continue
        if token not in seen:
            seen.append(token)
        if len(seen) >= limit:
            break
    return seen


class MockAIProvider:
    name = "mock"

    def generate_search_terms(self, invention: Invention) -> SearchTerms:
        base_text = " ".join(
            filter(
                None,
                [invention.title, invention.original_idea, invention.core_principle],
            )
        )
        keywords = _extract_keywords(base_text, limit=8)
        korean = [k for k in keywords if re.search(r"[가-힣]", k)]
        english = [k for k in keywords if not re.search(r"[가-힣]", k)]

        return SearchTerms(
            korean_keywords=korean or [invention.title],
            english_keywords=english,
            synonyms=[],
            materials=[],
            processes=[],
            device_terms=[],
            functional_phrases=[],
            ipc_candidates=[],
            cpc_candidates=[],
            recommended_queries=[invention.title] + korean[:2] + english[:2],
        )

    def translate_abstract(self, abstract: str, source_language: str) -> str:
        if not abstract:
            return ""
        return f"[Mock 번역 / 원문 언어: {source_language or '미상'}] {abstract}"

    def summarize_patent(self, patent: PatentDocument) -> str:
        abstract = patent.abstract_original or ""
        summary = abstract[:120].strip()
        return f"[Mock 요약] {summary}{'...' if len(abstract) > 120 else ''}"

    def compare_invention_and_patent(
        self, invention: Invention, patent: PatentDocument
    ) -> PatentComparisonDraft:
        return PatentComparisonDraft(
            similarities=["(Mock) 두 문서 모두 유사한 기술 분야를 다룹니다."],
            differences=["(Mock) 세부 구현 방식에 차이가 있을 수 있습니다."],
            prior_patent_core=(patent.abstract_original or "")[:100],
            possible_differentiators=["(Mock) 실제 AI Provider 설정 후 다시 생성하세요."],
            technical_risks=[],
            additional_search_terms=[],
            confidence=0,
        )

    def review_invention(self, invention: Invention, kind: str) -> str:
        label = REVIEW_KIND_LABELS.get(kind, kind)
        instruction = PROMPT_INSTRUCTIONS.get(kind, "")
        base_text = (invention.original_idea or invention.title or "").strip()
        snippet = base_text[:80] + ("..." if len(base_text) > 80 else "")
        return (
            f"[Mock {label}]\n{instruction}\n\n"
            f"원본 요약: {snippet}\n"
            "(실제 AI Provider를 설정하면 더 구체적인 결과를 받을 수 있습니다.)"
        )
