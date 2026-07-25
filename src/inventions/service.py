"""발명 비즈니스 로직.

UI는 이 계층만 호출하고, ORM/DB 세부사항을 직접 다루지 않는다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.database.models import Invention, InventionRevision
from src.inventions.repository import InventionRepository
from src.inventions.schemas import InventionInput


def invention_to_dict(invention: Invention) -> dict:
    return {
        "id": invention.id,
        "invention_no": invention.invention_no,
        "title": invention.title,
        "technical_field": invention.technical_field,
        "original_idea": invention.original_idea,
        "problem_to_solve": invention.problem_to_solve,
        "conventional_method": invention.conventional_method,
        "conventional_problems": invention.conventional_problems,
        "core_principle": invention.core_principle,
        "expected_effects": invention.expected_effects,
        "technical_barriers": invention.technical_barriers,
        "applicable_industries": invention.applicable_industries,
        "keywords": invention.keywords or [],
        "inventor_name": invention.inventor_name,
        "status": invention.status,
        "is_archived": invention.is_archived,
        "created_at": invention.created_at.isoformat() if invention.created_at else None,
        "updated_at": invention.updated_at.isoformat() if invention.updated_at else None,
        "version": invention.version,
    }


class InventionService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = InventionRepository(session)

    def create(self, data: InventionInput) -> Invention:
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        year = datetime.now(timezone.utc).year
        invention_no = self.repo.next_invention_no(year)
        invention = Invention(
            invention_no=invention_no,
            title=data.title.strip(),
            technical_field=data.technical_field,
            original_idea=data.original_idea.strip(),
            problem_to_solve=data.problem_to_solve,
            conventional_method=data.conventional_method,
            conventional_problems=data.conventional_problems,
            core_principle=data.core_principle,
            expected_effects=data.expected_effects,
            technical_barriers=data.technical_barriers,
            applicable_industries=data.applicable_industries,
            keywords=data.keywords or [],
            inventor_name=data.inventor_name,
            status=data.status or "아이디어",
        )
        return self.repo.add(invention)

    def update(self, invention_id: str, data: InventionInput) -> Invention:
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        invention = self.repo.get(invention_id)
        if invention is None:
            raise LookupError(f"발명을 찾을 수 없습니다: {invention_id}")

        invention.title = data.title.strip()
        invention.technical_field = data.technical_field
        invention.original_idea = data.original_idea.strip()
        invention.problem_to_solve = data.problem_to_solve
        invention.conventional_method = data.conventional_method
        invention.conventional_problems = data.conventional_problems
        invention.core_principle = data.core_principle
        invention.expected_effects = data.expected_effects
        invention.technical_barriers = data.technical_barriers
        invention.applicable_industries = data.applicable_industries
        invention.keywords = data.keywords or []
        invention.inventor_name = data.inventor_name
        invention.status = data.status or invention.status
        self.session.flush()
        return invention

    def get(self, invention_id: str) -> Invention | None:
        return self.repo.get(invention_id)

    def list(self, include_archived: bool = False) -> list[Invention]:
        return self.repo.list_all(include_archived=include_archived)

    def search(
        self,
        keyword: str | None = None,
        technical_field: str | None = None,
        status: str | None = None,
        include_archived: bool = False,
    ) -> list[Invention]:
        return self.repo.search(
            keyword=keyword,
            technical_field=technical_field,
            status=status,
            include_archived=include_archived,
        )

    def delete(self, invention_id: str) -> None:
        invention = self.repo.get(invention_id)
        if invention is None:
            raise LookupError(f"발명을 찾을 수 없습니다: {invention_id}")
        self.repo.delete(invention)

    def set_archived(self, invention_id: str, archived: bool) -> Invention:
        invention = self.repo.get(invention_id)
        if invention is None:
            raise LookupError(f"발명을 찾을 수 없습니다: {invention_id}")
        invention.is_archived = archived
        self.session.flush()
        return invention

    def save_revision(self, invention_id: str, change_note: str | None = None) -> InventionRevision:
        invention = self.repo.get(invention_id)
        if invention is None:
            raise LookupError(f"발명을 찾을 수 없습니다: {invention_id}")

        revision_no = self.repo.next_revision_no(invention_id)
        revision = InventionRevision(
            invention_id=invention_id,
            revision_no=revision_no,
            snapshot_json=invention_to_dict(invention),
            change_note=change_note,
        )
        invention.version = revision_no
        self.repo.add_revision(revision)
        return revision

    def list_revisions(self, invention_id: str) -> list[InventionRevision]:
        return self.repo.list_revisions(invention_id)
