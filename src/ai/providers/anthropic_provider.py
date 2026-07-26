"""Anthropic Claude 기반 AI Provider.

검색어 생성/비교초안은 JSON 스키마로 응답 형식을 강제하고, 번역/요약은
일반 텍스트 응답을 사용한다. 모든 호출 실패(인증, 네트워크, 응답 형식
오류)는 AIProviderError로 감싸서 상위에서 안전하게 처리한다.
"""
from __future__ import annotations

import json

import anthropic

from src.ai.base import AIProviderError, PatentComparisonDraft, SearchTerms
from src.ai.review import (
    PROMPT_INSTRUCTIONS,
    STRUCTURED_RESULT_SCHEMA,
    InventionReviewResult,
    build_context,
    coerce_review_result,
)
from src.database.models import Invention, PatentDocument

_SEARCH_TERMS_SCHEMA = {
    "type": "object",
    "properties": {
        "korean_keywords": {"type": "array", "items": {"type": "string"}},
        "english_keywords": {"type": "array", "items": {"type": "string"}},
        "synonyms": {"type": "array", "items": {"type": "string"}},
        "materials": {"type": "array", "items": {"type": "string"}},
        "processes": {"type": "array", "items": {"type": "string"}},
        "device_terms": {"type": "array", "items": {"type": "string"}},
        "functional_phrases": {"type": "array", "items": {"type": "string"}},
        "ipc_candidates": {"type": "array", "items": {"type": "string"}},
        "cpc_candidates": {"type": "array", "items": {"type": "string"}},
        "recommended_queries": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "korean_keywords",
        "english_keywords",
        "synonyms",
        "materials",
        "processes",
        "device_terms",
        "functional_phrases",
        "ipc_candidates",
        "cpc_candidates",
        "recommended_queries",
    ],
    "additionalProperties": False,
}

