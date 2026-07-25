"""특허 및 발명-특허 연결 비즈니스 로직."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from src.database.models import InventionPatentLink, PatentDocument
from src.patents.providers.base import PatentDetail, normalize_publication_number
from src.patents.repository import PatentRepository
from src.patents.schemas import ComparisonInput, ManualPatentInput


class DuplicatePatentLinkError(Exception):
    """이미 같은 발명에 같은 특허(공개번호 기준)가 연결되어 있는 경우."""


class PatentService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = PatentRepository(session)

    def _get_or_create_patent(
        self,
        publication_number: str,
        build_patent: callable,
    ) -> PatentDocument:
        """공개번호(정규화 기준)로 기존 특허를 재사용하거나 새로 만든다.

        동일 공개번호가 여러 발명에서 참조될 수 있으므로 PatentDocument는
        전역에서 1건만 유지한다.
        """
        normalized = normalize_publication_number(publication_number)
        existing = self.repo.find_by_normalized(normalized)
        if existing:
            return existing
        patent = build_patent(normalized)
        return self.repo.add(patent)

    def register_manual(
        self, invention_id: str, data: ManualPatentInput
    ) -> InventionPatentLink:
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        def build_patent(normalized: str) -> PatentDocument:
            return PatentDocument(
                provider="manual",
                provider_document_id=None,
                publication_number=data.publication_number.strip(),
                publication_number_normalized=normalized,
                application_number=data.application_number,
                title=data.title.strip(),
                abstract_original=data.abstract_original,
                abstract_language="ko" if data.abstract_original else None,
                applicant=data.applicant,
                priority_date=data.priority_date,
                country_code=data.country_code,
                legal_status=None,
                source_url=data.source_url,
                raw_data_json={"source": "user_input", "note": data.note},
                fetched_at=datetime.utcnow(),
            )

        patent = self._get_or_create_patent(data.publication_number, build_patent)
        return self._link(invention_id, patent.id)

    def register_from_detail(
        self, invention_id: str, detail: PatentDetail
    ) -> InventionPatentLink:
        """Phase 3+ Provider 검색 결과를 발명에 연결한다."""

        def build_patent(normalized: str) -> PatentDocument:
            return PatentDocument(
                provider=detail.provider,
                provider_document_id=detail.provider_document_id,
                publication_number=detail.publication_number,
                publication_number_normalized=normalized,
                application_number=detail.application_number,
                registration_number=detail.registration_number,
                title=detail.title,
                abstract_original=detail.abstract_original,
                abstract_language=detail.abstract_language,
                applicant=detail.applicant,
                inventors=detail.inventors,
                priority_date=detail.priority_date,
                filing_date=detail.filing_date,
                publication_date=detail.publication_date,
                country_code=detail.country_code,
                legal_status=detail.legal_status,
                ipc_codes=detail.ipc_codes,
                cpc_codes=detail.cpc_codes,
                family_id=detail.family_id,
                source_url=detail.source_url,
                raw_data_json=detail.raw_data_json,
                fetched_at=datetime.utcnow(),
            )

        patent = self._get_or_create_patent(detail.publication_number, build_patent)
        return self._link(invention_id, patent.id)

    def _link(self, invention_id: str, patent_id: str) -> InventionPatentLink:
        existing_link = self.repo.find_link(invention_id, patent_id)
        if existing_link:
            raise DuplicatePatentLinkError("이미 이 발명에 연결된 특허입니다.")
        link = InventionPatentLink(invention_id=invention_id, patent_id=patent_id)
        return self.repo.add_link(link)

    def list_for_invention(self, invention_id: str) -> list[InventionPatentLink]:
        return self.repo.list_links_for_invention(invention_id)

    def update_comparison(self, link_id: str, data: ComparisonInput) -> InventionPatentLink:
        link = self.repo.get_link(link_id)
        if link is None:
            raise LookupError(f"연결 정보를 찾을 수 없습니다: {link_id}")
        link.similarities = data.similarities
        link.differences = data.differences
        link.patent_solved_problem = data.patent_solved_problem
        link.unsolved_problem = data.unsolved_problem
        link.differentiation_ideas = data.differentiation_ideas
        link.additional_research = data.additional_research
        link.user_notes = data.user_notes
        link.importance = data.importance
        link.review_status = data.review_status
        self.session.flush()
        return link

    def set_similarity_score(self, link_id: str, score: float) -> InventionPatentLink:
        link = self.repo.get_link(link_id)
        if link is None:
            raise LookupError(f"연결 정보를 찾을 수 없습니다: {link_id}")
        link.similarity_score = score
        self.session.flush()
        return link

    def delete_link(self, link_id: str) -> None:
        link = self.repo.get_link(link_id)
        if link is None:
            raise LookupError(f"연결 정보를 찾을 수 없습니다: {link_id}")
        self.repo.delete_link(link)
