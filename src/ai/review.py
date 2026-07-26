"""발명 상세 화면 'AI로 검토하기'에서 쓰는 12가지 검토 종류를 한 곳에 정의한다.

버튼 라벨, 그룹 묶음, 반영 시 기본으로 채울 발명 필드, AI에게 보낼 지시문을
전부 여기서 관리한다 — Mock/Anthropic Provider와 AIResultService가 이 모듈을
공통으로 참조하므로, 새 검토 종류를 추가할 때 여기 한 곳만 고치면 된다.
"""
from __future__ import annotations

from src.database.models import Invention

# (그룹 이름, [(kind, 버튼 라벨), ...]) — 발명 상세 화면에서 이 순서 그대로
# 3개 묶음으로 보여준다. 모바일에서도 한 화면에 12개를 다 늘어놓지 않기
# 위한 구성이다.
REVIEW_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "아이디어 정리",
        [
            ("summary", "아이디어 정리"),
            ("problem_extraction", "문제점 추출"),
            ("conventional_limits", "기존 방식의 한계 정리"),
            ("core_principle_summary", "핵심 원리 정리"),
        ],
    ),
    (
        "기술 검토",
        [
            ("gap_analysis", "부족한 부분 찾기"),
            ("ambiguity_check", "기술적 애매점 찾기"),
            ("feasibility_review", "실현 가능성 검토"),
            ("implementation_suggestion", "구현 방법 제안"),
        ],
    ),
    (
        "발전시키기",
        [
            ("differentiation", "차별점 찾기"),
            ("experiment_plan", "실험 계획 제안"),
            ("derived_idea", "파생 아이디어 제안"),
            ("patent_search_terms", "특허 검색어 생성"),
        ],
    ),
]

REVIEW_KIND_LABELS: dict[str, str] = {
    kind: label for _, items in REVIEW_GROUPS for kind, label in items
}

# 버튼을 눌러 결과를 만들었을 때 "전체 반영"이 채워 넣을 기본 발명 필드.
REVIEW_DEFAULT_FIELD: dict[str, str] = {
    "summary": "refined_content",
    "problem_extraction": "problem_to_solve",
    "conventional_limits": "conventional_problems",
    "core_principle_summary": "core_principle",
    "gap_analysis": "review_notes",
    "ambiguity_check": "review_notes",
    "feasibility_review": "technical_barriers",
    "implementation_suggestion": "implementation_method",
    "differentiation": "differentiation",
    "experiment_plan": "experiment_notes",
    "derived_idea": "review_notes",
    "patent_search_terms": "review_notes",
}

# "일부만 반영"에서 사용자가 고를 수 있는 항목 단위 목록 (문단 단위 선택은
# 다음 단계로 미루고, 우선 항목 단위로 구현한다).
PARTIAL_APPLY_FIELDS: list[tuple[str, str]] = [
    ("problem_to_solve", "해결하려는 문제"),
    ("conventional_method", "기존 방식"),
    ("conventional_problems", "기존 방식의 한계"),
    ("core_principle", "핵심 아이디어"),
    ("operating_principle", "작동 원리"),
    ("differentiation", "차별점"),
    ("expected_effects", "예상 효과"),
    ("implementation_method", "구현 방법"),
    ("experiment_notes", "실험 계획"),
    ("review_notes", "특허 검색어"),
]

PARTIAL_APPLY_FIELD_LABELS: dict[str, str] = dict(PARTIAL_APPLY_FIELDS)

# AI에게 보낼 지시문. 발명 배경(build_context)에 이어 붙여서 하나의
# 프롬프트를 만든다.
PROMPT_INSTRUCTIONS: dict[str, str] = {
    "summary": "이 아이디어를 발명 노트 형식으로, 이해하기 쉽게 정리하세요.",
    "problem_extraction": "이 아이디어가 해결하려는 핵심 문제를 구체적으로 추출하세요.",
    "conventional_limits": "이 문제를 지금까지 해결해 온 기존 방식과 그 한계를 정리하세요.",
    "core_principle_summary": "이 발명의 핵심 원리를 한 문단으로 명확하게 정리하세요.",
    "gap_analysis": "이 아이디어 설명에서 아직 부족하거나 빠진 부분을 찾아 나열하세요.",
    "ambiguity_check": (
        "이 아이디어 설명에서 기술적으로 모호하거나 애매한 부분을 찾아 "
        "질문 형태로 나열하세요."
    ),
    "feasibility_review": (
        "이 아이디어를 실제로 구현할 수 있을지 실현 가능성 관점에서 검토하고, "
        "예상되는 어려움을 정리하세요."
    ),
    "implementation_suggestion": "이 아이디어를 실제로 구현하는 구체적인 방법을 제안하세요.",
    "differentiation": "이 아이디어가 기존 기술과 어떻게 다른지 차별점을 정리하세요.",
    "experiment_plan": (
        "이 아이디어를 검증하기 위한 실험 계획(조건, 측정 방법, 예상 결과)을 제안하세요."
    ),
    "derived_idea": "이 아이디어에서 파생될 수 있는 새로운 아이디어를 2~3개 제안하세요.",
    "patent_search_terms": (
        "이 아이디어에 대한 선행특허를 검색할 때 사용할 한국어/영어 검색어를 나열하세요."
    ),
}

# 배경 설명에 포함할 발명 필드 (있는 것만 골라서 보여준다).
_CONTEXT_FIELDS: list[tuple[str, str]] = [
    ("problem_to_solve", "해결하려는 문제"),
    ("core_principle", "핵심 아이디어"),
    ("operating_principle", "작동 원리"),
    ("differentiation", "차별점"),
]


def build_context(invention: Invention) -> str:
    """AI에게 보낼 발명 배경 설명 텍스트. InventionAIResult.input_snapshot으로도 저장한다."""
    lines = [f"발명 제목: {invention.title}", f"최초 아이디어: {invention.original_idea}"]
    for field, label in _CONTEXT_FIELDS:
        value = (getattr(invention, field, None) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)
