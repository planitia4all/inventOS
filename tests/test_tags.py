from __future__ import annotations

from src.inventions.schemas import InventionInput, QuickIdeaInput
from src.inventions.service import InventionService
from src.tags.service import TagService


def make_invention(session):
    return InventionService(session).quick_create(QuickIdeaInput(memo="태그 테스트용"))


def test_add_tags_creates_and_links(db_session):
    inv = make_invention(db_session)
    TagService(db_session).add_tags(inv.id, ["Battery", "Robot"])

    names = TagService(db_session).tag_names(inv.id)
    assert set(names) == {"Battery", "Robot"}


def test_add_tags_reuses_existing_tag_case_insensitively(db_session):
    inv1 = InventionService(db_session).quick_create(QuickIdeaInput(memo="1"))
    inv2 = InventionService(db_session).quick_create(QuickIdeaInput(memo="2"))

    TagService(db_session).add_tags(inv1.id, ["battery"])
    TagService(db_session).add_tags(inv2.id, ["Battery"])

    assert len(TagService(db_session).list_all()) == 1


def test_add_tags_skips_duplicates_on_same_invention(db_session):
    inv = make_invention(db_session)
    TagService(db_session).add_tags(inv.id, ["AI"])
    TagService(db_session).add_tags(inv.id, ["AI", "Robot"])

    names = TagService(db_session).tag_names(inv.id)
    assert names.count("AI") == 1
    assert set(names) == {"AI", "Robot"}


def test_set_tags_for_invention_replaces_all(db_session):
    inv = make_invention(db_session)
    TagService(db_session).add_tags(inv.id, ["AI", "Robot"])

    TagService(db_session).set_tags_for_invention(inv.id, ["Marine"])

    assert TagService(db_session).tag_names(inv.id) == ["Marine"]


def test_find_inventions_by_tag(db_session):
    inv = make_invention(db_session)
    TagService(db_session).add_tags(inv.id, ["Automation"])

    found = TagService(db_session).find_inventions_by_tag("automation")
    assert [i.id for i in found] == [inv.id]


def test_invention_create_wires_tags(db_session):
    invention = InventionService(db_session).create(
        InventionInput(
            title="발명",
            original_idea="본문",
            keywords=["Electrical", "Patent"],
        )
    )
    names = TagService(db_session).tag_names(invention.id)
    assert set(names) == {"Electrical", "Patent"}


def test_invention_update_replaces_tags(db_session):
    invention = InventionService(db_session).create(
        InventionInput(title="발명", original_idea="본문", keywords=["A"])
    )
    InventionService(db_session).update(
        invention.id,
        InventionInput(title="발명", original_idea="본문", keywords=["B", "C"]),
    )
    assert set(TagService(db_session).tag_names(invention.id)) == {"B", "C"}
