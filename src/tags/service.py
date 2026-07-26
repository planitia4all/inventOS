"""태그 서비스.

태그를 발명마다 문자열로 따로 들고 있지 않고, `Tag` 사전 테이블 하나를
공유해서 중복 없이 관리한다. 대소문자/앞뒤 공백만 다른 태그는 같은
태그로 합친다.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Invention, InventionTag, Tag


def _normalize(name: str) -> str:
    return name.strip()


class TagService:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, name: str) -> Tag:
        clean = _normalize(name)
        existing = self.session.scalar(
            select(Tag).where(Tag.name.ilike(clean))
        )
        if existing:
            return existing
        tag = Tag(name=clean)
        self.session.add(tag)
        self.session.flush()
        return tag

    def add_tags(self, invention_id: str, names: list[str]) -> list[Tag]:
        """주어진 태그들을 발명에 추가한다 (이미 있으면 건너뜀)."""
        added: list[Tag] = []
        existing_names = {t.name.lower() for t in self.list_for_invention(invention_id)}
        for raw_name in names:
            clean = _normalize(raw_name)
            if not clean or clean.lower() in existing_names:
                continue
            tag = self.get_or_create(clean)
            self.session.add(InventionTag(invention_id=invention_id, tag_id=tag.id))
            existing_names.add(clean.lower())
            added.append(tag)
        if added:
            self.session.flush()
        return added

    def set_tags_for_invention(self, invention_id: str, names: list[str]) -> list[Tag]:
        """발명의 태그를 주어진 목록으로 완전히 교체한다."""
        stmt = select(InventionTag).where(InventionTag.invention_id == invention_id)
        for link in self.session.scalars(stmt):
            self.session.delete(link)
        self.session.flush()
        return self.add_tags(invention_id, names)

    def list_for_invention(self, invention_id: str) -> list[Tag]:
        stmt = (
            select(Tag)
            .join(InventionTag, InventionTag.tag_id == Tag.id)
            .where(InventionTag.invention_id == invention_id)
            .order_by(Tag.name)
        )
        return list(self.session.scalars(stmt))

    def tag_names(self, invention_id: str) -> list[str]:
        return [t.name for t in self.list_for_invention(invention_id)]

    def list_all(self) -> list[Tag]:
        return list(self.session.scalars(select(Tag).order_by(Tag.name)))

    def find_inventions_by_tag(self, name: str) -> list[Invention]:
        stmt = (
            select(Invention)
            .join(InventionTag, InventionTag.invention_id == Invention.id)
            .join(Tag, Tag.id == InventionTag.tag_id)
            .where(Tag.name.ilike(_normalize(name)))
        )
        return list(self.session.scalars(stmt))
