"""발명 비즈니스 로직.

UI는 이 계층만 호출하고, ORM/DB 세부사항을 직접 다루지 않는다.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.database.models import Invention, InventionRevision
from src.inventions.repository import InventionRepository
from src.inventions.schemas import InventionInput, QuickIdeaInput

_TITLE_MAX_LEN = 40

# invention_to_dict / update 에서 함께 다루는 본문 필드
_CONTENT_FIELDS = (
    "technical_field",
    "refined_content",
    "problem_to_solve",
    "conventional_method",
    "conventional_problems",
    "core_principle",
    "key_components",
    "operating_principle",
    "differentiation",
    "expected_effects",
    "technical_barriers",
    "applicable_industries",
    "implementation_method",
    "experiment_notes",
    "review_notes",
    "inventor_name",
)


def generate_title(memo: str, created_at: datetime | None = None) -> str:
    """제목을 입력하지 않았을 때 메모 첫 문장(없으면 날짜)으로 제목을 만든다."""
    text = (memo or "").strip()
    if text:
        # 첫 문장 또는 첫 줄을 제목 후보로 사용한다.
        first = re.split(r"[.!?\n]", text, maxsplit=1)[0].strip()
        if first:
            if len(first) > _TITLE_MAX_LEN:
                first = first[:_TITLE_MAX_LEN].rstrip() + "..."
            return first

    stamp = (created_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return f"{stamp} 아이디어"


def invention_to_dict(invention: Invention) -> dict:
    data = {
        "id": invention.id,
        "invention_no": invention.invention_no,
        "title": invention.title,
        "original_idea": invention.original_idea,
        "keywords": invention.keywords or [],
        "status": invention.status,
        "is_favorite": invention.is_favorite,
        "is_archived": invention.is_archived,
        "created_at": invention.created_at.isoformat() if invention.created_at else None,
        "updated_at": invention.updated_at.isoformat() if invention.updated_at else None,
        "version": invention.version,
    }
    for name in _CONTENT_FIELDS:
        data[name] = getattr(invention, name)
    return data


class InventionService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = InventionRepository(session)

    # ------------------------------------------------------------------
    # 생성
    # ------------------------------------------------------------------
    def quick_create(self, data: QuickIdeaInput) -> Invention:
        """홈 화면의 빠른 기록. 메모만 있으면 바로 저장한다."""
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        return self._create(
            original_idea=data.memo.strip(),
            title=data.title,
            keywords=data.keywords or [],
        )

    def create(self, data: InventionInput) -> Invention:
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        invention = self._create(
            original_idea=data.original_idea.strip(),
            title=data.title,
            keywords=data.keywords or [],
            status=data.status or "아이디어",
        )
        for name in _CONTENT_FIELDS:
            setattr(invention, name, getattr(data, name))
        self.session.flush()
        return invention

    def _create(
        self,
        original_idea: str,
        title: str = "",
        keywords: list[str] | None = None,
        status: str = "아이디어",
    ) -> Invention:
        year = datetime.now(timezone.utc).year
        invention = Invention(
            invention_no=self.repo.next_invention_no(year),
            title=(title or "").strip() or generate_title(original_idea),
            original_idea=original_idea,
            keywords=keywords or [],
            status=status,
        )
        return self.repo.add(invention)

    # ------------------------------------------------------------------
    # 수정
    # ------------------------------------------------------------------
    def update(self, invention_id: str, data: InventionInput) -> Invention:
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        invention = self._require(invention_id)

        # 원본 아이디어가 바뀌는 경우, 바뀌기 전 상태를 자동으로 버전에 남긴다.
        # (원본 기록은 덮어쓰더라도 이전 내용을 반드시 되찾을 수 있어야 한다)
        new_original = data.original_idea.strip()
        if new_original != invention.original_idea:
            self._snapshot(invention, change_note="원본 아이디어 수정 전 자동 저장")

        invention.original_idea = new_original
        invention.title = (data.title or "").strip() or generate_title(new_original)
        invention.keywords = data.keywords or []
        invention.status = data.status or invention.status
        for name in _CONTENT_FIELDS:
            setattr(invention, name, getattr(data, name))
        self.session.flush()
        return invention

    def update_fields(self, invention_id: str, **fields) -> Invention:
        """상세 화면에서 일부 항목만 저장할 때 사용한다.

        원본 아이디어(original_idea)는 이 경로로 바꿀 수 없다. 원본을 고치려면
        `update()`를 써서 이전 버전이 남도록 한다.
        """
        invention = self._require(invention_id)
        allowed = set(_CONTENT_FIELDS) | {"title", "status", "keywords"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"수정할 수 없는 항목입니다: {', '.join(sorted(unknown))}")

        for name, value in fields.items():
            setattr(invention, name, value)
        self.session.flush()
        return invention

    def update_original_idea(
        self, invention_id: str, new_text: str, change_note: str | None = None
    ) -> Invention:
        """원본 메모만 수정한다. 수정 전 내용은 항상 버전으로 남는다."""
        text = (new_text or "").strip()
        if not text:
            raise ValueError("아이디어 내용을 입력하세요.")

        invention = self._require(invention_id)
        if text == invention.original_idea:
            return invention

        self._snapshot(
            invention, change_note=change_note or "원본 아이디어 수정 전 자동 저장"
        )
        invention.original_idea = text
        self.session.flush()
        return invention

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------
    def get(self, invention_id: str) -> Invention | None:
        return self.repo.get(invention_id)

    def list(self, include_archived: bool = False) -> list[Invention]:
        return self.repo.list_all(include_archived=include_archived)

    def list_recent(self, limit: int = 5) -> list[Invention]:
        return self.repo.list_all(include_archived=False)[:limit]

    def list_favorites(self, limit: int | None = None) -> list[Invention]:
        items = [i for i in self.repo.list_all(include_archived=False) if i.is_favorite]
        return items[:limit] if limit else items

    def list_needs_review(self, limit: int | None = None) -> list[Invention]:
        """아직 구체화하지 않은 아이디어.

        빠르게 적어두기만 하고 내용을 채우지 않은 것을 골라낸다.
        """
        items = [
            i
            for i in self.repo.list_all(include_archived=False)
            if i.status == "아이디어" and not (i.refined_content or "").strip()
        ]
        return items[:limit] if limit else items

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

    # ------------------------------------------------------------------
    # 상태 변경
    # ------------------------------------------------------------------
    def delete(self, invention_id: str) -> None:
        self.repo.delete(self._require(invention_id))

    def set_archived(self, invention_id: str, archived: bool) -> Invention:
        invention = self._require(invention_id)
        invention.is_archived = archived
        self.session.flush()
        return invention

    def toggle_favorite(self, invention_id: str) -> Invention:
        invention = self._require(invention_id)
        invention.is_favorite = not invention.is_favorite
        self.session.flush()
        return invention

    # ------------------------------------------------------------------
    # 버전
    # ------------------------------------------------------------------
    def save_revision(self, invention_id: str, change_note: str | None = None) -> InventionRevision:
        return self._snapshot(self._require(invention_id), change_note=change_note)

    def list_revisions(self, invention_id: str) -> list[InventionRevision]:
        return self.repo.list_revisions(invention_id)

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------
    def _require(self, invention_id: str) -> Invention:
        invention = self.repo.get(invention_id)
        if invention is None:
            raise LookupError(f"발명을 찾을 수 없습니다: {invention_id}")
        return invention

    def _snapshot(
        self, invention: Invention, change_note: str | None = None
    ) -> InventionRevision:
        revision_no = self.repo.next_revision_no(invention.id)
        revision = InventionRevision(
            invention_id=invention.id,
            revision_no=revision_no,
            snapshot_json=invention_to_dict(invention),
            change_note=change_note,
        )
        invention.version = revision_no
        return self.repo.add_revision(revision)
