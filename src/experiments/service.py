"""실험 기록 서비스.

실험은 발명 본문과 동등하게 중요한 1급 데이터다. 발명 하나에 여러 실험이
쌓일 수 있고, 각 실험에는 사진/동영상을 따로 붙일 수 있다.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Experiment
from src.experiments.schemas import ExperimentInput
from src.timeline.service import TimelineService


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
        return experiment

    def list_for_invention(self, invention_id: str) -> list[Experiment]:
        stmt = (
            select(Experiment)
            .where(Experiment.invention_id == invention_id)
            .order_by(Experiment.experiment_date.desc().nulls_last(), Experiment.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def delete(self, experiment_id: str) -> None:
        self.session.delete(self._require(experiment_id))

    def _require(self, experiment_id: str) -> Experiment:
        experiment = self.session.get(Experiment, experiment_id)
        if experiment is None:
            raise LookupError(f"실험 기록을 찾을 수 없습니다: {experiment_id}")
        return experiment
