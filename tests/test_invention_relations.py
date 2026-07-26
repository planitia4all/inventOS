"""파생 아이디어(부모-자식) 관계 검증. UI에는 아직 노출하지 않지만
DB/서비스 계층은 미리 준비해 둔다."""
from __future__ import annotations

import pytest

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
