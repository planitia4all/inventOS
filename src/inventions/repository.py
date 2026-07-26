"""발명 데이터 접근 계층."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.database.models import (
    Attachment,
    Experiment,
    Invention,
    InventionAIResult,
    InventionRevision,
    InventionTag,
    Tag,
)
from src.search.fts import CONTENT_FIELDS

# 실험 기록에서 fallback 검색이 훑는 필드 (src/search/fts.py의 색인 범위와 맞춘다)
_EXPERIMENT_SEARCH_FIELDS = ("conditions", "results", "failure_reason", "improvement_ideas")


class InventionRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, invention: Invention) -> Invention:
        self.session.add(invention)
        self.session.flush()
        return invention

    def get(self, invention_id: str) -> Invention | None:
        return self.session.get(Invention, invention_id)

    def list_all(self, include_archived: bool = False) -> list[Invention]:
        stmt = select(Invention).order_by(Invention.updated_at.desc())
        if not include_archived:
            stmt = stmt.where(Invention.is_archived.is_(False))
        return list(self.session.scalars(stmt))

    def list_by_created(self, limit: int = 5) -> list[Invention]:
        stmt = (
            select(Invention)
            .where(Invention.is_archived.is_(False))
            .order_by(Invention.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_children(self, invention_id: str) -> list[Invention]:
        stmt = (
            select(Invention)
            .where(Invention.parent_invention_id == invention_id)
            .order_by(Invention.created_at.asc())
        )
        return list(self.session.scalars(stmt))

    def search(
        self,
        keyword: str | None = None,
        technical_field: str | None = None,
        status: str | None = None,
        include_archived: bool = False,
    ) -> list[Invention]:
        """FTS 색인을 쓸 수 없을 때의 대체(fallback) 검색.

        FTS와 똑같은 범위(발명번호/제목/원본/정리된 내용/태그/첨부파일명/
        실험기록/AI결과)를 ILIKE로 훑는다 — 정상 검색과 fallback 검색의
        결과 범위가 달라 보이지 않도록 맞춘 것이다. FTS 장애 상황에서만
        실행되므로 조금 느려도 괜찮다.
        """
        stmt = select(Invention)
        if not include_archived:
            stmt = stmt.where(Invention.is_archived.is_(False))
        if keyword and keyword.strip():
            matched_ids = self._fallback_keyword_ids(keyword.strip())
            stmt = stmt.where(Invention.id.in_(matched_ids))
        if technical_field:
            stmt = stmt.where(Invention.technical_field == technical_field)
        if status:
            stmt = stmt.where(Invention.status == status)
        stmt = stmt.order_by(Invention.updated_at.desc())
        return list(self.session.scalars(stmt))

    def _fallback_keyword_ids(self, keyword: str) -> set[str]:
        like = f"%{keyword}%"
        ids: set[str] = set()

        direct_conditions = [
            Invention.invention_no.ilike(like),
            Invention.title.ilike(like),
            Invention.original_idea.ilike(like),
        ] + [getattr(Invention, name).ilike(like) for name in CONTENT_FIELDS]
        ids.update(
            row[0]
            for row in self.session.execute(select(Invention.id).where(or_(*direct_conditions)))
        )

        tag_stmt = (
            select(InventionTag.invention_id)
            .join(Tag, Tag.id == InventionTag.tag_id)
            .where(Tag.name.ilike(like))
        )
        ids.update(row[0] for row in self.session.execute(tag_stmt))

        attachment_stmt = select(Attachment.invention_id).where(
            Attachment.original_filename.ilike(like)
        )
        ids.update(row[0] for row in self.session.execute(attachment_stmt))

        experiment_conditions = [
            getattr(Experiment, name).ilike(like) for name in _EXPERIMENT_SEARCH_FIELDS
        ]
        experiment_stmt = select(Experiment.invention_id).where(or_(*experiment_conditions))
        ids.update(row[0] for row in self.session.execute(experiment_stmt))

        ai_result_stmt = select(InventionAIResult.invention_id).where(
            InventionAIResult.content.ilike(like),
            InventionAIResult.status != "삭제됨",
        )
        ids.update(row[0] for row in self.session.execute(ai_result_stmt))

        return ids

    def search_by_ids(
        self,
        invention_ids: list[str],
        technical_field: str | None = None,
        status: str | None = None,
        include_archived: bool = False,
    ) -> list[Invention]:
        """FTS 검색 결과(관련도 순 id 목록)를 그 순서 그대로 Invention으로 채운다."""
        if not invention_ids:
            return []
        stmt = select(Invention).where(Invention.id.in_(invention_ids))
        if not include_archived:
            stmt = stmt.where(Invention.is_archived.is_(False))
        if technical_field:
            stmt = stmt.where(Invention.technical_field == technical_field)
        if status:
            stmt = stmt.where(Invention.status == status)

        by_id = {inv.id: inv for inv in self.session.scalars(stmt)}
        return [by_id[i] for i in invention_ids if i in by_id]

    def delete(self, invention: Invention) -> None:
        self.session.delete(invention)
        self.session.flush()

    def next_invention_no(self, year: int) -> str:
        prefix = f"INV-{year}-"
        stmt = select(Invention.invention_no).where(
            Invention.invention_no.like(f"{prefix}%")
        )
        max_seq = 0
        for (invention_no,) in self.session.execute(stmt):
            suffix = invention_no[len(prefix):]
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
        return f"{prefix}{max_seq + 1:05d}"

    def add_revision(self, revision: InventionRevision) -> InventionRevision:
        self.session.add(revision)
        self.session.flush()
        return revision

    def next_revision_no(self, invention_id: str) -> int:
        stmt = select(func.max(InventionRevision.revision_no)).where(
            InventionRevision.invention_id == invention_id
        )
        current = self.session.scalar(stmt)
        return (current or 0) + 1

    def list_revisions(self, invention_id: str) -> list[InventionRevision]:
        stmt = (
            select(InventionRevision)
            .where(InventionRevision.invention_id == invention_id)
            .order_by(InventionRevision.revision_no.desc())
        )
        return list(self.session.scalars(stmt))
