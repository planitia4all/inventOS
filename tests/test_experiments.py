"""실험 기록 서비스 검증."""
from __future__ import annotations

from datetime import date

import pytest

from src.experiments.schemas import ExperimentInput
from src.experiments.service import ExperimentService
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService


def make_invention(session):
    return InventionService(session).quick_create(QuickIdeaInput(memo="실험 테스트용"))


def test_create_experiment(db_session):
    invention = make_invention(db_session)
    service = ExperimentService(db_session)
    exp = service.create(
        invention.id,
        ExperimentInput(
            experiment_date=date(2026, 7, 27),
            conditions="온도 200도",
            results="접합 성공",
            failure_reason=None,
            improvement_ideas="온도를 더 낮춰본다",
        ),
    )
    assert exp.conditions == "온도 200도"
    assert exp.invention_id == invention.id


def test_create_requires_some_content(db_session):
    invention = make_invention(db_session)
    with pytest.raises(ValueError):
        ExperimentService(db_session).create(invention.id, ExperimentInput())


def test_list_for_invention_orders_by_date_desc(db_session):
    invention = make_invention(db_session)
    service = ExperimentService(db_session)
    service.create(
        invention.id, ExperimentInput(experiment_date=date(2026, 7, 1), results="1차")
    )
    service.create(
        invention.id, ExperimentInput(experiment_date=date(2026, 7, 20), results="2차")
    )

    experiments = service.list_for_invention(invention.id)
    assert [e.results for e in experiments] == ["2차", "1차"]


def test_update_experiment(db_session):
    invention = make_invention(db_session)
    service = ExperimentService(db_session)
    exp = service.create(invention.id, ExperimentInput(results="1차 결과"))

    updated = service.update(exp.id, ExperimentInput(results="수정된 결과"))
    assert updated.results == "수정된 결과"


def test_delete_experiment(db_session):
    invention = make_invention(db_session)
    service = ExperimentService(db_session)
    exp = service.create(invention.id, ExperimentInput(results="삭제될 실험"))
    service.delete(exp.id)

    assert service.list_for_invention(invention.id) == []


def test_create_experiment_logs_timeline_event(db_session):
    invention = make_invention(db_session)
    ExperimentService(db_session).create(
        invention.id, ExperimentInput(results="실험 결과")
    )

    types = [e.event_type for e in InventionService(db_session).list_timeline(invention.id)]
    assert "experiment_recorded" in types
