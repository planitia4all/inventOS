"""공동 발명자/팀 협업을 대비한 의견(Comment) 서비스.

지금은 단일 사용자 프로그램이라 UI에 노출하지 않는다. DB와 서비스
계층만 미리 준비해서, 나중에 로그인 시스템이 생기면 author를 실제
사용자 ID로 바꿔 그대로 쓸 수 있게 한다.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import InventionComment


class CommentService:
    def __init__(self, session: Session):
        self.session = session

    def add(
        self, invention_id: str, content: str, author: str | None = None
    ) -> InventionComment:
        text = (content or "").strip()
        if not text:
            raise ValueError("의견 내용을 입력하세요.")

        comment = InventionComment(invention_id=invention_id, author=author, content=text)
        self.session.add(comment)
        self.session.flush()
        return comment

    def list_for_invention(self, invention_id: str) -> list[InventionComment]:
        stmt = (
            select(InventionComment)
            .where(InventionComment.invention_id == invention_id)
            .order_by(InventionComment.created_at.asc())
        )
        return list(self.session.scalars(stmt))

    def delete(self, comment_id: str) -> None:
        comment = self.session.get(InventionComment, comment_id)
        if comment is not None:
            self.session.delete(comment)
