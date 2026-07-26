"""AI가 만든 결과를 원본과 분리해서 관리하는 서비스.

예: 원본 아이디어 → AI 분석 → AI 개선안 → 사용자 수정 → 최종 발명 내용.
각 단계가 InventionAIResult 레코드 하나다. `apply()`를 호출해야만 발명의
실제 필드(예: refined_content)로 내용이 복사된다 — 만들어지는 시점에는
발명 본문에 어떤 영향도 주지 않는다.

특허 비교 초안(PatentService.save_ai_comparison_draft/apply_ai_comparison_draft)과
같은 '초안 → 검토 → 적용' 패턴을, 발명 본문 차원으로 일반화한 것이다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import InventionAIResult
from src.timeline.service import TimelineService

# 자유 문자열 — 새 종류를 추가해도 스키마 변경이 필요 없다.
RESULT_KINDS = {
    "summary": "아이디어 정리",
    "gap_analysis": "부족한 부분 찾기",
    "improvement": "개선안 제안",
    "differentiation": "차별점 찾기",
    "derived_idea": "파생 아이디어 제안",
}

# kind별로 적용했을 때 기본으로 채울 발명 필드
_DEFAULT_TARGET_FIELD = {
    "summary": "refined_content",
    "gap_analysis": "review_notes",
    "improvement": "core_principle",
    "differentiation": "differentiation",
    "derived_idea": "review_notes",
}


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
    ) -> InventionAIResult:
        result = InventionAIResult(
            invention_id=invention_id,
            kind=kind,
            content=content,
            source_field=source_field,
            provider=provider,
        )
        self.session.add(result)
        self.session.flush()
        return result

    def list_for_invention(self, invention_id: str) -> list[InventionAIResult]:
        stmt = (
            select(InventionAIResult)
            .where(InventionAIResult.invention_id == invention_id)
            .order_by(InventionAIResult.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def list_pending(self, invention_id: str) -> list[InventionAIResult]:
        return [r for r in self.list_for_invention(invention_id) if r.applied_at is None]

    def apply(self, result_id: str, target_field: str | None = None) -> InventionAIResult:
        """사용자가 검토 후 반영을 눌렀을 때만 발명 필드에 내용을 복사한다."""
        result = self.session.get(InventionAIResult, result_id)
        if result is None:
            raise LookupError(f"AI 결과를 찾을 수 없습니다: {result_id}")

        field = target_field or _DEFAULT_TARGET_FIELD.get(result.kind, "review_notes")

        # 순환 import를 피하려고 지연 import한다. update_fields()를 거치지
        # 않고 필드를 직접 바꾸는 이유: update_fields는 일반적인
        # "content_updated" Timeline을 남기는데, 여기서는 "AI 결과를
        # 반영했다"는 더 구체적인 사건 하나만 남기고 싶기 때문이다.
        from src.database.models import Invention

        invention = self.session.get(Invention, result.invention_id)
        if invention is None:
            raise LookupError(f"발명을 찾을 수 없습니다: {result.invention_id}")

        existing = getattr(invention, field) or ""
        merged = f"{existing}\n\n{result.content}".strip() if existing else result.content
        setattr(invention, field, merged)
        self.session.flush()

        result.applied_at = datetime.utcnow()
        result.applied_to_field = field
        self.session.flush()

        TimelineService(self.session).log(
            result.invention_id,
            "ai_result_applied",
            description=f"{RESULT_KINDS.get(result.kind, result.kind)} → {field}",
        )
        return result

    def discard(self, result_id: str) -> None:
        result = self.session.get(InventionAIResult, result_id)
        if result is not None:
            self.session.delete(result)
