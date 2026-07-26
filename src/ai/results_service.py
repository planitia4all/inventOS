"""AI가 만든 결과를 원본과 분리해서 관리하는 서비스.

예: 원본 아이디어 → AI 분석 → AI 개선안 → 사용자 수정 → 최종 발명 내용.
각 단계가 InventionAIResult 레코드 하나다. `apply()`를 호출해야만 발명의
실제 필드(예: refined_content)로 내용이 복사된다 — 만들어지는 시점에는
발명 본문에 어떤 영향도 주지 않는다.

같은 검토를 여러 번 실행해도 이전 결과를 덮어쓰지 않는다 — 매번 새
레코드를 만들어서 사용자가 여러 결과를 비교할 수 있게 한다.

특허 비교 초안(PatentService.save_ai_comparison_draft/apply_ai_comparison_draft)과
같은 '초안 → 검토 → 적용' 패턴을, 발명 본문 차원으로 일반화한 것이다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ai.review import PARTIAL_APPLY_FIELD_LABELS, REVIEW_DEFAULT_FIELD, REVIEW_KIND_LABELS
from src.database.models import InventionAIResult
from src.timeline.service import TimelineService

# 자유 문자열 — 새 종류를 추가해도 스키마 변경이 필요 없다. "AI로 검토하기"의
# 12종(src.ai.review)에 예전부터 있던 "improvement"(개선안 제안)를 더한 것.
RESULT_KINDS: dict[str, str] = {**REVIEW_KIND_LABELS, "improvement": "개선안 제안"}

# kind별로 적용했을 때 기본으로 채울 발명 필드
_DEFAULT_TARGET_FIELD: dict[str, str] = {**REVIEW_DEFAULT_FIELD, "improvement": "core_principle"}

STATUS_CREATED = "생성됨"
STATUS_APPLIED = "반영됨"
STATUS_ARCHIVED = "보관됨"
STATUS_DELETED = "삭제됨"


class AIResultService:
    def __init__(self, session: Session):
        self.session = session

    def create_draft(
        self,
        invention_id: str,
        kind: str,
        content: str,
        source_field: str | None = None,
        provider: str = "mock",
        model: str | None = None,
        input_snapshot: str | None = None,
    ) -> InventionAIResult:
        result = InventionAIResult(
            invention_id=invention_id,
            kind=kind,
            content=content,
            source_field=source_field,
            provider=provider,
            model=model,
            input_snapshot=input_snapshot,
            status=STATUS_CREATED,
        )
        self.session.add(result)
        self.session.flush()
        return result

    def list_for_invention(
        self, invention_id: str, include_deleted: bool = False
    ) -> list[InventionAIResult]:
        stmt = (
            select(InventionAIResult)
            .where(InventionAIResult.invention_id == invention_id)
            .order_by(InventionAIResult.created_at.desc())
        )
        results = list(self.session.scalars(stmt))
        if include_deleted:
            return results
        return [r for r in results if r.status != STATUS_DELETED]

    def list_pending(self, invention_id: str) -> list[InventionAIResult]:
        """아직 반영/보관/삭제되지 않아, 사용자가 판단해야 하는 결과."""
        return [
            r
            for r in self.list_for_invention(invention_id)
            if r.applied_at is None and r.status not in (STATUS_ARCHIVED, STATUS_DELETED)
        ]

    def apply(
        self,
        result_id: str,
        target_field: str | None = None,
        target_fields: list[str] | None = None,
    ) -> InventionAIResult:
        """사용자가 검토 후 반영을 눌렀을 때만 발명 필드에 내용을 복사한다.

        `target_fields`를 넘기면 그 필드 전부에 같은 내용을 채운다("일부만
        반영" — 항목 단위 선택). 아무것도 넘기지 않으면 kind별 기본 필드
        하나에 채운다("전체 반영").

        반영 전에는 항상 현재 내용을 InventionRevision으로 스냅샷하고,
        반영에 성공한 뒤에만 Timeline에 기록한다 — 실패하면(예: 발명을
        찾을 수 없음) 세션 전체가 롤백되어 절반만 저장되는 일이 없다.
        """
        result = self.session.get(InventionAIResult, result_id)
        if result is None:
            raise LookupError(f"AI 결과를 찾을 수 없습니다: {result_id}")

        if target_fields:
            fields = list(dict.fromkeys(target_fields))
        elif target_field:
            fields = [target_field]
        else:
            fields = [_DEFAULT_TARGET_FIELD.get(result.kind, "review_notes")]

        # 순환 import를 피하려고 지연 import한다. update_fields()를 거치지
        # 않고 필드를 직접 바꾸는 이유: update_fields는 일반적인
        # "content_updated" Timeline을 남기는데, 여기서는 "AI 검토 결과를
        # 반영했다"는 더 구체적인 사건 하나만 남기고 싶기 때문이다.
        from src.database.models import Invention
        from src.inventions.service import InventionService

        invention = self.session.get(Invention, result.invention_id)
        if invention is None:
            raise LookupError(f"발명을 찾을 수 없습니다: {result.invention_id}")

        InventionService(self.session).save_revision(
            invention.id, change_note=f"AI 검토 결과 반영 전 자동 저장 ({RESULT_KINDS.get(result.kind, result.kind)})"
        )

        for field in fields:
            existing = getattr(invention, field) or ""
            merged = f"{existing}\n\n{result.content}".strip() if existing else result.content
            setattr(invention, field, merged)
        self.session.flush()

        result.applied_at = datetime.utcnow()
        result.applied_to_field = fields[0]
        result.applied_fields = fields
        result.status = STATUS_APPLIED
        self.session.flush()

        field_labels = ", ".join(PARTIAL_APPLY_FIELD_LABELS.get(f, f) for f in fields)
        TimelineService(self.session).log(
            result.invention_id,
            "ai_result_applied",
            description=f"{RESULT_KINDS.get(result.kind, result.kind)} → {field_labels}",
            meta={"kind": result.kind, "applied_fields": fields},
        )
        return result

    def archive(self, result_id: str) -> InventionAIResult | None:
        """반영하지 않고 참고용으로만 남겨 둔다 ('검토 결과로 보관')."""
        result = self.session.get(InventionAIResult, result_id)
        if result is not None:
            result.status = STATUS_ARCHIVED
            self.session.flush()
        return result

    def discard(self, result_id: str) -> None:
        """소프트 삭제 — 행을 지우지 않고 상태만 '삭제됨'으로 바꾼다.

        InventOS는 생각이 어떻게 발전했는지 기록하는 것이 목적이라, 사용자가
        지운 AI 결과도 기본 목록에서만 숨기고 실제로는 보존한다.
        """
        result = self.session.get(InventionAIResult, result_id)
        if result is not None:
            result.status = STATUS_DELETED
            self.session.flush()
