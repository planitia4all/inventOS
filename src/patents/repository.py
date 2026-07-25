"""특허 데이터 접근 계층."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import InventionPatentLink, PatentDocument


class PatentRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_by_normalized(self, publication_number_normalized: str) -> PatentDocument | None:
        stmt = select(PatentDocument).where(
            PatentDocument.publication_number_normalized == publication_number_normalized
        )
        return self.session.scalars(stmt).first()

    def add(self, patent: PatentDocument) -> PatentDocument:
        self.session.add(patent)
        self.session.flush()
        return patent

    def get(self, patent_id: str) -> PatentDocument | None:
        return self.session.get(PatentDocument, patent_id)

    def find_link(self, invention_id: str, patent_id: str) -> InventionPatentLink | None:
        stmt = select(InventionPatentLink).where(
            InventionPatentLink.invention_id == invention_id,
            InventionPatentLink.patent_id == patent_id,
        )
        return self.session.scalars(stmt).first()

    def add_link(self, link: InventionPatentLink) -> InventionPatentLink:
        self.session.add(link)
        self.session.flush()
        return link

    def get_link(self, link_id: str) -> InventionPatentLink | None:
        return self.session.get(InventionPatentLink, link_id)

    def list_links_for_invention(self, invention_id: str) -> list[InventionPatentLink]:
        stmt = (
            select(InventionPatentLink)
            .where(InventionPatentLink.invention_id == invention_id)
            .order_by(InventionPatentLink.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def delete_link(self, link: InventionPatentLink) -> None:
        self.session.delete(link)
        self.session.flush()
