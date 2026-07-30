"""ConversationImport 저장 서비스 (Conversation Engine 1단계).

이 계층이 하는 일은 **저장과 검증뿐이다.** 대화를 파싱하지도, AI를
호출하지도, 발명 본문에 반영하지도 않는다 — 전부 다음 단계 몫이다.

목표는 하나다: 0단계에서 확정한 분석 계약(`analysis_schema`)과 대화
원문을 **데이터 손실 없이** SQLite에 넣었다 뺐다 할 수 있게 만드는 것.

설계 문서 `docs/conversation-engine-design.md` §5.2.2, §6, §16, §28.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.conversations.analysis_schema import (
    AnalysisDocument,
    dumps_analysis,
    loads_analysis,
)
from src.conversations.constants import (
    ANALYSIS_STATUS_ANALYZED,
    ANALYSIS_STATUS_PENDING,
    ANALYSIS_STATUSES,
    CHAIN_BEFORE_HASH_MISMATCH,
    CHAIN_MISSING_AFTER_SUMMARY,
    CHAIN_MISSING_PREVIOUS,
    CHAIN_NEEDS_REGENERATION,
    CHAIN_VALID,
    CURRENT_PROMPT_VERSION,
    CURRENT_SCHEMA_VERSION,
    DUPLICATE_NEW,
    DUPLICATE_OTHER_INVENTION,
    DUPLICATE_SAME_INVENTION,
    INITIAL_SYNONYM_DICT_VERSION,
    MAX_RAW_CONTENT_CHARS,
    MIN_RAW_CONTENT_CHARS,
    SUMMARY_STATUS_NEEDS_REGENERATION,
    SUMMARY_STATUS_NOT_GENERATED,
    SUMMARY_STATUS_VALID,
    SUMMARY_STATUSES,
)
from src.conversations.hashing import hash_raw_content, hash_summary_text
from src.conversations.repository import ConversationImportRepository
from src.database.models import ConversationImport, Invention

logger = logging.getLogger(__name__)

# 회차 번호는 잠금 없이 max+1로 계산하므로, 같은 발명에 동시에 저장하면
# 같은 번호가 나올 수 있다. UNIQUE 제약이 실제 중복은 막아 주니, 부딪히면
# 번호를 다시 계산해서 재시도한다 (기존 발명번호 생성과 같은 방식).
_SEQUENCE_RETRY_LIMIT = 5


class ConversationImportError(RuntimeError):
    """대화를 저장할 수 없을 때의 사용자 표시용 오류."""


class RawContentTooShortError(ConversationImportError):
    pass


class RawContentTooLongError(ConversationImportError):
    pass


@dataclass
class DuplicateCheck:
    """원문 해시 기반 중복 검사 결과 (§6.4 1단계).

    **저장을 막지 않는다.** 사용자가 같은 대화를 일부러 다시 넣고 싶을
    수도 있어서, DB에도 UNIQUE 제약을 걸지 않았다. 화면에서 경고를
    띄우기 위한 정보다.
    """

    result: str = DUPLICATE_NEW
    same_invention: list[str] = field(default_factory=list)
    other_invention: list[str] = field(default_factory=list)

    @property
    def is_duplicate(self) -> bool:
        return self.result != DUPLICATE_NEW


@dataclass
class ChainCheck:
    """대화 한 건의 요약 체인 검증 결과 (§5.2.2).

    `status`는 `constants.CHAIN_*` 중 하나. AI 호출 없이 계산한다.
    """

    import_id: str
    sequence_no: int
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == CHAIN_VALID


@dataclass
class DeleteImpact:
    """대화를 삭제하면 무엇이 영향을 받는지 미리 보여주기 위한 정보 (§28.2)."""

    import_id: str
    sequence_no: int
    is_applied: bool
    following_sequence_nos: list[int] = field(default_factory=list)
    created_revision_id: str | None = None
    created_event_id: str | None = None


class ConversationImportService:
    """대화 원문과 분석 JSON의 저장/조회/삭제.

    세션은 받아서 쓰되 **커밋하지 않는다** — 커밋 시점은 호출하는 쪽이
    정한다(기존 서비스들과 같은 규칙). 저장 도중 실패하면 호출한 쪽이
    rollback해서 아무 행도 남지 않게 한다.
    """

    def __init__(self, session: Session):
        self.session = session
        self.repo = ConversationImportRepository(session)

    # ------------------------------------------------------------------
    # 검증
    # ------------------------------------------------------------------
    @staticmethod
    def validate_raw_content(raw_content: str) -> None:
        """분량 제한을 확인한다 (§9).

        **길이 기준은 Python 문자열 길이(유니코드 코드포인트 수)다.**
        바이트 수가 아니다 — 한글은 UTF-8에서 3바이트라, 바이트로 재면
        같은 분량의 한글 대화가 영어 대화보다 3배 빨리 막힌다.

        원문을 **자동으로 자르지 않는다.** 어디를 버릴지는 사용자만
        결정할 수 있다.
        """
        length = len(raw_content or "")
        if length < MIN_RAW_CONTENT_CHARS:
            raise RawContentTooShortError(
                f"대화가 너무 짧아 분석하기 어렵습니다 "
                f"(현재 {length:,}자 / 최소 {MIN_RAW_CONTENT_CHARS:,}자)."
            )
        if length > MAX_RAW_CONTENT_CHARS:
            raise RawContentTooLongError(
                f"대화가 너무 깁니다 "
                f"(현재 {length:,}자 / 최대 {MAX_RAW_CONTENT_CHARS:,}자). "
                "여러 번에 나누어 붙여넣어 주세요 — 내용을 자동으로 자르지 않습니다."
            )

    def check_duplicate(self, invention_id: str, raw_content: str) -> DuplicateCheck:
        """같은 원문이 이미 있는지 본다. 저장을 막지는 않는다."""
        matches = self.repo.find_by_hash(hash_raw_content(raw_content))
        same = [m.id for m in matches if m.invention_id == invention_id]
        other = [m.id for m in matches if m.invention_id != invention_id]
        if same:
            result = DUPLICATE_SAME_INVENTION
        elif other:
            result = DUPLICATE_OTHER_INVENTION
        else:
            result = DUPLICATE_NEW
        return DuplicateCheck(result=result, same_invention=same, other_invention=other)

    # ------------------------------------------------------------------
    # 생성
    # ------------------------------------------------------------------
    def create(
        self,
        invention_id: str,
        raw_content: str,
        *,
        title: str = "",
        source_type: str = "other",
        source_name: str | None = None,
        conversation_date: date | None = None,
        link_previous: bool = True,
        skip_length_check: bool = False,
    ) -> ConversationImport:
        """대화 한 건을 저장한다.

        회차 계산 · 원문 · 해시 · 분석 JSON 자리 · 이전 대화 연결이 **한
        트랜잭션 안에서** 끝난다. 중간에 실패하면 아무 행도 남지 않는다.

        `created_event_id`는 이 단계에서 항상 NULL이다 — Timeline 연결은
        대화를 실제로 발명에 반영하는 다음 단계에서 채운다.
        """
        if not skip_length_check:
            self.validate_raw_content(raw_content)

        # FK가 막아 주기는 하지만, 그 전에 읽을 수 있는 메시지로 알려 준다.
        if self.session.get(Invention, invention_id) is None:
            raise ConversationImportError(
                f"발명을 찾을 수 없어 대화를 저장하지 못했습니다: {invention_id}"
            )

        previous = (
            self.repo.get_latest_for_invention(invention_id) if link_previous else None
        )

        last_error: IntegrityError | None = None
        for _ in range(_SEQUENCE_RETRY_LIMIT):
            record = ConversationImport(
                invention_id=invention_id,
                sequence_no=self.repo.next_sequence_no(invention_id),
                title=(title or "").strip(),
                source_type=source_type,
                source_name=source_name,
                conversation_date=conversation_date,
                raw_content=raw_content,
                raw_content_hash=hash_raw_content(raw_content),
                raw_content_length=len(raw_content or ""),
                analysis_status=ANALYSIS_STATUS_PENDING,
                analysis_json=None,
                analysis_schema_version=CURRENT_SCHEMA_VERSION,
                analysis_version=0,
                prompt_version=CURRENT_PROMPT_VERSION,
                synonym_dict_version=INITIAL_SYNONYM_DICT_VERSION,
                previous_conversation_import_id=previous.id if previous else None,
                rolling_summary_before_hash=(
                    previous.rolling_summary_after_hash if previous else None
                ),
                summary_status=SUMMARY_STATUS_NOT_GENERATED,
            )
            try:
                # SAVEPOINT로 감싼다 — 회차가 부딪혔을 때 이 INSERT만
                # 되돌리고, 호출한 쪽이 이미 열어 둔 트랜잭션은 살려 둔다.
                with self.session.begin_nested():
                    self.repo.add(record)
                return record
            except IntegrityError as exc:
                last_error = exc
                logger.warning("대화 회차 충돌을 감지해 다시 계산합니다: %s", exc)

        raise ConversationImportError(
            "대화 회차 번호를 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."
        ) from last_error

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------
    def get(self, import_id: str) -> ConversationImport | None:
        return self.repo.get(import_id)

    def list_for_invention(
        self, invention_id: str, *, include_deleted: bool = False
    ) -> list[ConversationImport]:
        return self.repo.list_for_invention(invention_id, include_deleted=include_deleted)

    def get_latest_for_invention(self, invention_id: str) -> ConversationImport | None:
        return self.repo.get_latest_for_invention(invention_id)

    def load_document(self, record: ConversationImport) -> AnalysisDocument:
        """저장된 `analysis_json`을 문서로 되돌린다.

        깨진 JSON이어도 예외를 던지지 않는다 — 목록을 여는 것만으로 앱이
        멈추면 안 된다. 그 경우 `document.is_unmigrated`가 True이고 원본
        문자열은 보존되어 있다.
        """
        return loads_analysis(record.analysis_json)

    def set_previous(self, import_id: str, previous_id: str | None) -> ConversationImport:
        """요약 체인의 이전 고리를 다시 연결한다.

        일반 FK로는 막을 수 없는 두 가지를 여기서 막는다.

        - **자기 자신 연결** — DB의 CHECK 제약도 막지만, 사용자에게는
          읽을 수 있는 메시지로 알려 준다.
        - **다른 발명의 대화 연결** — FK 입장에서는 완전히 유효한 참조라
          DB가 통과시킨다. 그대로 두면 A 발명의 요약 체인이 B 발명의
          내용 위에 얹히게 되어, 조용히 남의 맥락이 섞인다.
        """
        record = self._require(import_id)
        if previous_id is None:
            record.previous_conversation_import_id = None
            record.rolling_summary_before_hash = None
            self.session.flush()
            return record

        if previous_id == import_id:
            raise ConversationImportError(
                "대화를 자기 자신의 이전 대화로 연결할 수 없습니다."
            )
        previous = self.repo.get(previous_id)
        if previous is None:
            raise ConversationImportError(
                f"이전 대화를 찾을 수 없습니다: {previous_id}"
            )
        if previous.invention_id != record.invention_id:
            raise ConversationImportError(
                "다른 발명의 대화를 이전 대화로 연결할 수 없습니다 "
                "— 요약 체인은 발명 안에서만 이어집니다."
            )

        record.previous_conversation_import_id = previous.id
        record.rolling_summary_before_hash = previous.rolling_summary_after_hash
        self.session.flush()
        return record

    # ------------------------------------------------------------------
    # 분석 결과 저장
    # ------------------------------------------------------------------
    def update_analysis(
        self,
        import_id: str,
        document: AnalysisDocument,
        *,
        status: str = ANALYSIS_STATUS_ANALYZED,
        provider: str | None = None,
        model: str | None = None,
    ) -> ConversationImport:
        """분석 문서를 저장하고, 문서 안의 메타데이터를 컬럼에 동기화한다.

        `analysis_version` / `schema_version` / `prompt_version` /
        `synonym_dict_version`은 **문서가 정본이고 컬럼은 사본이다.**
        컬럼은 SQL로 걸러 보기 위한 것이므로, 여기서 한 번에 맞춰 둔다.
        """
        if status not in ANALYSIS_STATUSES:
            raise ValueError(f"알 수 없는 analysis_status: {status!r}")

        record = self._require(import_id)
        if provider or model:
            document.set_meta(provider=provider, model=model)

        record.analysis_json = dumps_analysis(document)
        record.analysis_status = status
        record.analysis_schema_version = document.schema_version
        record.analysis_version = document.analysis_version
        record.prompt_version = document.prompt_version
        record.synonym_dict_version = document.synonym_dict_version
        record.provider = document.provider
        record.model = document.model
        self.session.flush()
        return record

    def update_summary(
        self,
        import_id: str,
        summary_text: str | None,
        *,
        status: str = SUMMARY_STATUS_VALID,
    ) -> ConversationImport:
        """누적 요약과 그 해시를 저장한다.

        해시는 요약 **원문 그대로** 계산한다(줄바꿈·BOM·앞뒤 공백만 정리).
        1단계에서는 요약을 실제로 생성하지 않으므로, 테스트와 향후 서비스가
        쓰는 저장 경로만 확정해 둔다.
        """
        if status not in SUMMARY_STATUSES:
            raise ValueError(f"알 수 없는 summary_status: {status!r}")

        record = self._require(import_id)
        record.rolling_summary_after = summary_text
        record.rolling_summary_after_hash = hash_summary_text(summary_text)
        record.summary_status = status
        self.session.flush()
        return record

    # ------------------------------------------------------------------
    # 요약 체인 검증 (§10) — AI 호출 없음
    # ------------------------------------------------------------------
    def validate_summary_chain(
        self, invention_id: str, *, include_deleted: bool = False
    ) -> list[ChainCheck]:
        """발명의 대화 요약 체인이 끊기지 않았는지 회차 순서대로 확인한다.

        판정 규칙

        - 첫 회차: `previous`가 없고 `before_hash`도 없어야 정상
        - N회차: `previous`가 (N-1)회차를 가리키고, `before_hash`가
          (N-1)회차의 `after_hash`와 같아야 정상
        - 요약이 아직 없으면 `needs_regeneration`으로 본다 — 오류가
          아니라 "아직 만들지 않았다"는 뜻이다

        삭제된 대화는 기본적으로 목록에서 빠지지만, **근거 데이터로는
        읽는다** — 중간 회차가 삭제되면 그 뒤 회차는 끊긴 것이 아니라
        `needs_regeneration`이다 (§12).
        """
        records = self.repo.list_for_invention(
            invention_id, include_deleted=include_deleted
        )
        results: list[ChainCheck] = []
        previous_alive: ConversationImport | None = None

        for record in records:
            results.append(self._check_one(record, previous_alive))
            if not record.is_deleted:
                previous_alive = record
        return results

    def _check_one(
        self, record: ConversationImport, previous_alive: ConversationImport | None
    ) -> ChainCheck:
        def result(status: str, detail: str = "") -> ChainCheck:
            return ChainCheck(record.id, record.sequence_no, status, detail)

        # --- 첫 회차 ---
        if previous_alive is None:
            if record.previous_conversation_import_id is None:
                if record.rolling_summary_before_hash:
                    return result(
                        CHAIN_BEFORE_HASH_MISMATCH,
                        "첫 회차인데 이전 요약 해시가 남아 있습니다.",
                    )
                return self._check_after(record, result)
            # 원래 앞에 대화가 있었는데 그게 삭제된 경우.
            linked = self.repo.get(record.previous_conversation_import_id)
            if linked is None:
                return result(
                    CHAIN_MISSING_PREVIOUS,
                    "이전 대화 레코드를 찾을 수 없습니다.",
                )
            return result(
                CHAIN_NEEDS_REGENERATION,
                f"{linked.sequence_no}회차가 삭제되어 요약을 다시 만들어야 합니다.",
            )

        # --- N회차 ---
        if record.previous_conversation_import_id is None:
            return result(
                CHAIN_MISSING_PREVIOUS,
                f"{previous_alive.sequence_no}회차 뒤인데 이전 대화가 연결돼 있지 않습니다.",
            )
        if record.previous_conversation_import_id != previous_alive.id:
            linked = self.repo.get(record.previous_conversation_import_id)
            if linked is None:
                return result(
                    CHAIN_MISSING_PREVIOUS, "이전 대화 레코드를 찾을 수 없습니다."
                )
            # 가리키는 대화가 삭제됐다 → 요약만 다시 만들면 된다.
            return result(
                CHAIN_NEEDS_REGENERATION,
                f"{linked.sequence_no}회차가 삭제되어 요약을 다시 만들어야 합니다.",
            )
        if record.rolling_summary_before_hash != previous_alive.rolling_summary_after_hash:
            return result(
                CHAIN_BEFORE_HASH_MISMATCH,
                f"{previous_alive.sequence_no}회차의 요약이 바뀌었습니다 "
                "— 이 회차부터 요약을 다시 만들어야 합니다.",
            )
        return self._check_after(record, result)

    @staticmethod
    def _check_after(record: ConversationImport, result) -> ChainCheck:
        if record.summary_status == SUMMARY_STATUS_NEEDS_REGENERATION:
            return result(CHAIN_NEEDS_REGENERATION, "재생성 표시가 되어 있습니다.")
        if not record.rolling_summary_after:
            return result(CHAIN_MISSING_AFTER_SUMMARY, "누적 요약이 아직 없습니다.")
        return result(CHAIN_VALID)

    # ------------------------------------------------------------------
    # 삭제 / 복원 (§28)
    # ------------------------------------------------------------------
    def delete_impact(self, import_id: str) -> DeleteImpact:
        """삭제하기 전에 무엇이 영향을 받는지 보여준다."""
        record = self._require(import_id)
        following = [
            other.sequence_no
            for other in self.repo.list_following(import_id)
            if not other.is_deleted
        ]
        return DeleteImpact(
            import_id=record.id,
            sequence_no=record.sequence_no,
            is_applied=record.applied_at is not None,
            following_sequence_nos=following,
            created_revision_id=record.created_revision_id,
            created_event_id=record.created_event_id,
        )

    def soft_delete(self, import_id: str) -> ConversationImport:
        """휴지통에 넣는다 — 행도 회차 번호도 그대로 남는다.

        뒤따르는 대화의 요약은 이제 없는 회차 위에 얹혀 있으므로
        `needs_regeneration`으로 표시한다. **요약 내용을 지우지는
        않는다** — 복원하면 그대로 다시 유효해지기 때문이다.
        """
        record = self._require(import_id)
        if record.is_deleted:
            return record

        record.is_deleted = True
        record.deleted_at = datetime.utcnow()
        self._mark_following_for_regeneration(record)
        self.session.flush()
        return record

    def restore(self, import_id: str) -> ConversationImport:
        """같은 자리·같은 회차로 되살린다.

        뒤따르는 대화는 다시 `needs_regeneration`으로 표시한다 — 체인이
        한 번 흔들렸으므로, 요약이 지금도 맞는지는 다시 만들어 봐야
        확인할 수 있다.
        """
        record = self._require(import_id)
        if not record.is_deleted:
            return record

        record.is_deleted = False
        record.deleted_at = None
        self._mark_following_for_regeneration(record)
        self.session.flush()
        return record

    def _mark_following_for_regeneration(self, record: ConversationImport) -> None:
        for other in self.repo.list_following(record.id):
            if other.is_deleted:
                continue
            if other.summary_status in (
                SUMMARY_STATUS_VALID,
                SUMMARY_STATUS_NOT_GENERATED,
            ):
                other.summary_status = SUMMARY_STATUS_NEEDS_REGENERATION

    # ------------------------------------------------------------------
    def _require(self, import_id: str) -> ConversationImport:
        record = self.repo.get(import_id)
        if record is None:
            raise ConversationImportError(f"대화를 찾을 수 없습니다: {import_id}")
        return record