_COMPARISON_SCHEMA = {
    "type": "object",
    "properties": {
        "similarities": {"type": "array", "items": {"type": "string"}},
        "differences": {"type": "array", "items": {"type": "string"}},
        "prior_patent_core": {"type": "string"},
        "possible_differentiators": {"type": "array", "items": {"type": "string"}},
        "technical_risks": {"type": "array", "items": {"type": "string"}},
        "additional_search_terms": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer"},
    },
    "required": [
        "similarities",
        "differences",
        "prior_patent_core",
        "possible_differentiators",
        "technical_risks",
        "additional_search_terms",
        "confidence",
    ],
    "additionalProperties": False,
}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        if not api_key:
            raise AIProviderError(
                "Anthropic API 키가 설정되지 않았습니다. 설정 화면에서 "
                "ANTHROPIC_API_KEY를 등록하세요."
            )
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def _call_json(self, prompt: str, schema: dict) -> dict:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                thinking={"type": "disabled"},
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise AIProviderError(f"AI 호출에 실패했습니다: {exc}") from exc

        if response.stop_reason == "refusal":
            raise AIProviderError("AI가 이 요청을 처리할 수 없습니다 (정책상 거부).")

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except (ValueError, TypeError) as exc:
            raise AIProviderError("AI 응답을 JSON으로 해석할 수 없습니다.") from exc

    def _call_json_lenient(self, prompt: str, schema: dict) -> tuple[dict | None, str]:
        """`_call_json`과 달리 JSON 파싱 실패를 예외로 던지지 않는다.

        (파싱된 dict 또는 실패 시 None, 원문 텍스트)를 돌려준다. 네트워크/
        인증 실패나 정책 거부는 여전히 AIProviderError로 던진다 — 그건
        재시도 말고는 복구할 방법이 없어서, 애초에 결과 자체가 없기
        때문이다. 반면 "형식이 이상한 JSON"은 원문이라도 있으므로 예외
        대신 값으로 돌려주고 호출한 쪽이 사용자에게 원문을 보여줄 수
        있게 한다.
        """
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                thinking={"type": "disabled"},
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise AIProviderError(f"AI 호출에 실패했습니다: {exc}") from exc

        if response.stop_reason == "refusal":
            raise AIProviderError("AI가 이 요청을 처리할 수 없습니다 (정책상 거부).")

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text), text
        except (ValueError, TypeError):
            return None, text

    def _call_text(self, prompt: str) -> str:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                thinking={"type": "disabled"},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise AIProviderError(f"AI 호출에 실패했습니다: {exc}") from exc

        if response.stop_reason == "refusal":
            raise AIProviderError("AI가 이 요청을 처리할 수 없습니다 (정책상 거부).")

        return next((b.text for b in response.content if b.type == "text"), "").strip()

    def generate_search_terms(self, invention: Invention) -> SearchTerms:
        prompt = f"""다음 발명 아이디어를 바탕으로 선행특허 검색에 사용할 키워드를 JSON으로 생성하세요.

발명 제목: {invention.title}
최초 아이디어: {invention.original_idea}
핵심 해결 원리: {invention.core_principle or '(없음)'}
기술 분야: {invention.technical_field or '(없음)'}

한국어 키워드, 영어 키워드, 유사어, 재료명, 공정명, 장치명, 기능 중심 표현,
IPC/CPC 후보, 추천 검색어를 포함한 JSON을 반환하세요."""
        data = self._call_json(prompt, _SEARCH_TERMS_SCHEMA)
        return SearchTerms(**data)

    def translate_abstract(self, abstract: str, source_language: str) -> str:
        if not abstract:
            return ""
        prompt = (
            f"다음 특허 초록({source_language or '원문 언어 미상'})을 자연스러운 한국어로 "
            f"번역하세요. 번역문만 출력하세요.\n\n{abstract}"
        )
        return self._call_text(prompt)

    def summarize_patent(self, patent: PatentDocument) -> str:
        abstract = patent.abstract_original or ""
        if not abstract:
            return ""
        prompt = (
            f"다음 특허의 제목과 초록을 한국어로 3~4문장으로 요약하세요.\n\n"
            f"제목: {patent.title}\n초록: {abstract}"
        )
        return self._call_text(prompt)

    def compare_invention_and_patent(
        self, invention: Invention, patent: PatentDocument
    ) -> PatentComparisonDraft:
        prompt = f"""다음 내 발명 아이디어와 선행특허를 비교하여 JSON으로 초안을 작성하세요.
법적 판단이 아니라 검토를 위한 참고 초안임을 유의하세요.

[내 발명]
제목: {invention.title}
최초 아이디어: {invention.original_idea}
핵심 해결 원리: {invention.core_principle or '(없음)'}
해결하려는 문제: {invention.problem_to_solve or '(없음)'}

[선행특허]
제목: {patent.title}
초록: {patent.abstract_original or '(없음)'}

similarities(같은 점), differences(다른 점), prior_patent_core(선행특허 핵심 요약),
possible_differentiators(차별화 아이디어), technical_risks(기술적 위험),
additional_search_terms(추가 검색어), confidence(0~100 신뢰도)를 포함한 JSON을
반환하세요."""
        data = self._call_json(prompt, _COMPARISON_SCHEMA)
        return PatentComparisonDraft(**data)

    def review_invention(self, invention: Invention, kind: str) -> InventionReviewResult:
        instruction = PROMPT_INSTRUCTIONS.get(kind, "다음 발명을 검토하세요.")
        prompt = (
            f"{build_context(invention)}\n\n"
            f"요청: {instruction}\n\n"
            "problem, existing_method, limitations, core_idea, working_principle, "
            "differentiation, expected_effects, implementation, experiment_plan, "
            "patent_keywords(문자열 배열), findings 키를 모두 포함한 JSON으로 답하세요. "
            "요청과 직접 관련된 항목만 채우고 나머지는 빈 문자열 또는 빈 배열로 "
            "두되, 요청의 핵심 결론은 findings에 자유롭게 정리하세요. 한국어로 "
            "답하고, 발명 노트에 바로 옮겨 적을 수 있는 간결한 문장을 쓰세요. "
            "법적 판단(신규성/진보성 등)이 아닌 검토 참고용임을 유의하세요."
        )
        data, raw_text = self._call_json_lenient(prompt, STRUCTURED_RESULT_SCHEMA)
        return coerce_review_result(data, raw_text)
