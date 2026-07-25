from __future__ import annotations

import pytest

from src.inventions.schemas import InventionInput
from src.inventions.service import InventionService


def make_input(**overrides) -> InventionInput:
    data = dict(title="유리기판 관통전극", original_idea="금속 핀을 먼저 배열한다.")
    data.update(overrides)
    return InventionInput(**data)


def test_create_invention_requires_title_and_idea(db_session):
    service = InventionService(db_session)
    with pytest.raises(ValueError):
        service.create(InventionInput(title="", original_idea=""))


def test_create_invention_minimal_fields(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    assert invention.id
    assert invention.status == "아이디어"
    assert invention.invention_no.startswith("INV-")


def test_invention_no_increments_sequentially(db_session):
    service = InventionService(db_session)
    first = service.create(make_input(title="발명 1"))
    second = service.create(make_input(title="발명 2"))
    first_seq = int(first.invention_no.split("-")[-1])
    second_seq = int(second.invention_no.split("-")[-1])
    assert second_seq == first_seq + 1


def test_update_invention(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    updated = service.update(
        invention.id, make_input(title="수정된 제목", status="완료")
    )
    assert updated.title == "수정된 제목"
    assert updated.status == "완료"


def test_delete_invention(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    service.delete(invention.id)
    assert service.get(invention.id) is None


def test_archive_invention_excluded_from_default_list(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    service.set_archived(invention.id, True)
    assert invention.id not in [i.id for i in service.list()]
    assert invention.id in [i.id for i in service.list(include_archived=True)]


def test_save_revision_creates_snapshot(db_session):
    service = InventionService(db_session)
    invention = service.create(make_input())
    revision = service.save_revision(invention.id, change_note="첫 버전")
    assert revision.revision_no == 1
    assert revision.snapshot_json["title"] == invention.title

    service.update(invention.id, make_input(title="다음 버전"))
    revision2 = service.save_revision(invention.id, change_note="두번째 버전")
    assert revision2.revision_no == 2

    revisions = service.list_revisions(invention.id)
    assert len(revisions) == 2


def test_search_by_keyword(db_session):
    service = InventionService(db_session)
    service.create(make_input(title="유리기판 발명"))
    service.create(make_input(title="배터리 발명"))
    results = service.search(keyword="유리기판")
    assert len(results) == 1
    assert results[0].title == "유리기판 발명"
