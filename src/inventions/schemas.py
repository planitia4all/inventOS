"""발명 관련 입출력 DTO."""
from __future__ import annotations

from dataclasses import dataclass, field

STATUS_VALUES = [
    "아이디어",
    "선행기술 조사 중",
    "차별화 검토 중",
    "시험 검토 중",
    "보류",
    "출원 검토",
    "완료",
]


@dataclass
class InventionInput:
    """발명 작성 화면에서 넘어오는 입력.

    필수 항목은 title, original_idea 뿐이며 나머지는 이후 보완 가능하다.
    """

    title: str
    original_idea: str
    technical_field: str | None = None
    problem_to_solve: str | None = None
    conventional_method: str | None = None
    conventional_problems: str | None = None
    core_principle: str | None = None
    expected_effects: str | None = None
    technical_barriers: str | None = None
    applicable_industries: str | None = None
    keywords: list[str] = field(default_factory=list)
    inventor_name: str | None = None
    status: str = "아이디어"

    def validate(self) -> list[str]:
        errors = []
        if not self.title or not self.title.strip():
            errors.append("발명 제목은 필수입니다.")
        if not self.original_idea or not self.original_idea.strip():
            errors.append("최초 아이디어는 필수입니다.")
        return errors
