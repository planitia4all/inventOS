"""SQLAlchemy ORM 모델.

요구사항 9절의 데이터 모델을 그대로 구현한다.
원문 데이터(raw_data_json)와 AI 생성 데이터(ai_comparison_json 등)는
컬럼 단위로 분리해서 보존한다.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Invention(Base):
    __tablename__ = "inventions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    technical_field: Mapped[str | None] = mapped_column(String(200))
    original_idea: Mapped[str] = mapped_column(Text, nullable=False)
    problem_to_solve: Mapped[str | None] = mapped_column(Text)
    conventional_method: Mapped[str | None] = mapped_column(Text)
    conventional_problems: Mapped[str | None] = mapped_column(Text)
    core_principle: Mapped[str | None] = mapped_column(Text)
    expected_effects: Mapped[str | None] = mapped_column(Text)
    technical_barriers: Mapped[str | None] = mapped_column(Text)
    applicable_industries: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    inventor_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(50), default="아이디어")
    is_archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    version: Mapped[int] = mapped_column(Integer, default=1)

    patent_links: Mapped[list["InventionPatentLink"]] = relationship(
        back_populates="invention", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["InventionRevision"]] = relationship(
        back_populates="invention", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="invention", cascade="all, delete-orphan"
    )


class PatentDocument(Base):
    __tablename__ = "patent_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_document_id: Mapped[str | None] = mapped_column(String(200))
    publication_number: Mapped[str] = mapped_column(String(100), nullable=False)
    publication_number_normalized: Mapped[str] = mapped_column(String(100), nullable=False)
    application_number: Mapped[str | None] = mapped_column(String(100))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    abstract_original: Mapped[str | None] = mapped_column(Text)
    abstract_language: Mapped[str | None] = mapped_column(String(10))
    abstract_translated_ko: Mapped[str | None] = mapped_column(Text)
    abstract_ai_summary: Mapped[str | None] = mapped_column(Text)
    applicant: Mapped[str | None] = mapped_column(String(500))
    inventors: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority_date: Mapped[date | None] = mapped_column(Date)
    filing_date: Mapped[date | None] = mapped_column(Date)
    publication_date: Mapped[date | None] = mapped_column(Date)
    country_code: Mapped[str | None] = mapped_column(String(10))
    legal_status: Mapped[str | None] = mapped_column(String(100))
    ipc_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    cpc_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    family_id: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    raw_data_json: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    links: Mapped[list["InventionPatentLink"]] = relationship(
        back_populates="patent", cascade="all, delete-orphan"
    )


class InventionPatentLink(Base):
    __tablename__ = "invention_patent_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=False
    )
    patent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patent_documents.id"), nullable=False
    )
    similarity_score: Mapped[float | None] = mapped_column()
    importance: Mapped[str] = mapped_column(String(20), default="참고")
    review_status: Mapped[str] = mapped_column(String(20), default="미검토")
    similarities: Mapped[str | None] = mapped_column(Text)
    differences: Mapped[str | None] = mapped_column(Text)
    patent_solved_problem: Mapped[str | None] = mapped_column(Text)
    unsolved_problem: Mapped[str | None] = mapped_column(Text)
    differentiation_ideas: Mapped[str | None] = mapped_column(Text)
    additional_research: Mapped[str | None] = mapped_column(Text)
    user_notes: Mapped[str | None] = mapped_column(Text)
    ai_comparison_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    invention: Mapped["Invention"] = relationship(back_populates="patent_links")
    patent: Mapped["PatentDocument"] = relationship(back_populates="links")


class InventionRevision(Base):
    __tablename__ = "invention_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invention: Mapped["Invention"] = relationship(back_populates="revisions")


class Attachment(Base):
    """발명에 첨부된 이미지/PDF 파일 메타데이터.

    실제 파일은 data/attachments/<invention_id>/ 폴더에 저장하고
    DB에는 경로와 원본 파일명만 저장한다.
    """

    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invention: Mapped["Invention"] = relationship(back_populates="attachments")
