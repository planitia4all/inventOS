"""발명이 어떻게 발전했는지 자동으로 기록하는 Timeline 서비스."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import InventionEvent

# 자유 문자열이지만 UI에서 아이콘/문구를 붙이기 위한 참고용 목록.
# 새 종류를 추가해도 이 목록 밖의 값이 저장/표시되는 데는 문제가 없다.
EVENT_LABELS: dict[str, str] = {
    "created": "아이디어 생성",
    "original_revised": "원본 아이디어 수정",
    "content_updated": "발명 내용 수정",
    "status_changed": "상태 변경",
    "tags_changed": "태그 변경",
    "attachment_added": "첨부파일 추가",
    "attachment_removed": "첨부파일 삭제",
    "prior_art_linked": "비슷한 기술 연결",
    "prior_art_updated": "비슷한 기술 비교 기록 수정",
    "prior_art_unlinked": "비슷한 기술 연결 해제",
    "ai_result_applied": "AI 결과 반영",
    "experiment_recorded": "실험 기록 추가",
    "experiment_updated": "실험 기록 수정",
    "experiment_deleted": "실험 기록 삭제",
    "derived_child_created": "파생 아이디어 생성",
    "derived_from_parent": "원래 아이디어에서 파생됨",
    "archived": "보관함으로 이동",
    "unarchived": "보관 해제",
    "markdown_exported": "Markdown 내보내기",
}


class TimelineService:
    def __init__(self, session: Session):
        self.session = session

    def log(
        self,
        invention_id: str,
        event_type: str,
        title: str | None = None,
        description: str | None = None,
        meta: dict | None = None,
    ) -> InventionEvent:
        event = InventionEvent(
            invention_id=invention_id,
            event_type=event_type,
            title=title or EVENT_LABELS.get(event_type, event_type),
            description=description,
            meta_json=meta,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def list_for_invention(self, invention_id: str) -> list[InventionEvent]:
        stmt = (
            select(InventionEvent)
            .where(InventionEvent.invention_id == invention_id)
            .order_by(InventionEvent.occurred_at.asc())
        )
        return list(self.session.scalars(stmt))
