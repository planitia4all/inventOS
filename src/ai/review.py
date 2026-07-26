"""발명 상세 화면 'AI로 검토하기'에서 쓰는 12가지 검토 종류를 한 곳에 정의한다.

버튼 라벨, 그룹 묶음, 반영 시 기본으로 채울 발명 필드, AI에게 보낼 지시문을
전부 여기서 관리한다 — Mock/Anthropic Provider와 AIResultService가 이 모듈을
공통으로 참조하므로, 새 검토 종류를 추가할 때 여기 한 곳만 고치면 된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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

# 12종 검토 전부가 공유하는 하나의 구조화 응답 형식. Mock과 실제 AI
# Provider(Anthropic 등)가 항상 같은 모양의 결과를 반환하도록 통일해 두면,
# "일부만 반영"이 어느 검토 결과에서든 같은 방식으로 항목을 골라 쓸 수 있고
# 파싱/오류 처리 코드도 하나로 유지할 수 있다.
@dataclass
class InventionReviewResult:
    problem: str = ""
    existing_method: str = ""
    limitations: str = ""
    core_idea: str = ""
    working_principle: str = ""
    differentiation: str = ""
    expected_effects: str = ""
    implementation: str = ""
    experiment_plan: str = ""
    patent_keywords: list[str] = field(default_factory=list)
    # 9개 항목에 딱 들어맞지 않는 자유 서술(부족한 부분, 애매한 점, 파생
    # 아이디어 제안 등 분석/비평형 검토의 주 결과가 여기 담긴다).
    findings: str = ""
    # AI가 실제로 반환한 원문. 구조화 파싱이 실패해도 항상 보존한다.
    raw_text: str = ""
    # 파싱에 문제가 있었으면(JSON이 아니거나 필드가 누락됨) 이유를 담는다.
    # 문제가 없으면 None.
    parse_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "problem": self.problem,
            "existing_method": self.existing_method,
            "limitations": self.limitations,
            "core_idea": self.core_idea,
            "working_principle": self.working_principle,
            "differentiation": self.differentiation,
            "expected_effects": self.expected_effects,
            "implementation": self.implementation,
            "experiment_plan": self.experiment_plan,
            "patent_keywords": self.patent_keywords,
            "findings": self.findings,
        }


# InventionAIResult.structured_content(JSON)에 담기는 키 -> 스키마 기본값.
# Provider가 일부 키를 빠뜨려도(JSON 파싱 실패 처리) 여기서 기본값을 채운다.
STRUCTURED_RESULT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "problem": {"type": "string"},
        "existing_method": {"type": "string"},
        "limitations": {"type": "string"},
        "core_idea": {"type": "string"},
        "working_principle": {"type": "string"},
        "differentiation": {"type": "string"},
        "expected_effects": {"type": "string"},
        "implementation": {"type": "string"},
        "experiment_plan": {"type": "string"},
        "patent_keywords": {"type": "array", "items": {"type": "string"}},
        "findings": {"type": "string"},
    },
    "required": [
        "problem",
        "existing_method",
        "limitations",
        "core_idea",
        "working_principle",
        "differentiation",
        "expected_effects",
        "implementation",
        "experiment_plan",
        "patent_keywords",
        "findings",
    ],
    "additionalProperties": False,
}

# 발명 필드(항목별 반영 대상) -> 구조화 응답의 키. "review_notes"(특허
# 검색어)만 예외적으로 findings/patent_keywords 둘 다에서 값을 가져온다
# (apply_structured_value 참고).
STRUCTURED_FIELD_MAP: dict[str, str] = {
    "problem_to_solve": "problem",
    "conventional_method": "existing_method",
    "conventional_problems": "limitations",
    "core_principle": "core_idea",
    "operating_principle": "working_principle",
    "differentiation": "differentiation",
    "expected_effects": "expected_effects",
    "implementation_method": "implementation",
    "experiment_notes": "experiment_plan",
    "review_notes": "findings",
}


def coerce_review_result(data: object, raw_text: str) -> InventionReviewResult:
    """Provider가 반환한 원시 데이터를 안전하게 InventionReviewResult로 바꾼다.

    JSON 파싱 자체가 실패한 경우(Provider가 문자열을 넘김) 또는 dict가
    아닌 경우, 누락된 키가 있는 경우 전부 예외 없이 처리하고 원문은 항상
    보존한다 — AI가 형식에 안 맞는 응답을 줘도 프로그램이 죽지 않는다.
    """
    if not isinstance(data, dict):
        return InventionReviewResult(raw_text=raw_text, findings=raw_text, parse_error="AI 응답이 JSON 객체 형식이 아닙니다.")

    missing = [
        key
        for key in STRUCTURED_RESULT_SCHEMA["required"]
        if key not in data
    ]
    parse_error = None
    if missing:
        parse_error = f"AI 응답에 다음 항목이 없어 빈 값으로 채웠습니다: {', '.join(missing)}"

    def _text(key: str) -> str:
        value = data.get(key, "")
        return value if isinstance(value, str) else ("" if value is None else str(value))

    keywords = data.get("patent_keywords", [])
    if not isinstance(keywords, list):
        keywords = [str(keywords)] if keywords else []
        parse_error = (parse_error + " " if parse_error else "") + "patent_keywords 형식이 올바르지 않았습니다."
    keywords = [str(k) for k in keywords if k]

    return InventionReviewResult(
        problem=_text("problem"),
        existing_method=_text("existing_method"),
        limitations=_text("limitations"),
        core_idea=_text("core_idea"),
        working_principle=_text("working_principle"),
        differentiation=_text("differentiation"),
        expected_effects=_text("expected_effects"),
        implementation=_text("implementation"),
        experiment_plan=_text("experiment_plan"),
        patent_keywords=keywords,
        findings=_text("findings"),
        raw_text=raw_text,
        parse_error=parse_error,
    )


def render_review_result(result: InventionReviewResult) -> str:
    """구조화 결과를 AI 검토 결과 카드에 보여줄 사람이 읽기 좋은 텍스트로 바꾼다."""
    labels = [
        ("findings", "검토 내용"),
        ("problem", "해결하려는 문제"),
        ("existing_method", "기존 방식"),
        ("limitations", "기존 방식의 한계"),
        ("core_idea", "핵심 아이디어"),
        ("working_principle", "작동 원리"),
        ("differentiation", "차별점"),
        ("expected_effects", "예상 효과"),
        ("implementation", "구현 방법"),
        ("experiment_plan", "실험 계획"),
    ]
    lines = []
    for key, label in labels:
        value = getattr(result, key, "")
        if value and value.strip():
            lines.append(f"**{label}**: {value.strip()}")
    if result.patent_keywords:
        lines.append(f"**특허 검색어**: {', '.join(result.patent_keywords)}")
    if not lines:
        # 구조화된 값이 하나도 없으면(예: 파싱 실패) 원문을 그대로 보여준다.
        return result.raw_text or "(빈 응답)"
    return "\n\n".join(lines)


def apply_structured_value(result_dict: dict | None, invention_field: str) -> str:
    """`InventionAIResult.structured_content`에서 특정 발명 필드에 대응하는 값을 꺼낸다.

    구조화 데이터가 없거나 대응 값이 비어 있으면 빈 문자열을 돌려준다 —
    호출한 쪽(AIResultService.apply)이 이 경우 raw content로 대체한다.
    """
    if not result_dict:
        return ""
    key = STRUCTURED_FIELD_MAP.get(invention_field)
    if key is None:
        return ""
    value = (result_dict.get(key) or "").strip() if isinstance(result_dict.get(key), str) else ""
    if not value and key == "findings":
        keywords = result_dict.get("patent_keywords") or []
        if keywords:
            value = ", ".join(keywords)
    return value


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
    for field_name, label in _CONTEXT_FIELDS:
        value = (getattr(invention, field_name, None) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)
