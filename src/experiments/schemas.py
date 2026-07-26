"""실험 기록 입력 DTO."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class ExperimentInput:
    experiment_date: date | None = None
    conditions: str | None = None
    results: str | None = None
    failure_reason: str | None = None
    improvement_ideas: str | None = None

    def validate(self) -> list[str]:
        if not any(
            (self.conditions, self.results, self.failure_reason, self.improvement_ideas)
        ):
            return ["조건, 결과, 실패 원인, 개선 아이디어 중 하나는 입력하세요."]
        return []
