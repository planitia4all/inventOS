"""향후 공동 발명자/팀 협업을 대비한 Comment 스텁 검증.

UI에는 아직 노출하지 않지만, DB/서비스 계층이 정상 동작하는지 확인한다.
"""
from __future__ import annotations

import pytest

from src.comments.service import CommentService
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService


def make_invention(session):
    return InventionService(session).quick_create(QuickIdeaInput(memo="의견 테스트용"))


def test_add_comment(db_session):
    invention = make_invention(db_session)
    comment = CommentService(db_session).add(invention.id, "좋은 아이디어네요", author="철수")
    assert comment.content == "좋은 아이디어네요"
    assert comment.author == "철수"


def test_add_comment_rejects_empty_content(db_session):
    invention = make_invention(db_session)
    with pytest.raises(ValueError):
        CommentService(db_session).add(invention.id, "   ")


def test_list_for_invention_is_chronological(db_session):
    invention = make_invention(db_session)
    service = CommentService(db_session)
    service.add(invention.id, "첫 의견")
    service.add(invention.id, "두번째 의견")

    comments = service.list_for_invention(invention.id)
    assert [c.content for c in comments] == ["첫 의견", "두번째 의견"]


def test_delete_comment(db_session):
    invention = make_invention(db_session)
    service = CommentService(db_session)
    comment = service.add(invention.id, "삭제될 의견")
    service.delete(comment.id)
    assert service.list_for_invention(invention.id) == []


def test_invention_owner_id_defaults_to_none(db_session):
    invention = make_invention(db_session)
    assert invention.owner_id is None
