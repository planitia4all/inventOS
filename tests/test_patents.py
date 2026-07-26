from __future__ import annotations

from datetime import date

import pytest

from src.inventions.schemas import InventionInput
from src.inventions.service import InventionService
from src.patents.providers.base import normalize_publication_number
from src.patents.schemas import ComparisonInput, ManualPatentInput
from src.patents.service import DuplicatePatentLinkError, PatentService


def make_invention(session, title="발명 A"):
    return InventionService(session).create(
        InventionInput(title=title, original_idea="아이디어 본문")
    )


def make_patent_input(**overrides) -> ManualPatentInput:
    data = dict(
        title="선행특허 A",
        publication_number="KR10-2020-0012345",
        applicant="테스트출원인",
        priority_date=date(2019, 1, 1),
        country_code="KR",
        abstract_original="선행특허 초록입니다.",
    )
    data.update(overrides)
    return ManualPatentInput(**data)


def test_normalize_publication_number():
    assert normalize_publication_number("KR10-2020-0012345 A1") == "KR1020200012345A1"
    assert normalize_publication_number("kr 10-2020-0012345") == "KR1020200012345"


def test_register_manual_patent_and_link(db_session):
    invention = make_invention(db_session)
    service = PatentService(db_session)

    link = service.register_manual(invention.id, make_patent_input())

    assert link.patent.title == "선행특허 A"
    assert link.patent.provider == "manual"
    assert link.importance == "참고"
    assert link.review_status == "미검토"

    links = service.list_for_invention(invention.id)
    assert len(links) == 1


def test_register_manual_requires_title_and_number(db_session):
    invention = make_invention(db_session)
    service = PatentService(db_session)
    with pytest.raises(ValueError):
        service.register_manual(
            invention.id, make_patent_input(title="", publication_number="")
        )


def test_duplicate_publication_number_reuses_patent_document(db_session):
    inv1 = make_invention(db_session, "발명 A")
    inv2 = make_invention(db_session, "발명 B")
    service = PatentService(db_session)

    link1 = service.register_manual(inv1.id, make_patent_input())
    link2 = service.register_manual(
        inv2.id, make_patent_input(publication_number="KR 10-2020-0012345")
    )

    assert link1.patent_id == link2.patent_id


def test_same_invention_cannot_link_same_patent_twice(db_session):
    invention = make_invention(db_session)
    service = PatentService(db_session)
    service.register_manual(invention.id, make_patent_input())
    with pytest.raises(DuplicatePatentLinkError):
        service.register_manual(invention.id, make_patent_input())


def test_update_comparison_fields(db_session):
    invention = make_invention(db_session)
    service = PatentService(db_session)
    link = service.register_manual(invention.id, make_patent_input())

    updated = service.update_comparison(
        link.id,
        ComparisonInput(
            similarities="공통점 메모",
            differences="차이점 메모",
            importance="매우 중요",
            review_status="검토 완료",
        ),
    )

    assert updated.similarities == "공통점 메모"
    assert updated.importance == "매우 중요"
    assert updated.review_status == "검토 완료"


def test_ai_comparison_draft_not_applied_until_apply_called(db_session):
    invention = make_invention(db_session)
    service = PatentService(db_session)
    link = service.register_manual(invention.id, make_patent_input())

    draft = {
        "similarities": ["같은 점 A"],
        "differences": ["다른 점 B"],
        "prior_patent_core": "핵심",
        "possible_differentiators": ["차별화 C"],
        "technical_risks": [],
        "additional_search_terms": [],
        "confidence": 70,
    }
    service.save_ai_comparison_draft(link.id, draft)

    unchanged = service.repo.get_link(link.id)
    assert unchanged.similarities is None
    assert unchanged.ai_comparison_json == draft

    applied = service.apply_ai_comparison_draft(link.id)
    assert applied.similarities == "같은 점 A"
    assert applied.differences == "다른 점 B"
    assert applied.differentiation_ideas == "차별화 C"


def test_apply_ai_comparison_draft_without_draft_raises(db_session):
    invention = make_invention(db_session)
    service = PatentService(db_session)
    link = service.register_manual(invention.id, make_patent_input())
    with pytest.raises(ValueError):
        service.apply_ai_comparison_draft(link.id)


def test_register_manual_logs_timeline_event(db_session):
    invention = make_invention(db_session)
    service = PatentService(db_session)
    service.register_manual(invention.id, make_patent_input())

    from src.inventions.service import InventionService

    types = [e.event_type for e in InventionService(db_session).list_timeline(invention.id)]
    assert "prior_art_linked" in types


def test_apply_ai_comparison_draft_logs_timeline_event(db_session):
    invention = make_invention(db_session)
    service = PatentService(db_session)
    link = service.register_manual(invention.id, make_patent_input())
    service.save_ai_comparison_draft(
        link.id,
        {
            "similarities": ["A"],
            "differences": [],
            "prior_patent_core": "",
            "possible_differentiators": [],
            "technical_risks": [],
            "additional_search_terms": [],
            "confidence": 50,
        },
    )
    service.apply_ai_comparison_draft(link.id)

    from src.inventions.service import InventionService

    types = [e.event_type for e in InventionService(db_session).list_timeline(invention.id)]
    assert "ai_result_applied" in types


def test_delete_link_removes_from_invention_but_keeps_patent(db_session):
    invention = make_invention(db_session)
    service = PatentService(db_session)
    link = service.register_manual(invention.id, make_patent_input())
    patent_id = link.patent_id

    service.delete_link(link.id)

    assert service.list_for_invention(invention.id) == []
    assert service.repo.get(patent_id) is not None
