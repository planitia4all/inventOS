"""ConversationImport DB 접근 계층.

UI와 서비스가 SQLAlchemy 쿼리를 직접 쓰지 않도록, 이 파일에만 쿼리를
둔다 — 기존 `src/inventions/repository.py`와 같은 규칙이다.

여기에는 **검증 규칙이 없다.** 길이 제한·중복 판정·회차 재시도 같은
판단은 전부 `service.py`가 한다. 저장소는 시키는 대로 읽고 쓴다.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import ConversationImport


class ConversationImportRepository:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # 쓰기
    # ------------------------------------------------------------------
    def add(self, record: ConversationImport) -> ConversationImport:
        self.session.add(record)
        # commit이 아니라 flush다 — 커밋 시점은 호출한 쪽(서비스/UI)이
        # 정한다. 그래야 여러 작업을 한 트랜잭션으로 묶을 수 있다.
        self.session.flush()
        return record

    # ------------------------------------------------------------------
    # 읽기
    # ------------------------------------------------------------------
    def get(self, import_id: str) -> ConversationImport | None:
        """삭제 여부와 무관하게 가져온다.

        Soft Delete된 대화도 요약 체인 검증의 근거 데이터로 읽어야 하므로
        (§12), 저장소 수준에서 숨기지 않는다.
        """
        return self.session.get(ConversationImport, import_id)

    def list_for_invention(
        self, invention_id: str, *, include_deleted: bool = False
    ) -> list[ConversationImport]:
        """회차 오름차순. 기본적으로 삭제된 대화는 빼고 돌려준다."""
        stmt = select(ConversationImport).where(
            ConversationImport.invention_id == invention_id
        )
        if not include_deleted:
            stmt = stmt.where(ConversationImport.is_deleted.is_(False))
        stmt = stmt.order_by(ConversationImport.sequence_no)
        return list(self.session.scalars(stmt))

    def get_latest_for_invention(
        self, invention_id: str, *, include_deleted: bool = False
    ) -> ConversationImport | None:
        """가장 최근 회차. 요약 체인의 다음 고리를 이을 때 쓴다."""
        stmt = select(ConversationImport).where(
            ConversationImport.invention_id == invention_id
        )
        if not include_deleted:
            stmt = stmt.where(ConversationImport.is_deleted.is_(False))
        stmt = stmt.order_by(ConversationImport.sequence_no.desc()).limit(1)
        return self.session.scalars(stmt).first()

    def next_sequence_no(self, invention_id: str) -> int:
        """다음 회차 번호.

        **삭제된 대화까지 포함해서** 최대값 + 1을 계산한다. Soft Delete된
        행이 그대로 남아 있으므로 회차 번호가 재사용되지 않는다 — 복원했을
        때 원래 자리로 돌아가야 하기 때문이다.
        """
        stmt = select(ConversationImport.sequence_no).where(
            ConversationImport.invention_id == invention_id
        )
        numbers = list(self.session.scalars(stmt))
        return max(numbers, default=0) + 1

    def find_by_hash(
        self, raw_content_hash: str, *, invention_id: str | None = None
    ) -> list[ConversationImport]:
        """같은 원문 해시를 가진 대화를 찾는다 (중복 검사 1단계, §6.4).

        삭제된 대화는 제외한다 — 휴지통에 있는 것과 같은 내용을 다시
        넣는 것은 중복이 아니라 복구 시도에 가깝다.
        """
        stmt = select(ConversationImport).where(
            ConversationImport.raw_content_hash == raw_content_hash,
            ConversationImport.is_deleted.is_(False),
        )
        if invention_id is not None:
            stmt = stmt.where(ConversationImport.invention_id == invention_id)
        return list(self.session.scalars(stmt.order_by(ConversationImport.imported_at)))

    def list_following(self, import_id: str) -> list[ConversationImport]:
        """이 대화를 요약 체인의 이전 고리로 삼는 대화들 (삭제 영향 범위)."""
        stmt = select(ConversationImport).where(
            ConversationImport.previous_conversation_import_id == import_id
        )
        return list(self.session.scalars(stmt.order_by(ConversationImport.sequence_no)))

    def count_for_invention(self, invention_id: str, *, include_deleted: bool = False) -> int:
        stmt = select(ConversationImport.id).where(
            ConversationImport.invention_id == invention_id
        )
        if not include_deleted:
            stmt = stmt.where(ConversationImport.is_deleted.is_(False))
        return len(list(self.session.scalars(stmt)))
