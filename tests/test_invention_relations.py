"""파생 아이디어(부모-자식) 관계 검증."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.config.settings import Settings
from src.database.models import Invention
from src.experiments.schemas import ExperimentInput
from src.experiments.service import ExperimentService, draft_text_from_experiment
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService


def test_create_child_links_to_parent(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    child = service.create_child(parent.id, QuickIdeaInput(memo="Graphene Fiber 방식"))

    assert child.parent_invention_id == parent.id


def test_list_children_returns_multiple_derived_ideas(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    child1 = service.create_child(parent.id, QuickIdeaInput(memo="Graphene Fiber 방식"))
    child2 = service.create_child(parent.id, QuickIdeaInput(memo="Laser Hybrid 방식"))

    children = service.list_children(parent.id)
    assert {c.id for c in children} == {child1.id, child2.id}


def test_create_child_requires_existing_parent(db_session):
    service = InventionService(db_session)
    with pytest.raises(LookupError):
        service.create_child("no-such-id", QuickIdeaInput(memo="파생 아이디어"))


def test_create_child_logs_timeline_events_on_both_sides(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    child = service.create_child(parent.id, QuickIdeaInput(memo="Graphene Heating 방식"))

    parent_events = [e.event_type for e in service.list_timeline(parent.id)]
    child_events = [e.event_type for e in service.list_timeline(child.id)]

    assert "derived_child_created" in parent_events
    assert "derived_from_parent" in child_events


def test_no_children_returns_empty_list(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="파생 없음"))
    assert service.list_children(parent.id) == []


def test_deleting_parent_preserves_children(db_session):
    """부모를 지워도 파생된 자식 아이디어 자체는 사라지면 안 된다."""
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="부모 아이디어"))
    child = service.create_child(parent.id, QuickIdeaInput(memo="자식 아이디어"))

    service.delete(parent.id)

    refreshed = service.get(child.id)
    assert refreshed is not None
    assert refreshed.parent_invention_id is None


def test_derivation_chain_cannot_form_a_cycle(db_session):
    """parent_invention_id는 create_child()에서 항상 새로 만든 자식에만
    설정되므로(기존 발명을 나중에 재부모화하는 기능 자체가 없음) 구조적으로
    순환이 생길 수 없다. 3단계 파생 체인으로 이를 문서화해 둔다."""
    service = InventionService(db_session)
    a = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    b = service.create_child(a.id, QuickIdeaInput(memo="Graphene Fiber 방식"))
    c = service.create_child(b.id, QuickIdeaInput(memo="Laser Hybrid 방식"))

    chain = [c.id]
    current = c
    while current.parent_invention_id:
        current = service.get(current.parent_invention_id)
        assert current.id not in chain, "순환 관계가 발생했습니다"
        chain.append(current.id)

    assert chain == [c.id, b.id, a.id]


def test_create_child_stores_derivation_reason(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    child = service.create_child(
        parent.id,
        QuickIdeaInput(memo="Ceramic 접합 방식"),
        derivation_reason="재료 변경",
    )
    assert child.derivation_reason == "재료 변경"


def test_create_child_copies_selected_fields_only(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    InventionService(db_session).update_fields(
        parent.id,
        problem_to_solve="접합 강도 부족",
        core_principle="레이저로 국소 가열",
        operating_principle="펄스 레이저를 순차 조사한다",
    )

    child = service.create_child(
        parent.id,
        QuickIdeaInput(memo="Laser Hybrid 방식"),
        copy_fields=["problem_to_solve", "core_principle"],
    )

    assert child.problem_to_solve == "접합 강도 부족"
    assert child.core_principle == "레이저로 국소 가열"
    assert not (child.operating_principle or "").strip()


def test_create_child_default_copies_nothing(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    InventionService(db_session).update_fields(parent.id, problem_to_solve="접합 강도 부족")

    child = service.create_child(parent.id, QuickIdeaInput(memo="관계만 연결"))

    assert child.parent_invention_id == parent.id
    assert not (child.problem_to_solve or "").strip()


def test_create_child_rejects_unknown_copy_field(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    with pytest.raises(ValueError):
        service.create_child(
            parent.id,
            QuickIdeaInput(memo="잘못된 파생"),
            copy_fields=["no_such_field"],
        )


def test_create_child_copies_tags_when_requested(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합", keywords=["배터리", "AI"]))

    child = service.create_child(
        parent.id, QuickIdeaInput(memo="파생"), copy_tags=True
    )

    assert set(service.tags.tag_names(child.id)) == {"배터리", "AI"}


def test_create_child_does_not_copy_tags_by_default(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합", keywords=["배터리"]))

    child = service.create_child(parent.id, QuickIdeaInput(memo="파생"))

    assert service.tags.tag_names(child.id) == []


def test_create_child_copies_attachments_when_requested(db_session, tmp_path):
    from src.attachments.service import AttachmentService

    settings = Settings(data_dir=tmp_path)
    service = InventionService(db_session, settings=settings)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    AttachmentService(db_session, settings=settings).save(
        parent.id, "photo.png", b"fake-bytes"
    )

    child = service.create_child(
        parent.id, QuickIdeaInput(memo="파생"), copy_attachments=True
    )

    copied = AttachmentService(db_session, settings=settings).list_for_invention(child.id)
    assert len(copied) == 1
    assert copied[0].original_filename == "photo.png"
    assert copied[0].invention_id == child.id


def test_create_child_from_experiment_links_source(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    experiment = ExperimentService(db_session).create(
        parent.id, ExperimentInput(results="접합 강도 20% 향상")
    )

    child = service.create_child(
        parent.id,
        QuickIdeaInput(memo=draft_text_from_experiment(experiment)),
        derivation_reason="실험 결과에서 파생",
        source_experiment_id=experiment.id,
    )

    assert child.source_experiment_id == experiment.id
    assert "접합 강도 20% 향상" in child.original_idea


def test_draft_text_from_experiment_does_not_touch_experiment(db_session):
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="원본"))
    experiment = ExperimentService(db_session).create(
        invention.id, ExperimentInput(conditions="200도", results="성공")
    )

    text = draft_text_from_experiment(experiment)

    assert "200도" in text
    assert "성공" in text
    assert experiment.conditions == "200도"


def test_create_child_logs_derivation_reason_in_timeline_meta(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    child = service.create_child(
        parent.id,
        QuickIdeaInput(memo="파생"),
        derivation_reason="성능 개선",
    )

    parent_events = service.list_timeline(parent.id)
    child_events = service.list_timeline(child.id)
    derived_created = next(e for e in parent_events if e.event_type == "derived_child_created")
    derived_from = next(e for e in child_events if e.event_type == "derived_from_parent")

    assert derived_created.meta_json["derivation_reason"] == "성능 개선"
    assert derived_from.meta_json["derivation_reason"] == "성능 개선"
    assert "성능 개선" in derived_created.description
    assert "성능 개선" in derived_from.description


def test_create_child_transaction_rolls_back_on_invalid_copy_field(db_session):
    service = InventionService(db_session)
    parent = service.quick_create(QuickIdeaInput(memo="Separator 접합"))
    before = db_session.scalar(select(func.count()).select_from(Invention))

    with pytest.raises(ValueError):
        with db_session.begin_nested():
            service.create_child(
                parent.id,
                QuickIdeaInput(memo="잘못된 파생"),
                copy_fields=["no_such_field"],
            )

    after = db_session.scalar(select(func.count()).select_from(Invention))
    assert after == before
