"""SQLAlchemy ORM 모델.

핵심 관점: 발명은 정적인 문서 한 건이 아니라 시간에 따라 계속 발전하는
객체다. 그래서 원본 메모(Invention.original_idea)와 AI가 만든 결과
(InventionAIResult), 발전 과정의 각 사건(InventionEvent), 실험
(Experiment), 파생 아이디어(Invention.parent_invention_id)를 각각
독립된 테이블로 분리해서 보존한다 — 무엇 하나가 다른 것을 덮어쓰지 않는다.

원문 데이터(raw_data_json)와 AI 생성 데이터(ai_comparison_json 등)는
컬럼 단위로 분리해서 보존한다.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Invention(Base):
    __tablename__ = "inventions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # UUID(id)는 내부용, invention_no(INV-2026-00001)는 사용자가 보는 번호.
    invention_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # 사용자가 제목을 비워두면 서비스 계층이 메모 첫 문장/날짜로 자동 생성한다.
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    technical_field: Mapped[str | None] = mapped_column(String(200))
    # 최초로 기록한 원본 메모. AI 정리나 내용 구체화로 덮어쓰지 않는다.
    original_idea: Mapped[str] = mapped_column(Text, nullable=False)
    # 원본과 분리해서 보관하는 '정리된 발명 내용'
    refined_content: Mapped[str | None] = mapped_column(Text)
    problem_to_solve: Mapped[str | None] = mapped_column(Text)
    conventional_method: Mapped[str | None] = mapped_column(Text)
    conventional_problems: Mapped[str | None] = mapped_column(Text)
    core_principle: Mapped[str | None] = mapped_column(Text)
    key_components: Mapped[str | None] = mapped_column(Text)
    operating_principle: Mapped[str | None] = mapped_column(Text)
    differentiation: Mapped[str | None] = mapped_column(Text)
    expected_effects: Mapped[str | None] = mapped_column(Text)
    technical_barriers: Mapped[str | None] = mapped_column(Text)
    applicable_industries: Mapped[str | None] = mapped_column(Text)
    implementation_method: Mapped[str | None] = mapped_column(Text)
    experiment_notes: Mapped[str | None] = mapped_column(Text)
    review_notes: Mapped[str | None] = mapped_column(Text)
    # 더 이상 새로 쓰지 않는 예전 컬럼. 표시/검색은 Tag 테이블을 정본으로
    # 쓴다 — 마이그레이션이 이 값을 Tag/InventionTag로 옮겨 담는다.
    # (파괴적 컬럼 삭제는 하지 않는다는 원칙에 따라 컬럼 자체는 남겨둔다)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    inventor_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(50), default="아이디어")
    is_favorite: Mapped[bool] = mapped_column(default=False)
    is_archived: Mapped[bool] = mapped_column(default=False)

    # 파생 아이디어(부모→자식) 관계. 예: Separator 접합 → Graphene Fiber 방식.
    # 지금은 DB 구조만 준비하고 UI에는 노출하지 않는다.
    parent_invention_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=True
    )

    # 다중 사용자 확장을 대비한 자리. 지금은 단일 사용자라 항상 None이고
    # UI에도 없다 — 나중에 로그인/공동 발명자를 붙일 때 채워 넣는다.
    owner_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

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
    ai_results: Mapped[list["InventionAIResult"]] = relationship(
        back_populates="invention", cascade="all, delete-orphan"
    )
    events: Mapped[list["InventionEvent"]] = relationship(
        back_populates="invention", cascade="all, delete-orphan"
    )
    experiments: Mapped[list["Experiment"]] = relationship(
        back_populates="invention", cascade="all, delete-orphan"
    )
    comments: Mapped[list["InventionComment"]] = relationship(
        back_populates="invention", cascade="all, delete-orphan"
    )
    tag_links: Mapped[list["InventionTag"]] = relationship(
        back_populates="invention", cascade="all, delete-orphan"
    )

    children: Mapped[list["Invention"]] = relationship(
        back_populates="parent",
        cascade="all",
        remote_side="Invention.parent_invention_id",
        foreign_keys="[Invention.parent_invention_id]",
        single_parent=False,
    )
    parent: Mapped["Invention | None"] = relationship(
        back_populates="children",
        remote_side="Invention.id",
        foreign_keys="[Invention.parent_invention_id]",
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
    """원본/발명 내용 전체의 시점별 스냅샷 (되돌리기용)."""

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


class InventionAIResult(Base):
    """AI가 만든 결과를 원본과 분리해서 보관하는 독립 객체.

    예: 원본 아이디어 → AI 분석 → AI 개선안 → 사용자 수정 → 최종 발명 내용.
    각 단계가 별도 레코드다. 사용자가 '결과 반영' 버튼을 눌러야만
    `applied_at`이 채워지고 지정한 발명 필드로 내용이 복사된다 — 그
    전까지는 발명 원문에 어떤 영향도 주지 않는다.
    """

    __tablename__ = "invention_ai_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=False
    )
    # 자유 문자열: "summary"(정리), "gap_analysis"(부족한 부분), "improvement"(개선안),
    # "differentiation"(차별점), "derived_idea"(파생 아이디어 제안) 등. 새 종류를
    # 추가할 때 코드 변경(마이그레이션) 없이 문자열만 늘어난다.
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    source_field: Mapped[str | None] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # 적용 전에는 둘 다 None. 적용하는 순간 시각과 반영된 발명 필드명이 채워진다.
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    applied_to_field: Mapped[str | None] = mapped_column(String(50))

    invention: Mapped["Invention"] = relationship(back_populates="ai_results")


class InventionEvent(Base):
    """발명이 어떻게 발전했는지 보여주는 자동 기록(Timeline)의 한 줄.

    InventionRevision(되돌리기용 전체 스냅샷)과는 목적이 다르다 — 이건
    '무슨 일이 있었는지'를 시간순으로 보여주기 위한 요약 로그다.
    """

    __tablename__ = "invention_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=False
    )
    # 자유 문자열: created/original_revised/content_updated/status_changed/
    # attachment_added/prior_art_linked/ai_result_applied/experiment_recorded/
    # derived_child_created 등. 새 종류를 추가해도 스키마 변경이 필요 없다.
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    meta_json: Mapped[dict | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invention: Mapped["Invention"] = relationship(back_populates="events")


class Experiment(Base):
    """실험 기록. 발명 본문과 동등하게 중요한 1급 데이터로 관리한다."""

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=False
    )
    experiment_date: Mapped[date | None] = mapped_column(Date)
    conditions: Mapped[str | None] = mapped_column(Text)
    results: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    improvement_ideas: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    invention: Mapped["Invention"] = relationship(back_populates="experiments")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="experiment")


class InventionComment(Base):
    """향후 공동 발명자/팀 협업을 대비한 의견(Comment) 자리.

    지금은 단일 사용자 프로그램이라 UI에 노출하지 않는다. author는 자유
    문자열(로그인 시스템이 생기면 사용자 ID로 대체).
    """

    __tablename__ = "invention_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=False
    )
    author: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invention: Mapped["Invention"] = relationship(back_populates="comments")


class Tag(Base):
    """중복 없이 관리하는 태그 사전. 문자열을 발명마다 따로 들고 있지 않는다."""

    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invention_links: Mapped[list["InventionTag"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class InventionTag(Base):
    """발명 ↔ 태그 다대다 연결."""

    __tablename__ = "invention_tags"
    __table_args__ = (UniqueConstraint("invention_id", "tag_id", name="uq_invention_tag"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=False
    )
    tag_id: Mapped[str] = mapped_column(String(36), ForeignKey("tags.id"), nullable=False)

    invention: Mapped["Invention"] = relationship(back_populates="tag_links")
    tag: Mapped["Tag"] = relationship(back_populates="invention_links")


# 첨부파일을 어떤 목적으로 올렸는지 구분하는 값. 자유 문자열이라 나중에
# 종류를 추가해도 스키마 변경이 필요 없다.
ATTACHMENT_CATEGORIES = [
    "사진",
    "스케치",
    "특허 PDF",
    "실험 자료",
    "참고자료",
    "도면",
    "매뉴얼",
    "CAD",
    "동영상",
    "음성",
    "기타",
]


class Attachment(Base):
    """발명(또는 특정 실험)에 첨부된 파일 메타데이터.

    실제 파일은 data/attachments/<invention_id>/ 폴더에 저장하고
    DB에는 경로와 원본 파일명만 저장한다.
    """

    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invention_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventions.id"), nullable=False
    )
    # 특정 실험에 딸린 사진/영상이면 채워진다 (선택).
    experiment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("experiments.id"), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(30), default="기타")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invention: Mapped["Invention"] = relationship(back_populates="attachments")
    experiment: Mapped["Experiment | None"] = relationship(back_populates="attachments")
