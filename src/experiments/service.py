"""실험 기록 서비스.

실험은 발명 본문과 동등하게 중요한 1급 데이터다. 발명 하나에 여러 실험이
쌓일 수 있고, 각 실험에는 사진/동영상을 따로 붙일 수 있다.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Experiment
from src.experiments.schemas import ExperimentInput
from src.search.fts import SearchIndexService
from src.timeline.service import TimelineService


def draft_text_from_experiment(experiment: Experiment) -> str:
    """실험 기록을 새 파생 아이디어의 '초안'으로 바꾼다.

    그대로 복사해서 저장하지 않는다 — 사용자가 확인하고 다듬을 수 있도록
    캡처 화면의 메모 입력칸에 미리 채워 넣기만 하는 용도다.
    """
    lines = ["[실험 기록에서 파생된 아이디어 — 내용을 확인하고 다듬어 주세요]"]
    if experiment.experiment_date:
        lines.append(f"실험 날짜: {experiment.experiment_date.isoformat()}")
    if experiment.conditions:
        lines.append(f"조건: {experiment.conditions}")
    if experiment.results:
        lines.append(f"결과: {experiment.results}")
    if experiment.failure_reason:
        lines.append(f"실패 원인: {experiment.failure_reason}")
    if experiment.improvement_ideas:
        lines.append(f"개선 아이디어: {experiment.improvement_ideas}")
    return "\n".join(lines)


class ExperimentService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, invention_id: str, data: ExperimentInput) -> Experiment:
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        experiment = Experiment(
            invention_id=invention_id,
            experiment_date=data.experiment_date,
            conditions=data.conditions,
            results=data.results,
            failure_reason=data.failure_reason,
            improvement_ideas=data.improvement_ideas,
        )
        self.session.add(experiment)
        self.session.flush()

        TimelineService(self.session).log(
            invention_id,
            "experiment_recorded",
            description=data.results or data.conditions or "실험 기록 추가",
        )
        SearchIndexService(self.session).reindex_invention(invention_id)
        return experiment

    def update(self, experiment_id: str, data: ExperimentInput) -> Experiment:
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        experiment = self._require(experiment_id)
        experiment.experiment_date = data.experiment_date
        experiment.conditions = data.conditions
        experiment.results = data.results
        experiment.failure_reason = data.failure_reason
        experiment.improvement_ideas = data.improvement_ideas
        self.session.flush()
        TimelineService(self.session).log(
            experiment.invention_id,
            "experiment_updated",
            description=data.results or data.conditions or "실험 기록 수정",
        )
        SearchIndexService(self.session).reindex_invention(experiment.invention_id)
        return experiment

    def get(self, experiment_id: str) -> Experiment | None:
        return self.session.get(Experiment, experiment_id)

    def list_for_invention(self, invention_id: str) -> list[Experiment]:
        stmt = (
            select(Experiment)
            .where(Experiment.invention_id == invention_id)
            .order_by(Experiment.experiment_date.desc().nulls_last(), Experiment.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def delete(self, experiment_id: str) -> None:
        experiment = self._require(experiment_id)
        invention_id = experiment.invention_id
        description = experiment.results or experiment.conditions or "실험 기록 삭제"
        self.session.delete(experiment)
        self.session.flush()
        TimelineService(self.session).log(
            invention_id, "experiment_deleted", description=description
        )
        SearchIndexService(self.session).reindex_invention(invention_id)

    def _require(self, experiment_id: str) -> Experiment:
        experiment = self.session.get(Experiment, experiment_id)
        if experiment is None:
            raise LookupError(f"실험 기록을 찾을 수 없습니다: {experiment_id}")
        return experiment
