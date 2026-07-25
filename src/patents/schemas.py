"""특허 관련 입출력 DTO."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

IMPORTANCE_VALUES = ["매우 중요", "중요", "참고", "관련 낮음"]
REVIEW_STATUS_VALUES = ["미검토", "검토 중", "검토 완료", "제외"]


@dataclass
class ManualPatentInput:
    """수동 특허 등록 입력 (요구사항 8절)."""

    title: str
    publication_number: str
    applicant: str | None = None
    application_number: str | None = None
    priority_date: date | None = None
    country_code: str | None = None
    abstract_original: str | None = None
    source_url: str | None = None
    note: str | None = None

    def validate(self) -> list[str]:
        errors = []
        if not self.title or not self.title.strip():
            errors.append("발명의 명칭은 필수입니다.")
        if not self.publication_number or not self.publication_number.strip():
            errors.append("공개번호는 필수입니다.")
        return errors


@dataclass
class ComparisonInput:
    """발명-특허 비교 기록 (요구사항 4.4절)."""

    similarities: str | None = None
    differences: str | None = None
    patent_solved_problem: str | None = None
    unsolved_problem: str | None = None
    differentiation_ideas: str | None = None
    additional_research: str | None = None
    user_notes: str | None = None
    importance: str = "참고"
    review_status: str = "미검토"
