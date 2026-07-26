"""발명 비즈니스 로직.

UI는 이 계층만 호출하고, ORM/DB 세부사항을 직접 다루지 않는다.

핵심 관점: 발명은 정적 문서가 아니라 시간에 따라 발전하는 객체다. 그래서
이 서비스는 내용을 바꿀 때마다 (1) 원본 보존이 필요하면 InventionRevision
스냅샷을 남기고, (2) 무슨 일이 있었는지 TimelineService로 기록한다.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.database.models import Invention, InventionRevision
from src.inventions.repository import InventionRepository
from src.inventions.schemas import DEFAULT_STATUS, InventionInput, QuickIdeaInput
from src.search.fts import SearchIndexService
from src.tags.service import TagService
from src.timeline.service import TimelineService

logger = logging.getLogger(__name__)

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
        "status": invention.status,
        "is_favorite": invention.is_favorite,
        "is_archived": invention.is_archived,
        "parent_invention_id": invention.parent_invention_id,
        "created_at": invention.created_at.isoformat() if invention.created_at else None,
        "updated_at": invention.updated_at.isoformat() if invention.updated_at else None,
        "version": invention.version,
    }
    for name in _CONTENT_FIELDS:
        data[name] = getattr(invention, name)
    return data


class InventionService:
    def __init__(self, session: Session, settings=None):
        self.session = session
        self.settings = settings
        self.repo = InventionRepository(session)
        self.tags = TagService(session)
        self.timeline = TimelineService(session)
        self.search_index = SearchIndexService(session)

    # ------------------------------------------------------------------
    # 생성
    # ------------------------------------------------------------------
    def quick_create(self, data: QuickIdeaInput) -> Invention:
        """홈 화면의 빠른 기록. 메모만 있으면 바로 저장한다."""
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        invention = self._create(original_idea=data.memo.strip(), title=data.title)
        if data.keywords:
            self.tags.add_tags(invention.id, data.keywords)
        self.timeline.log(invention.id, "created", description=invention.title)
        self.search_index.reindex_invention(invention.id)
        return invention

    def create(self, data: InventionInput) -> Invention:
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        invention = self._create(
            original_idea=data.original_idea.strip(),
            title=data.title,
            status=data.status or DEFAULT_STATUS,
        )
        for name in _CONTENT_FIELDS:
            setattr(invention, name, getattr(data, name))
        if data.keywords:
            self.tags.add_tags(invention.id, data.keywords)
        self.session.flush()
        self.timeline.log(invention.id, "created", description=invention.title)
        self.search_index.reindex_invention(invention.id)
        return invention

    def create_child(
        self,
        parent_id: str,
        data: QuickIdeaInput,
        derivation_reason: str | None = None,
        copy_fields: list[str] | None = None,
        copy_tags: bool = False,
        copy_attachments: bool = False,
        source_experiment_id: str | None = None,
    ) -> Invention:
        """기존 아이디어에서 파생된 새 아이디어를 만든다.

        예: Separator 접합 → Graphene Fiber 방식. 기본값은 관계만 연결하고
        (copy_fields/copy_tags/copy_attachments를 모두 비워 두면), 필요한
        내용만 선택적으로 부모에서 가져올 수 있다.

        핵심 관계(부모 연결 + 양쪽 Timeline 기록)는 이 메서드 하나가 같은
        세션 안에서 전부 처리한다 — 호출하는 쪽(UI)이 `run_and_rerun`처럼
        하나의 짧은 트랜잭션으로 감싸서 실행하면, 중간에 실패했을 때 부모
        관계만 반쯤 만들어지는 일 없이 전체가 롤백된다.
        """
        parent = self._require(parent_id)
        errors = data.validate()
        if errors:
            raise ValueError("; ".join(errors))

        child = self._create(original_idea=data.memo.strip(), title=data.title)
        child.parent_invention_id = parent.id
        child.derivation_reason = derivation_reason
        child.source_experiment_id = source_experiment_id

        for field in copy_fields or []:
            if field not in _CONTENT_FIELDS:
                raise ValueError(f"복사할 수 없는 항목입니다: {field}")
            value = getattr(parent, field)
            if value:
                setattr(child, field, value)

        if data.keywords:
            self.tags.add_tags(child.id, data.keywords)
        if copy_tags:
            parent_tag_names = self.tags.tag_names(parent.id)
            if parent_tag_names:
                self.tags.add_tags(child.id, parent_tag_names)

        if copy_attachments:
            self._copy_attachments(parent.id, child.id)

        self.session.flush()

        reason_note = f" ({derivation_reason})" if derivation_reason else ""
        self.timeline.log(
            child.id,
            "derived_from_parent",
            description=f"'{parent.title}'({parent.invention_no})에서 파생됨{reason_note}",
            meta={
                "parent_invention_id": parent.id,
                "parent_invention_no": parent.invention_no,
                "parent_title": parent.title,
                "derivation_reason": derivation_reason,
            },
        )
        self.timeline.log(
            parent.id,
            "derived_child_created",
            description=f"'{child.title}'({child.invention_no}) 파생 아이디어 생성{reason_note}",
            meta={
                "child_invention_id": child.id,
                "child_invention_no": child.invention_no,
                "child_title": child.title,
                "derivation_reason": derivation_reason,
            },
        )
        self.search_index.reindex_invention(child.id)
        return child

    def _copy_attachments(self, parent_id: str, child_id: str) -> None:
        """부모의 첨부파일을 실제로 복사해 자식에 붙인다.

        파일 하나가 복사에 실패해도(예: 원본 파일이 디스크에서 사라짐)
        나머지 복사와 파생 아이디어 생성 자체는 계속 진행한다 — DB 행과
        실제 파일이 항상 함께 만들어지도록 보장하는 `AttachmentService.save()`를
        그대로 재사용하므로, 실패한 파일은 자식 쪽에 아무 흔적도 남기지 않는다.
        """
        from src.attachments.service import AttachmentError, AttachmentService

        attachment_service = AttachmentService(self.session, settings=self.settings)
        for attachment in attachment_service.list_for_invention(parent_id):
            try:
                attachment_service.copy_to_invention(attachment, child_id)
            except (AttachmentError, OSError) as exc:
                logger.warning(
                    "첨부파일 복사 실패 (parent=%s, file=%s): %s",
                    parent_id,
                    attachment.original_filename,
                    exc,
                )

    def list_children(self, invention_id: str) -> list[Invention]:
        return self.repo.list_children(invention_id)

    def _create(
        self,
        original_idea: str,
        title: str = "",
        status: str = DEFAULT_STATUS,
    ) -> Invention:
        year = datetime.now(timezone.utc).year
        invention = Invention(
            invention_no=self.repo.next_invention_no(year),
            title=(title or "").strip() or generate_title(original_idea),
            original_idea=original_idea,
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
            self.timeline.log(invention.id, "original_revised")

        invention.original_idea = new_original
        invention.title = (data.title or "").strip() or generate_title(new_original)
        old_status = invention.status
        invention.status = data.status or invention.status
        for name in _CONTENT_FIELDS:
            setattr(invention, name, getattr(data, name))
        old_tags = set(self.tags.tag_names(invention.id))
        self.tags.set_tags_for_invention(invention.id, data.keywords or [])
        self.session.flush()

        if invention.status != old_status:
            self.timeline.log(
                invention.id,
                "status_changed",
                description=f"{old_status} → {invention.status}",
            )
        new_tags = set(self.tags.tag_names(invention.id))
        if new_tags != old_tags:
            self._log_tags_changed(invention.id, new_tags)
        self.search_index.reindex_invention(invention.id)
        return invention

    def update_fields(self, invention_id: str, **fields) -> Invention:
        """상세 화면에서 일부 항목만 저장할 때 사용한다.

        원본 아이디어(original_idea)는 이 경로로 바꿀 수 없다. 원본을 고치려면
        `update_original_idea()`를 써서 이전 버전이 남도록 한다.
        """
        invention = self._require(invention_id)
        allowed = set(_CONTENT_FIELDS) | {"title", "status"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"수정할 수 없는 항목입니다: {', '.join(sorted(unknown))}")

        old_status = invention.status
        for name, value in fields.items():
            setattr(invention, name, value)
        self.session.flush()

        if "status" in fields and invention.status != old_status:
            self.timeline.log(
                invention.id,
                "status_changed",
                description=f"{old_status} → {invention.status}",
            )
        elif set(fields) - {"status", "title"}:
            self.timeline.log(invention.id, "content_updated")
        self.search_index.reindex_invention(invention.id)
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
        self.timeline.log(invention.id, "original_revised")
        self.search_index.reindex_invention(invention.id)
        return invention

    def set_tags(self, invention_id: str, names: list[str]) -> None:
        self._require(invention_id)
        old_tags = set(self.tags.tag_names(invention_id))
        self.tags.set_tags_for_invention(invention_id, names)
        new_tags = set(self.tags.tag_names(invention_id))
        if new_tags != old_tags:
            self._log_tags_changed(invention_id, new_tags)
        self.search_index.reindex_invention(invention_id)

    def _log_tags_changed(self, invention_id: str, new_tags: set[str]) -> None:
        self.timeline.log(
            invention_id,
            "tags_changed",
            description=", ".join(sorted(new_tags)) if new_tags else "(태그 없음)",
        )

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------
    def get(self, invention_id: str) -> Invention | None:
        return self.repo.get(invention_id)

    def list(self, include_archived: bool = False) -> list[Invention]:
        return self.repo.list_all(include_archived=include_archived)

    def list_recent(self, limit: int = 5) -> list[Invention]:
        """updated_at 기준 최근 항목 (하위 호환용 별칭)."""
        return self.list_recently_updated(limit=limit)

    def list_recently_created(self, limit: int = 5) -> list[Invention]:
        return self.repo.list_by_created(limit=limit)

    def list_recently_updated(self, limit: int = 5) -> list[Invention]:
        return self.repo.list_all(include_archived=False)[:limit]

    def list_in_progress(self, limit: int | None = None) -> list[Invention]:
        """'아이디어'도 '보관됨'도 아닌, 실제로 진행 중인 발명."""
        items = [
            i
            for i in self.repo.list_all(include_archived=False)
            if i.status not in (DEFAULT_STATUS, "보관됨")
        ]
        return items[:limit] if limit else items

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
            if i.status == DEFAULT_STATUS and not (i.refined_content or "").strip()
        ]
        return items[:limit] if limit else items

    def search(
        self,
        keyword: str | None = None,
        technical_field: str | None = None,
        status: str | None = None,
        include_archived: bool = False,
    ) -> list[Invention]:
        """제목/원본 메모/발명 내용/태그/첨부파일 이름을 통합 검색한다.

        FTS5 색인을 우선 쓰고, 색인에 검색어 토큰이 하나도 없으면(예:
        특수문자만 입력) 제목/원본 메모만 보는 단순 검색으로 대체한다.
        """
        if keyword and keyword.strip():
            matched_ids = self.search_index.search(keyword.strip())
            if matched_ids:
                return self.repo.search_by_ids(
                    matched_ids,
                    technical_field=technical_field,
                    status=status,
                    include_archived=include_archived,
                )
            return self.repo.search(
                keyword=keyword,
                technical_field=technical_field,
                status=status,
                include_archived=include_archived,
            )

        return self.repo.search(
            technical_field=technical_field,
            status=status,
            include_archived=include_archived,
        )

    # ------------------------------------------------------------------
    # 상태 변경
    # ------------------------------------------------------------------
    def delete(self, invention_id: str) -> None:
        self.repo.delete(self._require(invention_id))
        self.search_index.remove(invention_id)

    def set_archived(self, invention_id: str, archived: bool) -> Invention:
        invention = self._require(invention_id)
        invention.is_archived = archived
        self.session.flush()
        self.timeline.log(invention.id, "archived" if archived else "unarchived")
        return invention

    def toggle_favorite(self, invention_id: str) -> Invention:
        invention = self._require(invention_id)
        invention.is_favorite = not invention.is_favorite
        self.session.flush()
        return invention

    # ------------------------------------------------------------------
    # 버전 / Timeline
    # ------------------------------------------------------------------
    def save_revision(self, invention_id: str, change_note: str | None = None) -> InventionRevision:
        return self._snapshot(self._require(invention_id), change_note=change_note)

    def list_revisions(self, invention_id: str) -> list[InventionRevision]:
        return self.repo.list_revisions(invention_id)

    def list_timeline(self, invention_id: str):
        return self.timeline.list_for_invention(invention_id)

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
