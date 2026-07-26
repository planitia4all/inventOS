"""AI Provider 공통 인터페이스.

AI는 항상 선택 기능이다. API 키가 없어도 MockAIProvider로 프로그램이
정상 동작해야 한다. AI가 생성한 결과는 원문 데이터와 명확히 분리해서
저장하고, 비교 초안은 사용자가 검토 후 '적용'을 눌러야 확정 저장된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.database.models import Invention, PatentDocument


class AIProviderError(Exception):
    """AI 호출 실패 (네트워크, 인증, 응답 형식 오류 등).

    발생해도 발명/특허 데이터에는 영향을 주지 않아야 한다.
    """


@dataclass
class SearchTerms:
    korean_keywords: list[str] = field(default_factory=list)
    english_keywords: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    processes: list[str] = field(default_factory=list)
    device_terms: list[str] = field(default_factory=list)
    functional_phrases: list[str] = field(default_factory=list)
    ipc_candidates: list[str] = field(default_factory=list)
    cpc_candidates: list[str] = field(default_factory=list)
    recommended_queries: list[str] = field(default_factory=list)


@dataclass
class PatentComparisonDraft:
    similarities: list[str] = field(default_factory=list)
    differences: list[str] = field(default_factory=list)
    prior_patent_core: str = ""
    possible_differentiators: list[str] = field(default_factory=list)
    technical_risks: list[str] = field(default_factory=list)
    additional_search_terms: list[str] = field(default_factory=list)
    confidence: int = 0

    def to_dict(self) -> dict:
        return {
            "similarities": self.similarities,
            "differences": self.differences,
            "prior_patent_core": self.prior_patent_core,
            "possible_differentiators": self.possible_differentiators,
            "technical_risks": self.technical_risks,
            "additional_search_terms": self.additional_search_terms,
            "confidence": self.confidence,
        }


class AIProvider(Protocol):
    name: str

    def generate_search_terms(self, invention: Invention) -> SearchTerms:
        ...

    def translate_abstract(self, abstract: str, source_language: str) -> str:
        ...

    def summarize_patent(self, patent: PatentDocument) -> str:
        ...

    def compare_invention_and_patent(
        self, invention: Invention, patent: PatentDocument
    ) -> PatentComparisonDraft:
        ...

    def review_invention(self, invention: Invention, kind: str) -> str:
        """'AI로 검토하기'의 한 항목(예: 아이디어 정리, 실현 가능성 검토)을 실행한다.

        결과 텍스트만 반환한다 — 발명 내용을 저장/수정하는 것은 이 함수의
        책임이 아니다 (호출한 쪽이 InventionAIResult로 별도 저장한다).
        """
        ...
