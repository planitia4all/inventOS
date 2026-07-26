"""발명 관련 입출력 DTO."""
from __future__ import annotations

from dataclasses import dataclass, field

# 자유 문자열 컬럼(DB ENUM 아님)이라 새 상태를 코드 몇 줄로 추가할 수 있다.
# 목록은 추천값일 뿐이며 강제되지 않는다 — 옛 데이터에 이 목록에 없는 값이
# 남아 있어도(마이그레이션 이전 값 등) 정상적으로 표시·저장된다.
STATUS_VALUES = [
    "아이디어",       # Idea
    "검토 중",         # Reviewing
    "실험 중",         # Experiment
    "특허 검토",       # Patent
    "개발 중",         # Development
    "보관됨",         # Archived (목록에서 숨기는 is_archived 플래그와는 별개로,
                      # '이 발명 라인은 종료됐다'는 상태 값으로도 쓸 수 있다)
]

DEFAULT_STATUS = STATUS_VALUES[0]

# 예전 상태값을 새 6종 상태값으로 옮기기 위한 매핑 (DB 마이그레이션에서 사용)
LEGACY_STATUS_MIGRATION: dict[str, str] = {
    "선행기술 조사 중": "검토 중",
    "차별화 검토 중": "검토 중",
    "시험 검토 중": "실험 중",
    "보류": "검토 중",
    "출원 검토": "특허 검토",
    "완료": "개발 중",
}

# 상세 화면 항목의 라벨과 도움말. 전문 용어 대신 쉬운 표현을 쓰고,
# 특허 용어가 필요한 경우에만 도움말로 덧붙인다.
FIELD_LABELS: dict[str, tuple[str, str]] = {
    "refined_content": ("정리된 발명 내용", "원본 메모를 다듬어 정리한 내용"),
    "problem_to_solve": ("해결하려는 문제", "이 아이디어가 없앨 불편함이나 문제"),
    "conventional_method": ("기존 방식 또는 기존 기술", "지금까지 이 문제를 해결하던 방법"),
    "conventional_problems": ("기존 방식의 한계", "기존 방법이 잘 안 되는 이유"),
    "core_principle": ("핵심 아이디어", "이 발명에서 가장 중요한 한 가지"),
    "key_components": ("주요 구성 요소", "아이디어를 이루는 부품이나 단계"),
    "operating_principle": ("작동 원리", "어떤 순서로 어떻게 동작하는지"),
    "implementation_method": ("구현 방법", "실제로 만들려면 무엇이 필요한지"),
    "technical_barriers": ("예상되는 어려움", "만들 때 걸림돌이 될 만한 것"),
    "differentiation": (
        "기존 기술과 다른 점",
        "특허에서 말하는 '신규성 검토'에 해당합니다. 기존 기술과 무엇이 다른지 적어두세요.",
    ),
    "expected_effects": ("예상 효과", "적용했을 때 좋아지는 점"),
    "applicable_industries": ("적용 가능 분야", "어디에 쓸 수 있는지"),
    "experiment_notes": ("실험 기록", "시험해 본 내용과 결과"),
    "review_notes": ("추가 검토 사항", "나중에 더 알아봐야 할 것"),
    "technical_field": ("기술 분야", "어떤 분야의 기술인지"),
    "inventor_name": ("작성자", ""),
}

# 상세 화면에서 버튼을 눌렀을 때 펼쳐지는 묶음.
# (버튼 이름, 설명, 필드 목록)
DETAIL_GROUPS: list[tuple[str, str, list[str]]] = [
    (
        "발명 내용 구체화",
        "떠오른 메모를 발명 노트 형태로 정리합니다.",
        [
            "refined_content",
            "problem_to_solve",
            "conventional_method",
            "conventional_problems",
            "core_principle",
        ],
    ),
    (
        "기술 내용 추가",
        "무엇으로 어떻게 만드는지 적어둡니다.",
        [
            "key_components",
            "operating_principle",
            "implementation_method",
            "technical_barriers",
        ],
    ),
    (
        "차별점 정리",
        "기존 기술과 무엇이 다른지 정리합니다.",
        ["differentiation", "expected_effects", "applicable_industries"],
    ),
    ("실험 기록 추가", "시험해 본 내용과 결과를 남깁니다.", ["experiment_notes"]),
    ("검토 내용 추가", "더 알아봐야 할 것을 적어둡니다.", ["review_notes"]),
]


@dataclass
class QuickIdeaInput:
    """홈 화면의 빠른 기록 입력.

    필수 항목은 메모 하나뿐이다. 제목을 비워두면 서비스가 자동 생성한다.
    """

    memo: str
    title: str = ""
    keywords: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        if not self.memo or not self.memo.strip():
            return ["아이디어 내용을 입력하세요."]
        return []


@dataclass
class InventionInput:
    """발명 상세 화면에서 넘어오는 입력.

    필수 항목은 original_idea(원본 아이디어) 하나뿐이다.
    제목을 비워두면 서비스가 메모 첫 문장이나 날짜로 자동 생성한다.
    """

    original_idea: str
    title: str = ""
    technical_field: str | None = None
    refined_content: str | None = None
    problem_to_solve: str | None = None
    conventional_method: str | None = None
    conventional_problems: str | None = None
    core_principle: str | None = None
    key_components: str | None = None
    operating_principle: str | None = None
    differentiation: str | None = None
    expected_effects: str | None = None
    technical_barriers: str | None = None
    applicable_industries: str | None = None
    implementation_method: str | None = None
    experiment_notes: str | None = None
    review_notes: str | None = None
    keywords: list[str] = field(default_factory=list)
    inventor_name: str | None = None
    status: str = "아이디어"

    def validate(self) -> list[str]:
        if not self.original_idea or not self.original_idea.strip():
            return ["아이디어 내용을 입력하세요."]
        return []
