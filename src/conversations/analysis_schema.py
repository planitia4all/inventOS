"""Conversation 분석 JSON(`analysis_json`)의 유일한 계약 계층.

이 파일의 존재 이유
-------------------
`analysis_json`을 자유 형식 dict로 다루면, 6개월 뒤에는 어느 키가 언제
생겼는지 아무도 모르는 상태가 된다. 나중에 테이블로 승격하는 것도
스키마가 정확할 때만 가능하다.

그래서 **JSON 키 문자열은 이 파일에만 존재한다.** Parser·Service·UI는
`AnalysisDocument`의 접근자만 쓴다. `tests/test_analysis_schema.py`의
AST 계약 테스트가 이 규칙을 자동으로 강제한다.

세 계층 (§26.2, §27.1)
----------------------
- ``ai_analysis``        AI(또는 Mock)가 만든 것 — 재분석 시 통째로 교체
- ``user_review``        사람이 판단한 것 — 재분석해도 보존
- ``application_result`` 실제 본문 반영 결과 — 승인과는 별개

승인(`user_review`)과 반영(`application_result`)을 나눈 이유: 사용자가
승인해도 중복으로 건너뛰거나 트랜잭션이 실패하면 본문에 들어가지
않는다. 두 개를 한 곳에 두면 "내가 승인한 게 실제로 들어갔나"를
확인할 수 없다.

불변성
------
`load_analysis()`는 입력 dict를 절대 수정하지 않는다(깊은 복사 후 작업).
문서를 바꾸는 메서드는 이름에 동사를 붙여(`set_`/`record_`/`replace_`)
변경 여부를 분명히 한다.

설계 문서: `docs/conversation-engine-design.md` §26, §27
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

from src.conversations.constants import (
    CURRENT_PROMPT_VERSION,
    CURRENT_SCHEMA_VERSION,
    INITIAL_SYNONYM_DICT_VERSION,
)

# ---------------------------------------------------------------------------
# JSON 키 — 이 클래스 밖에서 문자열로 쓰지 않는다
# ---------------------------------------------------------------------------


class AnalysisKeys:
    """analysis_json에 등장하는 모든 키 문자열.

    이 클래스가 키의 유일한 정의처다. 다른 파일에서 `data["ai_analysis"]`
    처럼 쓰면 AST 계약 테스트가 실패한다.
    """

    # 최상위
    SCHEMA_VERSION = "schema_version"
    ANALYSIS_VERSION = "analysis_version"
    PROVIDER = "provider"
    MODEL = "model"
    PROMPT_VERSION = "prompt_version"
    SYNONYM_DICT_VERSION = "synonym_dict_version"
    ANALYZED_AT = "analyzed_at"
    MESSAGES = "messages"
    OVERLAP = "overlap"
    AI_ANALYSIS = "ai_analysis"
    USER_REVIEW = "user_review"
    APPLICATION_RESULT = "application_result"
    UNMIGRATED_RAW = "_unmigrated_raw"
    EXTRA = "_extra"

    # ai_analysis 하위
    NEW_ELEMENTS = "new_elements"
    REINFORCED_ELEMENTS = "reinforced_elements"
    MODIFIED_ELEMENTS = "modified_elements"
    CONFLICTING_ELEMENTS = "conflicting_elements"
    REJECTED_ELEMENTS = "rejected_elements"
    OPEN_QUESTIONS = "open_questions"
    SOURCE_REFERENCES = "source_references"
    MERGE_PROPOSALS = "merge_proposals"

    # user_review 하위
    DECISIONS = "decisions"
    ORPHANED_DECISIONS = "orphaned_decisions"
    NOTES = "notes"

    # application_result 하위
    APPLIED_ITEMS = "applied_items"
    REVISION_ID = "revision_id"
    EVENT_IDS = "event_ids"
    APPLIED_AT = "applied_at"

    # 항목(AnalysisItem)
    ITEM_ID = "item_id"
    KIND = "kind"
    CHANGE_TYPE = "change_type"
    TARGET_FIELD = "target_field"
    TEXT = "text"
    NORMALIZED_TEXT = "normalized_text"
    ORIGIN_STANCE = "origin_stance"
    DECLARED_STATUS = "declared_status"
    DERIVED_STATUS = "derived_status"
    CONFIDENCE = "confidence"
    RATIONALE = "rationale"
    SOURCES = "sources"
    SUPERSEDES_ITEM_ID = "supersedes_item_id"
    RELATED_PREVIOUS_ITEM_ID = "related_previous_item_id"
    MATCH_TYPE = "match_type"
    SIMILARITY_SCORE = "similarity_score"
    CARRIED_OVER = "carried_over"

    # SourceReference
    CONVERSATION_IMPORT_ID = "conversation_import_id"
    SEQUENCE_NO = "sequence_no"
    MESSAGE_INDEX = "message_index"
    MESSAGE_ROLE = "message_role"
    SOURCE_START = "source_start"
    SOURCE_END = "source_end"
    SOURCE_EXCERPT = "source_excerpt"
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    REF_KIND = "ref_kind"
    REF_ID = "ref_id"

    # MessageRef
    CONTENT_HASH = "content_hash"
    ROLE = "role"

    # OverlapInfo
    OVERLAP_WITH_IMPORT_ID = "overlap_with_import_id"
    ALREADY_IMPORTED_INDICES = "already_imported_indices"
    NEWLY_ADDED_INDICES = "newly_added_indices"
    MODIFIED_INDICES = "modified_indices"
    ANALYZED_RANGE = "analyzed_range"

    # UserDecision
    DECISION = "decision"
    EDITED_TEXT = "edited_text"
    REVIEWED_AT = "reviewed_at"
    ORIGINAL_ITEM_ID = "original_item_id"
    CARRIED_FROM_ANALYSIS_VERSION = "carried_from_analysis_version"
    USER_NOTE = "user_note"

    # ApplicationEntry
    STATUS = "status"
    APPLIED_TEXT = "applied_text"
    EVENT_ID = "event_id"
    ERROR_MESSAGE = "error_message"

    # 깨진 JSON을 그대로 보존할 때 원문을 담는 자리 (`_unmigrated_raw` 안).
    CORRUPTED_TEXT = "corrupted_text"


# ai_analysis 안에서 "제안 항목" 형태를 갖는 버킷들
ITEM_BUCKETS: tuple[str, ...] = (
    AnalysisKeys.NEW_ELEMENTS,
    AnalysisKeys.REINFORCED_ELEMENTS,
    AnalysisKeys.MODIFIED_ELEMENTS,
    AnalysisKeys.CONFLICTING_ELEMENTS,
    AnalysisKeys.REJECTED_ELEMENTS,
)

# ai_analysis 안의 나머지 배열 (항목 형태가 다름)
_OTHER_AI_LISTS: tuple[str, ...] = (
    AnalysisKeys.OPEN_QUESTIONS,
    AnalysisKeys.SOURCE_REFERENCES,
    AnalysisKeys.MERGE_PROPOSALS,
)


# ---------------------------------------------------------------------------
# 값 상수
# ---------------------------------------------------------------------------


class ChangeType:
    ADDED = "added"
    MODIFIED = "modified"
    STRENGTHENED = "strengthened"
    DEPRECATED = "deprecated"
    CONFLICT = "conflict"
    UNDECIDED = "undecided"

    ALL = (ADDED, MODIFIED, STRENGTHENED, DEPRECATED, CONFLICT, UNDECIDED)


class OriginStance:
    """누가 말했는가 (§9.5). AI만 제안한 것은 자동 승격하지 않는다."""

    USER_PROPOSED = "user_proposed"
    USER_ASKED = "user_asked"
    AI_PROPOSED = "ai_proposed"
    USER_AGREED = "user_agreed"
    USER_REJECTED = "user_rejected"
    USER_ADOPTED = "user_adopted"
    USER_DEFERRED = "user_deferred"

    ALL = (
        USER_PROPOSED, USER_ASKED, AI_PROPOSED, USER_AGREED,
        USER_REJECTED, USER_ADOPTED, USER_DEFERRED,
    )


class DeclaredStatus:
    """사용자가 정한 상태 (§9.4). 시스템 계산이 절대 바꾸지 못한다."""

    PROPOSED = "proposed"
    CANDIDATE = "candidate"
    DEFERRED = "deferred"
    ADOPTED = "adopted"
    REJECTED = "rejected"
    DISPROVED_BY_EXPERIMENT = "disproved_by_experiment"
    SUPERSEDED = "superseded"

    ALL = (
        PROPOSED, CANDIDATE, DEFERRED, ADOPTED,
        REJECTED, DISPROVED_BY_EXPERIMENT, SUPERSEDED,
    )


class DerivedStatus:
    """시스템이 계산한 상태 (§9.4). 여러 개를 동시에 가질 수 있다.

    `DORMANT`(최근 미언급)는 **폐기가 아니다** — 확인해 보라는 힌트일 뿐이며
    사용자가 정한 `declared_status`를 덮어쓰지 않는다.
    """

    NEWLY_PROPOSED = "newly_proposed"
    STRENGTHENED = "strengthened"
    MODIFIED = "modified"
    DORMANT = "dormant"

    ALL = (NEWLY_PROPOSED, STRENGTHENED, MODIFIED, DORMANT)


class DecisionStatus:
    """사용자 판단 (§27.1)."""

    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    DEFERRED = "deferred"

    ALL = (UNREVIEWED, APPROVED, EDITED, REJECTED, DEFERRED)


class ApplicationStatus:
    """실제 반영 결과 (§27.1). 승인했다고 반영되는 것이 아니다."""

    APPLIED = "applied"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_EMPTY = "skipped_empty"
    FAILED_VALIDATION = "failed_validation"
    FAILED_TRANSACTION = "failed_transaction"
    NOT_SELECTED = "not_selected"

    ALL = (
        APPLIED, SKIPPED_DUPLICATE, SKIPPED_EMPTY,
        FAILED_VALIDATION, FAILED_TRANSACTION, NOT_SELECTED,
    )


class MatchType:
    """재분석 시 이전 항목과의 관계 (§27.3)."""

    EXACT = "exact"
    SIMILAR = "similar"
    NEW = "new"

    ALL = (EXACT, SIMILAR, NEW)


ACTOR_USER = "user"
ACTOR_SYSTEM = "system"


class DeclaredStatusProtectedError(RuntimeError):
    """시스템이 `declared_status`를 바꾸려 했을 때 (§9.4).

    사용자가 "채택"한 아이디어를 자동 계산이 "폐기"로 바꾸는 사고를
    구조적으로 막기 위해, 사용자 행위임을 명시해야만 바꿀 수 있다.
    """


# ---------------------------------------------------------------------------
# 안전한 타입 변환 — 잘못된 타입이 와도 예외를 던지지 않고 기록만 한다
# ---------------------------------------------------------------------------


def _as_str(value: Any, default: str, path: str, errors: list[str]) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    errors.append(f"{path}: 문자열이 아님({type(value).__name__}) → 기본값 사용")
    return default


def _as_opt_str(value: Any, path: str, errors: list[str]) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    errors.append(f"{path}: 문자열이 아님({type(value).__name__}) → None 사용")
    return None


def _as_int(value: Any, default: int, path: str, errors: list[str]) -> int:
    if value is None:
        return default
    if isinstance(value, bool):  # bool은 int의 하위형이라 먼저 걸러낸다
        errors.append(f"{path}: 정수가 아님(bool) → 기본값 사용")
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            pass
    errors.append(f"{path}: 정수가 아님({type(value).__name__}) → 기본값 사용")
    return default


def _as_float(value: Any, default: float, path: str, errors: list[str]) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        errors.append(f"{path}: 실수가 아님(bool) → 기본값 사용")
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            pass
    errors.append(f"{path}: 실수가 아님({type(value).__name__}) → 기본값 사용")
    return default


def _as_bool(value: Any, default: bool, path: str, errors: list[str]) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    errors.append(f"{path}: 불리언이 아님({type(value).__name__}) → 기본값 사용")
    return default


def _as_list(value: Any, path: str, errors: list[str]) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    errors.append(f"{path}: 배열이 아님({type(value).__name__}) → 빈 배열 사용")
    return []


def _as_dict(value: Any, path: str, errors: list[str]) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    errors.append(f"{path}: 객체가 아님({type(value).__name__}) → 빈 객체 사용")
    return {}


def _as_str_list(value: Any, path: str, errors: list[str]) -> list[str]:
    raw = _as_list(value, path, errors)
    out = []
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            out.append(entry)
        else:
            errors.append(f"{path}[{i}]: 문자열이 아님 → 제외")
    return out


def _as_int_list(value: Any, path: str, errors: list[str]) -> list[int]:
    raw = _as_list(value, path, errors)
    out = []
    for i, entry in enumerate(raw):
        if isinstance(entry, bool):
            errors.append(f"{path}[{i}]: 정수가 아님(bool) → 제외")
        elif isinstance(entry, int):
            out.append(entry)
        else:
            errors.append(f"{path}[{i}]: 정수가 아님 → 제외")
    return out


def _extras(raw: dict, known: Iterable[str]) -> dict:
    """알 수 없는 추가 필드를 보존한다 (미래 버전 호환)."""
    known_set = set(known)
    return {k: v for k, v in raw.items() if k not in known_set}


# ---------------------------------------------------------------------------
# 구조체
# ---------------------------------------------------------------------------


@dataclass
class SourceReference:
    """구조화 항목이 원문 어디에서 나왔는지 (§12).

    `source_start`/`source_end`가 -1이면 원문에서 발췌를 찾지 못한 것이다.
    그래도 대화번호·역할·메시지번호·발췌는 항상 있으므로 추적은 성립한다.
    Offset은 **Python 문자열(유니코드 코드포인트) 기준**이다.
    """

    ref_kind: str = "conversation"
    conversation_import_id: str = ""
    sequence_no: int = 0
    message_index: int = -1
    message_role: str = ""
    source_excerpt: str = ""
    source_start: int = -1
    source_end: int = -1
    confidence: int = 0
    matched: bool = False
    ambiguous: bool = False
    ref_id: str = ""
    extra: dict = field(default_factory=dict)

    _KEYS = (
        AnalysisKeys.REF_KIND, AnalysisKeys.CONVERSATION_IMPORT_ID,
        AnalysisKeys.SEQUENCE_NO, AnalysisKeys.MESSAGE_INDEX,
        AnalysisKeys.MESSAGE_ROLE, AnalysisKeys.SOURCE_EXCERPT,
        AnalysisKeys.SOURCE_START, AnalysisKeys.SOURCE_END,
        AnalysisKeys.CONFIDENCE, AnalysisKeys.MATCHED,
        AnalysisKeys.AMBIGUOUS, AnalysisKeys.REF_ID,
    )

    @classmethod
    def from_json(cls, raw: Any, path: str, errors: list[str]) -> "SourceReference":
        data = _as_dict(raw, path, errors)
        return cls(
            ref_kind=_as_str(data.get(AnalysisKeys.REF_KIND), "conversation",
                             f"{path}.{AnalysisKeys.REF_KIND}", errors),
            conversation_import_id=_as_str(
                data.get(AnalysisKeys.CONVERSATION_IMPORT_ID), "",
                f"{path}.{AnalysisKeys.CONVERSATION_IMPORT_ID}", errors),
            sequence_no=_as_int(data.get(AnalysisKeys.SEQUENCE_NO), 0,
                                f"{path}.{AnalysisKeys.SEQUENCE_NO}", errors),
            message_index=_as_int(data.get(AnalysisKeys.MESSAGE_INDEX), -1,
                                  f"{path}.{AnalysisKeys.MESSAGE_INDEX}", errors),
            message_role=_as_str(data.get(AnalysisKeys.MESSAGE_ROLE), "",
                                 f"{path}.{AnalysisKeys.MESSAGE_ROLE}", errors),
            source_excerpt=_as_str(data.get(AnalysisKeys.SOURCE_EXCERPT), "",
                                   f"{path}.{AnalysisKeys.SOURCE_EXCERPT}", errors),
            source_start=_as_int(data.get(AnalysisKeys.SOURCE_START), -1,
                                 f"{path}.{AnalysisKeys.SOURCE_START}", errors),
            source_end=_as_int(data.get(AnalysisKeys.SOURCE_END), -1,
                               f"{path}.{AnalysisKeys.SOURCE_END}", errors),
            confidence=_as_int(data.get(AnalysisKeys.CONFIDENCE), 0,
                               f"{path}.{AnalysisKeys.CONFIDENCE}", errors),
            matched=_as_bool(data.get(AnalysisKeys.MATCHED), False,
                             f"{path}.{AnalysisKeys.MATCHED}", errors),
            ambiguous=_as_bool(data.get(AnalysisKeys.AMBIGUOUS), False,
                               f"{path}.{AnalysisKeys.AMBIGUOUS}", errors),
            ref_id=_as_str(data.get(AnalysisKeys.REF_ID), "",
                           f"{path}.{AnalysisKeys.REF_ID}", errors),
            extra=_extras(data, cls._KEYS),
        )

    def to_json(self) -> dict:
        out = {
            AnalysisKeys.REF_KIND: self.ref_kind,
            AnalysisKeys.CONVERSATION_IMPORT_ID: self.conversation_import_id,
            AnalysisKeys.SEQUENCE_NO: self.sequence_no,
            AnalysisKeys.MESSAGE_INDEX: self.message_index,
            AnalysisKeys.MESSAGE_ROLE: self.message_role,
            AnalysisKeys.SOURCE_EXCERPT: self.source_excerpt,
            AnalysisKeys.SOURCE_START: self.source_start,
            AnalysisKeys.SOURCE_END: self.source_end,
            AnalysisKeys.CONFIDENCE: self.confidence,
            AnalysisKeys.MATCHED: self.matched,
            AnalysisKeys.AMBIGUOUS: self.ambiguous,
            AnalysisKeys.REF_ID: self.ref_id,
        }
        out.update(self.extra)
        return out


@dataclass
class MessageRef:
    """메시지 분리 결과 (§26.2).

    내용(text)은 담지 않는다 — 원문은 `ConversationImport.raw_content`에
    이미 완전히 있고, 여기 또 넣으면 두 사본이 어긋날 수 있다.
    """

    message_index: int = -1
    role: str = ""
    content_hash: str = ""
    source_start: int = -1
    source_end: int = -1
    source_excerpt: str = ""
    extra: dict = field(default_factory=dict)

    _KEYS = (
        AnalysisKeys.MESSAGE_INDEX, AnalysisKeys.ROLE,
        AnalysisKeys.CONTENT_HASH, AnalysisKeys.SOURCE_START,
        AnalysisKeys.SOURCE_END, AnalysisKeys.SOURCE_EXCERPT,
    )

    @classmethod
    def from_json(cls, raw: Any, path: str, errors: list[str]) -> "MessageRef":
        data = _as_dict(raw, path, errors)
        return cls(
            message_index=_as_int(data.get(AnalysisKeys.MESSAGE_INDEX), -1,
                                  f"{path}.{AnalysisKeys.MESSAGE_INDEX}", errors),
            role=_as_str(data.get(AnalysisKeys.ROLE), "",
                         f"{path}.{AnalysisKeys.ROLE}", errors),
            content_hash=_as_str(data.get(AnalysisKeys.CONTENT_HASH), "",
                                 f"{path}.{AnalysisKeys.CONTENT_HASH}", errors),
            source_start=_as_int(data.get(AnalysisKeys.SOURCE_START), -1,
                                 f"{path}.{AnalysisKeys.SOURCE_START}", errors),
            source_end=_as_int(data.get(AnalysisKeys.SOURCE_END), -1,
                               f"{path}.{AnalysisKeys.SOURCE_END}", errors),
            source_excerpt=_as_str(data.get(AnalysisKeys.SOURCE_EXCERPT), "",
                                   f"{path}.{AnalysisKeys.SOURCE_EXCERPT}", errors),
            extra=_extras(data, cls._KEYS),
        )

    def to_json(self) -> dict:
        out = {
            AnalysisKeys.MESSAGE_INDEX: self.message_index,
            AnalysisKeys.ROLE: self.role,
            AnalysisKeys.CONTENT_HASH: self.content_hash,
            AnalysisKeys.SOURCE_START: self.source_start,
            AnalysisKeys.SOURCE_END: self.source_end,
            AnalysisKeys.SOURCE_EXCERPT: self.source_excerpt,
        }
        out.update(self.extra)
        return out


@dataclass
class OverlapInfo:
    """부분 중복(재복사) 판정 결과 (§6.5)."""

    match_type: str = ""
    overlap_with_import_id: str | None = None
    already_imported_indices: list[int] = field(default_factory=list)
    newly_added_indices: list[int] = field(default_factory=list)
    modified_indices: list[int] = field(default_factory=list)
    analyzed_range: list[int] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    _KEYS = (
        AnalysisKeys.MATCH_TYPE, AnalysisKeys.OVERLAP_WITH_IMPORT_ID,
        AnalysisKeys.ALREADY_IMPORTED_INDICES, AnalysisKeys.NEWLY_ADDED_INDICES,
        AnalysisKeys.MODIFIED_INDICES, AnalysisKeys.ANALYZED_RANGE,
    )

    @classmethod
    def from_json(cls, raw: Any, path: str, errors: list[str]) -> "OverlapInfo":
        data = _as_dict(raw, path, errors)
        return cls(
            match_type=_as_str(data.get(AnalysisKeys.MATCH_TYPE), "",
                               f"{path}.{AnalysisKeys.MATCH_TYPE}", errors),
            overlap_with_import_id=_as_opt_str(
                data.get(AnalysisKeys.OVERLAP_WITH_IMPORT_ID),
                f"{path}.{AnalysisKeys.OVERLAP_WITH_IMPORT_ID}", errors),
            already_imported_indices=_as_int_list(
                data.get(AnalysisKeys.ALREADY_IMPORTED_INDICES),
                f"{path}.{AnalysisKeys.ALREADY_IMPORTED_INDICES}", errors),
            newly_added_indices=_as_int_list(
                data.get(AnalysisKeys.NEWLY_ADDED_INDICES),
                f"{path}.{AnalysisKeys.NEWLY_ADDED_INDICES}", errors),
            modified_indices=_as_int_list(
                data.get(AnalysisKeys.MODIFIED_INDICES),
                f"{path}.{AnalysisKeys.MODIFIED_INDICES}", errors),
            analyzed_range=_as_int_list(
                data.get(AnalysisKeys.ANALYZED_RANGE),
                f"{path}.{AnalysisKeys.ANALYZED_RANGE}", errors),
            extra=_extras(data, cls._KEYS),
        )

    def to_json(self) -> dict:
        out = {
            AnalysisKeys.MATCH_TYPE: self.match_type,
            AnalysisKeys.OVERLAP_WITH_IMPORT_ID: self.overlap_with_import_id,
            AnalysisKeys.ALREADY_IMPORTED_INDICES: list(self.already_imported_indices),
            AnalysisKeys.NEWLY_ADDED_INDICES: list(self.newly_added_indices),
            AnalysisKeys.MODIFIED_INDICES: list(self.modified_indices),
            AnalysisKeys.ANALYZED_RANGE: list(self.analyzed_range),
        }
        out.update(self.extra)
        return out


@dataclass
class AnalysisItem:
    """AI가 제안한 항목 하나 (§26.3).

    `declared_status`는 사용자가 정하는 값이라 시스템이 직접 바꾸면 안 된다
    — `AnalysisDocument.set_declared_status(actor=ACTOR_USER)`만 허용된다.
    `derived_status`는 계산값이라 여러 개를 동시에 가질 수 있다.
    """

    item_id: str = ""
    kind: str = ""
    change_type: str = ""
    target_field: str = ""
    text: str = ""
    normalized_text: str = ""
    origin_stance: str = OriginStance.AI_PROPOSED
    declared_status: str = DeclaredStatus.PROPOSED
    derived_status: list[str] = field(default_factory=list)
    confidence: int = 0
    rationale: str = ""
    sources: list[SourceReference] = field(default_factory=list)
    supersedes_item_id: str | None = None
    related_previous_item_id: str | None = None
    match_type: str = MatchType.NEW
    similarity_score: float = 0.0
    carried_over: bool = False
    extra: dict = field(default_factory=dict)

    _KEYS = (
        AnalysisKeys.ITEM_ID, AnalysisKeys.KIND, AnalysisKeys.CHANGE_TYPE,
        AnalysisKeys.TARGET_FIELD, AnalysisKeys.TEXT, AnalysisKeys.NORMALIZED_TEXT,
        AnalysisKeys.ORIGIN_STANCE, AnalysisKeys.DECLARED_STATUS,
        AnalysisKeys.DERIVED_STATUS, AnalysisKeys.CONFIDENCE,
        AnalysisKeys.RATIONALE, AnalysisKeys.SOURCES,
        AnalysisKeys.SUPERSEDES_ITEM_ID, AnalysisKeys.RELATED_PREVIOUS_ITEM_ID,
        AnalysisKeys.MATCH_TYPE, AnalysisKeys.SIMILARITY_SCORE,
        AnalysisKeys.CARRIED_OVER,
    )

    @classmethod
    def from_json(cls, raw: Any, path: str, errors: list[str]) -> "AnalysisItem":
        data = _as_dict(raw, path, errors)
        sources_raw = _as_list(data.get(AnalysisKeys.SOURCES),
                               f"{path}.{AnalysisKeys.SOURCES}", errors)
        return cls(
            item_id=_as_str(data.get(AnalysisKeys.ITEM_ID), "",
                            f"{path}.{AnalysisKeys.ITEM_ID}", errors),
            kind=_as_str(data.get(AnalysisKeys.KIND), "",
                         f"{path}.{AnalysisKeys.KIND}", errors),
            change_type=_as_str(data.get(AnalysisKeys.CHANGE_TYPE), "",
                                f"{path}.{AnalysisKeys.CHANGE_TYPE}", errors),
            target_field=_as_str(data.get(AnalysisKeys.TARGET_FIELD), "",
                                 f"{path}.{AnalysisKeys.TARGET_FIELD}", errors),
            text=_as_str(data.get(AnalysisKeys.TEXT), "",
                         f"{path}.{AnalysisKeys.TEXT}", errors),
            normalized_text=_as_str(data.get(AnalysisKeys.NORMALIZED_TEXT), "",
                                    f"{path}.{AnalysisKeys.NORMALIZED_TEXT}", errors),
            origin_stance=_as_str(data.get(AnalysisKeys.ORIGIN_STANCE),
                                  OriginStance.AI_PROPOSED,
                                  f"{path}.{AnalysisKeys.ORIGIN_STANCE}", errors),
            declared_status=_as_str(data.get(AnalysisKeys.DECLARED_STATUS),
                                    DeclaredStatus.PROPOSED,
                                    f"{path}.{AnalysisKeys.DECLARED_STATUS}", errors),
            derived_status=_as_str_list(data.get(AnalysisKeys.DERIVED_STATUS),
                                        f"{path}.{AnalysisKeys.DERIVED_STATUS}", errors),
            confidence=_as_int(data.get(AnalysisKeys.CONFIDENCE), 0,
                               f"{path}.{AnalysisKeys.CONFIDENCE}", errors),
            rationale=_as_str(data.get(AnalysisKeys.RATIONALE), "",
                              f"{path}.{AnalysisKeys.RATIONALE}", errors),
            sources=[SourceReference.from_json(s, f"{path}.sources[{i}]", errors)
                     for i, s in enumerate(sources_raw)],
            supersedes_item_id=_as_opt_str(
                data.get(AnalysisKeys.SUPERSEDES_ITEM_ID),
                f"{path}.{AnalysisKeys.SUPERSEDES_ITEM_ID}", errors),
            related_previous_item_id=_as_opt_str(
                data.get(AnalysisKeys.RELATED_PREVIOUS_ITEM_ID),
                f"{path}.{AnalysisKeys.RELATED_PREVIOUS_ITEM_ID}", errors),
            match_type=_as_str(data.get(AnalysisKeys.MATCH_TYPE), MatchType.NEW,
                               f"{path}.{AnalysisKeys.MATCH_TYPE}", errors),
            similarity_score=_as_float(data.get(AnalysisKeys.SIMILARITY_SCORE), 0.0,
                                       f"{path}.{AnalysisKeys.SIMILARITY_SCORE}", errors),
            carried_over=_as_bool(data.get(AnalysisKeys.CARRIED_OVER), False,
                                  f"{path}.{AnalysisKeys.CARRIED_OVER}", errors),
            extra=_extras(data, cls._KEYS),
        )

    def to_json(self) -> dict:
        out = {
            AnalysisKeys.ITEM_ID: self.item_id,
            AnalysisKeys.KIND: self.kind,
            AnalysisKeys.CHANGE_TYPE: self.change_type,
            AnalysisKeys.TARGET_FIELD: self.target_field,
            AnalysisKeys.TEXT: self.text,
            AnalysisKeys.NORMALIZED_TEXT: self.normalized_text,
            AnalysisKeys.ORIGIN_STANCE: self.origin_stance,
            AnalysisKeys.DECLARED_STATUS: self.declared_status,
            AnalysisKeys.DERIVED_STATUS: list(self.derived_status),
            AnalysisKeys.CONFIDENCE: self.confidence,
            AnalysisKeys.RATIONALE: self.rationale,
            AnalysisKeys.SOURCES: [s.to_json() for s in self.sources],
            AnalysisKeys.SUPERSEDES_ITEM_ID: self.supersedes_item_id,
            AnalysisKeys.RELATED_PREVIOUS_ITEM_ID: self.related_previous_item_id,
            AnalysisKeys.MATCH_TYPE: self.match_type,
            AnalysisKeys.SIMILARITY_SCORE: self.similarity_score,
            AnalysisKeys.CARRIED_OVER: self.carried_over,
        }
        out.update(self.extra)
        return out


@dataclass
class UserDecision:
    """사용자 판단 하나 (§27.1). 재분석해도 보존된다."""

    item_id: str = ""
    decision: str = DecisionStatus.UNREVIEWED
    edited_text: str | None = None
    reviewed_at: str | None = None
    original_item_id: str | None = None
    carried_from_analysis_version: int | None = None
    user_note: str = ""
    extra: dict = field(default_factory=dict)

    _KEYS = (
        AnalysisKeys.ITEM_ID, AnalysisKeys.DECISION, AnalysisKeys.EDITED_TEXT,
        AnalysisKeys.REVIEWED_AT, AnalysisKeys.ORIGINAL_ITEM_ID,
        AnalysisKeys.CARRIED_FROM_ANALYSIS_VERSION, AnalysisKeys.USER_NOTE,
    )

    @classmethod
    def from_json(cls, raw: Any, path: str, errors: list[str]) -> "UserDecision":
        data = _as_dict(raw, path, errors)
        carried = data.get(AnalysisKeys.CARRIED_FROM_ANALYSIS_VERSION)
        return cls(
            item_id=_as_str(data.get(AnalysisKeys.ITEM_ID), "",
                            f"{path}.{AnalysisKeys.ITEM_ID}", errors),
            decision=_as_str(data.get(AnalysisKeys.DECISION),
                             DecisionStatus.UNREVIEWED,
                             f"{path}.{AnalysisKeys.DECISION}", errors),
            edited_text=_as_opt_str(data.get(AnalysisKeys.EDITED_TEXT),
                                    f"{path}.{AnalysisKeys.EDITED_TEXT}", errors),
            reviewed_at=_as_opt_str(data.get(AnalysisKeys.REVIEWED_AT),
                                    f"{path}.{AnalysisKeys.REVIEWED_AT}", errors),
            original_item_id=_as_opt_str(
                data.get(AnalysisKeys.ORIGINAL_ITEM_ID),
                f"{path}.{AnalysisKeys.ORIGINAL_ITEM_ID}", errors),
            carried_from_analysis_version=(
                None if carried is None
                else _as_int(carried, 0,
                             f"{path}.{AnalysisKeys.CARRIED_FROM_ANALYSIS_VERSION}",
                             errors)),
            user_note=_as_str(data.get(AnalysisKeys.USER_NOTE), "",
                              f"{path}.{AnalysisKeys.USER_NOTE}", errors),
            extra=_extras(data, cls._KEYS),
        )

    def to_json(self) -> dict:
        out = {
            AnalysisKeys.ITEM_ID: self.item_id,
            AnalysisKeys.DECISION: self.decision,
            AnalysisKeys.EDITED_TEXT: self.edited_text,
            AnalysisKeys.REVIEWED_AT: self.reviewed_at,
            AnalysisKeys.ORIGINAL_ITEM_ID: self.original_item_id,
            AnalysisKeys.CARRIED_FROM_ANALYSIS_VERSION: self.carried_from_analysis_version,
            AnalysisKeys.USER_NOTE: self.user_note,
        }
        out.update(self.extra)
        return out


@dataclass
class ApplicationEntry:
    """실제 반영 결과 하나 (§27.1).

    승인(`UserDecision`)과 별개다 — 승인했어도 중복이거나 트랜잭션이
    실패하면 여기 `applied`가 아닌 상태로 남는다.
    """

    item_id: str = ""
    status: str = ApplicationStatus.NOT_SELECTED
    target_field: str = ""
    applied_text: str = ""
    revision_id: str | None = None
    event_id: str | None = None
    error_message: str = ""
    applied_at: str | None = None
    extra: dict = field(default_factory=dict)

    _KEYS = (
        AnalysisKeys.ITEM_ID, AnalysisKeys.STATUS, AnalysisKeys.TARGET_FIELD,
        AnalysisKeys.APPLIED_TEXT, AnalysisKeys.REVISION_ID,
        AnalysisKeys.EVENT_ID, AnalysisKeys.ERROR_MESSAGE,
        AnalysisKeys.APPLIED_AT,
    )

    @classmethod
    def from_json(cls, raw: Any, path: str, errors: list[str]) -> "ApplicationEntry":
        data = _as_dict(raw, path, errors)
        return cls(
            item_id=_as_str(data.get(AnalysisKeys.ITEM_ID), "",
                            f"{path}.{AnalysisKeys.ITEM_ID}", errors),
            status=_as_str(data.get(AnalysisKeys.STATUS),
                           ApplicationStatus.NOT_SELECTED,
                           f"{path}.{AnalysisKeys.STATUS}", errors),
            target_field=_as_str(data.get(AnalysisKeys.TARGET_FIELD), "",
                                 f"{path}.{AnalysisKeys.TARGET_FIELD}", errors),
            applied_text=_as_str(data.get(AnalysisKeys.APPLIED_TEXT), "",
                                 f"{path}.{AnalysisKeys.APPLIED_TEXT}", errors),
            revision_id=_as_opt_str(data.get(AnalysisKeys.REVISION_ID),
                                    f"{path}.{AnalysisKeys.REVISION_ID}", errors),
            event_id=_as_opt_str(data.get(AnalysisKeys.EVENT_ID),
                                 f"{path}.{AnalysisKeys.EVENT_ID}", errors),
            error_message=_as_str(data.get(AnalysisKeys.ERROR_MESSAGE), "",
                                  f"{path}.{AnalysisKeys.ERROR_MESSAGE}", errors),
            applied_at=_as_opt_str(data.get(AnalysisKeys.APPLIED_AT),
                                   f"{path}.{AnalysisKeys.APPLIED_AT}", errors),
            extra=_extras(data, cls._KEYS),
        )

    def to_json(self) -> dict:
        out = {
            AnalysisKeys.ITEM_ID: self.item_id,
            AnalysisKeys.STATUS: self.status,
            AnalysisKeys.TARGET_FIELD: self.target_field,
            AnalysisKeys.APPLIED_TEXT: self.applied_text,
            AnalysisKeys.REVISION_ID: self.revision_id,
            AnalysisKeys.EVENT_ID: self.event_id,
            AnalysisKeys.ERROR_MESSAGE: self.error_message,
            AnalysisKeys.APPLIED_AT: self.applied_at,
        }
        out.update(self.extra)
        return out


# ---------------------------------------------------------------------------
# 빈 구조 / 마이그레이션
# ---------------------------------------------------------------------------


def empty_analysis() -> dict:
    """v1 기본 객체. 아직 아무것도 분석하지 않은 상태."""
    return {
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        AnalysisKeys.ANALYSIS_VERSION: 1,
        AnalysisKeys.PROVIDER: "",
        AnalysisKeys.MODEL: None,
        AnalysisKeys.PROMPT_VERSION: CURRENT_PROMPT_VERSION,
        AnalysisKeys.SYNONYM_DICT_VERSION: INITIAL_SYNONYM_DICT_VERSION,
        AnalysisKeys.ANALYZED_AT: "",
        AnalysisKeys.MESSAGES: [],
        AnalysisKeys.OVERLAP: {},
        AnalysisKeys.AI_ANALYSIS: {
            AnalysisKeys.NEW_ELEMENTS: [],
            AnalysisKeys.REINFORCED_ELEMENTS: [],
            AnalysisKeys.MODIFIED_ELEMENTS: [],
            AnalysisKeys.CONFLICTING_ELEMENTS: [],
            AnalysisKeys.REJECTED_ELEMENTS: [],
            AnalysisKeys.OPEN_QUESTIONS: [],
            AnalysisKeys.SOURCE_REFERENCES: [],
            AnalysisKeys.MERGE_PROPOSALS: [],
        },
        AnalysisKeys.USER_REVIEW: {
            AnalysisKeys.DECISIONS: [],
            AnalysisKeys.ORPHANED_DECISIONS: [],
            AnalysisKeys.NOTES: "",
        },
        AnalysisKeys.APPLICATION_RESULT: {
            AnalysisKeys.APPLIED_ITEMS: [],
            AnalysisKeys.REVISION_ID: None,
            AnalysisKeys.EVENT_IDS: [],
            AnalysisKeys.APPLIED_AT: None,
        },
    }


# 버전이 없는 최초 형식을 가리키는 이름. 실제로 배포된 적은 없지만,
# 마이그레이션 체인이 실제로 동작하는지 테스트하기 위한 기준점이다.
LEGACY_VERSION = "0"


def migrate_v0_to_v1(raw: dict) -> dict:
    """버전 표기가 없던 평평한 구조를 v1의 3계층 구조로 옮긴다.

    v0는 `ai_analysis` 없이 `new_elements` 등이 최상위에 있었다고 본다.
    사용자 판단 개념 자체가 없었으므로 `user_review`는 비워 둔다.
    """
    out = empty_analysis()
    ai = out[AnalysisKeys.AI_ANALYSIS]
    for bucket in (*ITEM_BUCKETS, *_OTHER_AI_LISTS):
        if isinstance(raw.get(bucket), list):
            ai[bucket] = copy.deepcopy(raw[bucket])

    for key in (AnalysisKeys.PROVIDER, AnalysisKeys.MODEL,
                AnalysisKeys.PROMPT_VERSION, AnalysisKeys.ANALYZED_AT):
        if key in raw:
            out[key] = copy.deepcopy(raw[key])

    if isinstance(raw.get(AnalysisKeys.MESSAGES), list):
        out[AnalysisKeys.MESSAGES] = copy.deepcopy(raw[AnalysisKeys.MESSAGES])

    known = {
        *ITEM_BUCKETS, *_OTHER_AI_LISTS,
        AnalysisKeys.PROVIDER, AnalysisKeys.MODEL, AnalysisKeys.PROMPT_VERSION,
        AnalysisKeys.ANALYZED_AT, AnalysisKeys.MESSAGES,
        AnalysisKeys.SCHEMA_VERSION,
    }
    leftover = _extras(raw, known)
    if leftover:
        out[AnalysisKeys.EXTRA] = leftover
    return out


# 버전 → 다음 버전으로 올리는 함수. 새 버전이 생기면 여기에 추가한다.
_MIGRATIONS: dict[str, Any] = {
    LEGACY_VERSION: migrate_v0_to_v1,
}


def _detect_version(raw: dict) -> str:
    value = raw.get(AnalysisKeys.SCHEMA_VERSION)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return LEGACY_VERSION


def _is_future_version(version: str) -> bool:
    """현재보다 높은 버전인가. 비교할 수 없는 형식이면 미래로 간주한다."""
    try:
        cur = tuple(int(p) for p in CURRENT_SCHEMA_VERSION.split("."))
        got = tuple(int(p) for p in version.split("."))
    except ValueError:
        return True
    return got > cur


def _wrap_unknown(raw: dict) -> dict:
    """알 수 없는(주로 미래) 버전 — 원본을 통째로 보존하고 빈 구조를 돌려준다.

    예외를 던지지 않는 이유: 미래 버전으로 저장된 DB를 구버전 앱에서 열어도
    **데이터가 사라지면 안 되기 때문**이다. 화면에는 분석 결과가 비어
    보이지만 원본은 그대로 남아, 최신 앱에서 다시 열면 정상적으로 읽힌다.
    """
    out = empty_analysis()
    out[AnalysisKeys.UNMIGRATED_RAW] = copy.deepcopy(raw)
    return out


# ---------------------------------------------------------------------------
# AnalysisDocument
# ---------------------------------------------------------------------------


class AnalysisDocument:
    """analysis_json에 접근하는 유일한 경로.

    `load_analysis()`로 만들고 `to_json()`으로 되돌린다.
    입력 dict는 절대 수정하지 않는다.
    """

    def __init__(self, doc: dict, errors: list[str] | None = None):
        self._doc = doc
        self._errors = list(errors or [])

    # -- 메타 --------------------------------------------------------------

    @property
    def schema_version(self) -> str:
        return self._doc[AnalysisKeys.SCHEMA_VERSION]

    @property
    def analysis_version(self) -> int:
        return self._doc[AnalysisKeys.ANALYSIS_VERSION]

    @property
    def provider(self) -> str:
        return self._doc[AnalysisKeys.PROVIDER]

    @property
    def model(self) -> str | None:
        return self._doc[AnalysisKeys.MODEL]

    @property
    def prompt_version(self) -> str:
        return self._doc[AnalysisKeys.PROMPT_VERSION]

    @property
    def synonym_dict_version(self) -> int:
        return self._doc[AnalysisKeys.SYNONYM_DICT_VERSION]

    @property
    def analyzed_at(self) -> str:
        return self._doc[AnalysisKeys.ANALYZED_AT]

    @property
    def coercion_errors(self) -> list[str]:
        """잘못된 타입을 만나 기본값으로 대체한 내역. 비어 있으면 정상."""
        return list(self._errors)

    @property
    def unmigrated_raw(self) -> dict | None:
        """알 수 없는 버전이라 해석하지 못한 원본 (§26.5)."""
        return self._doc.get(AnalysisKeys.UNMIGRATED_RAW)

    @property
    def is_unmigrated(self) -> bool:
        return self.unmigrated_raw is not None

    def set_meta(self, *, provider: str | None = None, model: str | None = None,
                 prompt_version: str | None = None, analyzed_at: str | None = None,
                 synonym_dict_version: int | None = None) -> None:
        if provider is not None:
            self._doc[AnalysisKeys.PROVIDER] = provider
        if model is not None:
            self._doc[AnalysisKeys.MODEL] = model
        if prompt_version is not None:
            self._doc[AnalysisKeys.PROMPT_VERSION] = prompt_version
        if analyzed_at is not None:
            self._doc[AnalysisKeys.ANALYZED_AT] = analyzed_at
        if synonym_dict_version is not None:
            self._doc[AnalysisKeys.SYNONYM_DICT_VERSION] = synonym_dict_version

    # -- 구조 --------------------------------------------------------------

    def messages(self) -> list[MessageRef]:
        errors: list[str] = []
        return [MessageRef.from_json(m, f"messages[{i}]", errors)
                for i, m in enumerate(self._doc[AnalysisKeys.MESSAGES])]

    def set_messages(self, messages: list[MessageRef]) -> None:
        self._doc[AnalysisKeys.MESSAGES] = [m.to_json() for m in messages]

    def overlap(self) -> OverlapInfo:
        errors: list[str] = []
        return OverlapInfo.from_json(self._doc[AnalysisKeys.OVERLAP], "overlap", errors)

    def set_overlap(self, overlap: OverlapInfo) -> None:
        self._doc[AnalysisKeys.OVERLAP] = overlap.to_json()

    # -- ai_analysis -------------------------------------------------------

    def _bucket(self, name: str) -> list[AnalysisItem]:
        errors: list[str] = []
        raw = self._doc[AnalysisKeys.AI_ANALYSIS].get(name, [])
        return [AnalysisItem.from_json(x, f"{name}[{i}]", errors)
                for i, x in enumerate(raw)]

    def new_elements(self) -> list[AnalysisItem]:
        return self._bucket(AnalysisKeys.NEW_ELEMENTS)

    def reinforced_elements(self) -> list[AnalysisItem]:
        return self._bucket(AnalysisKeys.REINFORCED_ELEMENTS)

    def modified_elements(self) -> list[AnalysisItem]:
        return self._bucket(AnalysisKeys.MODIFIED_ELEMENTS)

    def conflicting_elements(self) -> list[AnalysisItem]:
        return self._bucket(AnalysisKeys.CONFLICTING_ELEMENTS)

    def rejected_elements(self) -> list[AnalysisItem]:
        return self._bucket(AnalysisKeys.REJECTED_ELEMENTS)

    def all_items(self) -> list[AnalysisItem]:
        """모든 버킷의 제안 항목을 한 번에."""
        out: list[AnalysisItem] = []
        for bucket in ITEM_BUCKETS:
            out.extend(self._bucket(bucket))
        return out

    def item(self, item_id: str) -> AnalysisItem | None:
        for it in self.all_items():
            if it.item_id == item_id:
                return it
        return None

    def open_questions(self) -> list[dict]:
        return copy.deepcopy(
            self._doc[AnalysisKeys.AI_ANALYSIS].get(AnalysisKeys.OPEN_QUESTIONS, []))

    def merge_proposals(self) -> list[dict]:
        return copy.deepcopy(
            self._doc[AnalysisKeys.AI_ANALYSIS].get(AnalysisKeys.MERGE_PROPOSALS, []))

    def source_references(self) -> list[SourceReference]:
        errors: list[str] = []
        raw = self._doc[AnalysisKeys.AI_ANALYSIS].get(AnalysisKeys.SOURCE_REFERENCES, [])
        return [SourceReference.from_json(x, f"source_references[{i}]", errors)
                for i, x in enumerate(raw)]

    def set_items(self, bucket: str, items: list[AnalysisItem]) -> None:
        if bucket not in ITEM_BUCKETS:
            raise ValueError(f"알 수 없는 버킷입니다: {bucket}")
        self._doc[AnalysisKeys.AI_ANALYSIS][bucket] = [i.to_json() for i in items]

    # -- 상태 (§9.4) -------------------------------------------------------

    def set_declared_status(self, item_id: str, status: str, *, actor: str) -> None:
        """사용자가 정한 상태를 바꾼다. **사용자 행위일 때만 허용된다.**

        시스템 계산(`actor=ACTOR_SYSTEM`)이 이 값을 건드리면 예외를 던진다 —
        "최근 미언급"이라는 이유로 채택된 아이디어가 폐기로 바뀌는 사고를
        구조적으로 막기 위해서다.
        """
        if actor != ACTOR_USER:
            raise DeclaredStatusProtectedError(
                "declared_status는 사용자만 바꿀 수 있습니다 "
                f"(actor={actor!r}). 시스템 계산은 derived_status를 쓰세요."
            )
        self._update_item_field(item_id, AnalysisKeys.DECLARED_STATUS, status)

    def set_derived_status(self, item_id: str, statuses: list[str]) -> None:
        """시스템이 계산한 상태를 갱신한다. declared_status는 건드리지 않는다."""
        self._update_item_field(
            item_id, AnalysisKeys.DERIVED_STATUS, list(dict.fromkeys(statuses)))

    def _update_item_field(self, item_id: str, key: str, value: Any) -> None:
        for bucket in ITEM_BUCKETS:
            for entry in self._doc[AnalysisKeys.AI_ANALYSIS].get(bucket, []):
                if isinstance(entry, dict) and entry.get(AnalysisKeys.ITEM_ID) == item_id:
                    entry[key] = value
                    return
        raise KeyError(f"항목을 찾을 수 없습니다: {item_id}")

    # -- user_review (§27) -------------------------------------------------

    def decisions(self) -> list[UserDecision]:
        errors: list[str] = []
        raw = self._doc[AnalysisKeys.USER_REVIEW].get(AnalysisKeys.DECISIONS, [])
        return [UserDecision.from_json(d, f"decisions[{i}]", errors)
                for i, d in enumerate(raw)]

    def orphaned_decisions(self) -> list[UserDecision]:
        errors: list[str] = []
        raw = self._doc[AnalysisKeys.USER_REVIEW].get(
            AnalysisKeys.ORPHANED_DECISIONS, [])
        return [UserDecision.from_json(d, f"orphaned_decisions[{i}]", errors)
                for i, d in enumerate(raw)]

    def decision_of(self, item_id: str) -> UserDecision | None:
        for d in self.decisions():
            if d.item_id == item_id:
                return d
        return None

    def user_notes(self) -> str:
        return self._doc[AnalysisKeys.USER_REVIEW].get(AnalysisKeys.NOTES, "")

    def set_user_notes(self, notes: str) -> None:
        self._doc[AnalysisKeys.USER_REVIEW][AnalysisKeys.NOTES] = notes

    def set_decision(self, decision: UserDecision) -> None:
        """판단을 기록한다. 같은 item_id가 있으면 교체한다."""
        bucket = self._doc[AnalysisKeys.USER_REVIEW][AnalysisKeys.DECISIONS]
        payload = decision.to_json()
        for i, entry in enumerate(bucket):
            if isinstance(entry, dict) and entry.get(AnalysisKeys.ITEM_ID) == decision.item_id:
                bucket[i] = payload
                return
        bucket.append(payload)

    def set_decisions(self, decisions: list[UserDecision]) -> None:
        self._doc[AnalysisKeys.USER_REVIEW][AnalysisKeys.DECISIONS] = [
            d.to_json() for d in decisions]

    def set_orphaned_decisions(self, decisions: list[UserDecision]) -> None:
        self._doc[AnalysisKeys.USER_REVIEW][AnalysisKeys.ORPHANED_DECISIONS] = [
            d.to_json() for d in decisions]

    def pending_items(self) -> list[AnalysisItem]:
        """아직 사용자가 판단하지 않은 항목."""
        reviewed = {
            d.item_id for d in self.decisions()
            if d.decision != DecisionStatus.UNREVIEWED
        }
        return [it for it in self.all_items() if it.item_id not in reviewed]

    # -- application_result (§27.1) ---------------------------------------

    def application_entries(self) -> list[ApplicationEntry]:
        errors: list[str] = []
        raw = self._doc[AnalysisKeys.APPLICATION_RESULT].get(
            AnalysisKeys.APPLIED_ITEMS, [])
        return [ApplicationEntry.from_json(e, f"applied_items[{i}]", errors)
                for i, e in enumerate(raw)]

    def application_of(self, item_id: str) -> ApplicationEntry | None:
        for e in self.application_entries():
            if e.item_id == item_id:
                return e
        return None

    def application_revision_id(self) -> str | None:
        return self._doc[AnalysisKeys.APPLICATION_RESULT].get(AnalysisKeys.REVISION_ID)

    def application_event_ids(self) -> list[str]:
        return list(
            self._doc[AnalysisKeys.APPLICATION_RESULT].get(AnalysisKeys.EVENT_IDS, []))

    def application_applied_at(self) -> str | None:
        return self._doc[AnalysisKeys.APPLICATION_RESULT].get(AnalysisKeys.APPLIED_AT)

    def record_application(self, entries: list[ApplicationEntry], *,
                           revision_id: str | None = None,
                           event_ids: list[str] | None = None,
                           applied_at: str | None = None) -> None:
        """실제 반영 결과를 기록한다. 승인 기록(`user_review`)은 건드리지 않는다."""
        result = self._doc[AnalysisKeys.APPLICATION_RESULT]
        result[AnalysisKeys.APPLIED_ITEMS] = [e.to_json() for e in entries]
        if revision_id is not None:
            result[AnalysisKeys.REVISION_ID] = revision_id
        if event_ids is not None:
            result[AnalysisKeys.EVENT_IDS] = list(event_ids)
        if applied_at is not None:
            result[AnalysisKeys.APPLIED_AT] = applied_at

    # -- 재분석 (§27.3) ----------------------------------------------------

    def replace_ai_analysis(self, new_ai: dict) -> "AnalysisDocument":
        """AI 결과만 갈아끼우고 사용자 판단은 이어받은 **새 문서**를 만든다.

        이 문서 자신은 바뀌지 않는다. 판단 이어받기 규칙은
        `src.conversations.hashing.merge_user_reviews_after_reanalysis()`가
        결정하며, 여기서는 구조만 옮긴다.
        """
        doc = copy.deepcopy(self._doc)
        base = empty_analysis()[AnalysisKeys.AI_ANALYSIS]
        merged = {**base, **copy.deepcopy(new_ai)}
        doc[AnalysisKeys.AI_ANALYSIS] = merged
        doc[AnalysisKeys.ANALYSIS_VERSION] = doc[AnalysisKeys.ANALYSIS_VERSION] + 1
        return AnalysisDocument(doc, self._errors)

    # -- 직렬화 ------------------------------------------------------------

    def to_json(self) -> dict:
        return copy.deepcopy(self._doc)


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def normalize_v1(raw: dict, errors: list[str]) -> dict:
    """v1 구조를 채워 넣는다. 없는 필드는 기본값, 모르는 필드는 보존."""
    base = empty_analysis()
    out = copy.deepcopy(base)

    out[AnalysisKeys.SCHEMA_VERSION] = CURRENT_SCHEMA_VERSION
    out[AnalysisKeys.ANALYSIS_VERSION] = _as_int(
        raw.get(AnalysisKeys.ANALYSIS_VERSION), 1, AnalysisKeys.ANALYSIS_VERSION, errors)
    out[AnalysisKeys.PROVIDER] = _as_str(
        raw.get(AnalysisKeys.PROVIDER), "", AnalysisKeys.PROVIDER, errors)
    out[AnalysisKeys.MODEL] = _as_opt_str(
        raw.get(AnalysisKeys.MODEL), AnalysisKeys.MODEL, errors)
    out[AnalysisKeys.PROMPT_VERSION] = _as_str(
        raw.get(AnalysisKeys.PROMPT_VERSION), CURRENT_PROMPT_VERSION,
        AnalysisKeys.PROMPT_VERSION, errors)
    out[AnalysisKeys.SYNONYM_DICT_VERSION] = _as_int(
        raw.get(AnalysisKeys.SYNONYM_DICT_VERSION), INITIAL_SYNONYM_DICT_VERSION,
        AnalysisKeys.SYNONYM_DICT_VERSION, errors)
    out[AnalysisKeys.ANALYZED_AT] = _as_str(
        raw.get(AnalysisKeys.ANALYZED_AT), "", AnalysisKeys.ANALYZED_AT, errors)

    messages = _as_list(raw.get(AnalysisKeys.MESSAGES), AnalysisKeys.MESSAGES, errors)
    out[AnalysisKeys.MESSAGES] = [
        MessageRef.from_json(m, f"messages[{i}]", errors).to_json()
        for i, m in enumerate(messages)
    ]

    overlap = _as_dict(raw.get(AnalysisKeys.OVERLAP), AnalysisKeys.OVERLAP, errors)
    out[AnalysisKeys.OVERLAP] = (
        OverlapInfo.from_json(overlap, AnalysisKeys.OVERLAP, errors).to_json()
        if overlap else {}
    )

    ai_raw = _as_dict(raw.get(AnalysisKeys.AI_ANALYSIS),
                      AnalysisKeys.AI_ANALYSIS, errors)
    for bucket in ITEM_BUCKETS:
        entries = _as_list(ai_raw.get(bucket), f"ai_analysis.{bucket}", errors)
        out[AnalysisKeys.AI_ANALYSIS][bucket] = [
            AnalysisItem.from_json(e, f"ai_analysis.{bucket}[{i}]", errors).to_json()
            for i, e in enumerate(entries)
        ]
    for key in _OTHER_AI_LISTS:
        out[AnalysisKeys.AI_ANALYSIS][key] = _as_list(
            ai_raw.get(key), f"ai_analysis.{key}", errors)
    ai_extra = _extras(ai_raw, (*ITEM_BUCKETS, *_OTHER_AI_LISTS))
    out[AnalysisKeys.AI_ANALYSIS].update(ai_extra)

    review_raw = _as_dict(raw.get(AnalysisKeys.USER_REVIEW),
                          AnalysisKeys.USER_REVIEW, errors)
    for key in (AnalysisKeys.DECISIONS, AnalysisKeys.ORPHANED_DECISIONS):
        entries = _as_list(review_raw.get(key), f"user_review.{key}", errors)
        out[AnalysisKeys.USER_REVIEW][key] = [
            UserDecision.from_json(e, f"user_review.{key}[{i}]", errors).to_json()
            for i, e in enumerate(entries)
        ]
    out[AnalysisKeys.USER_REVIEW][AnalysisKeys.NOTES] = _as_str(
        review_raw.get(AnalysisKeys.NOTES), "", "user_review.notes", errors)
    review_extra = _extras(
        review_raw,
        (AnalysisKeys.DECISIONS, AnalysisKeys.ORPHANED_DECISIONS, AnalysisKeys.NOTES))
    out[AnalysisKeys.USER_REVIEW].update(review_extra)

    result_raw = _as_dict(raw.get(AnalysisKeys.APPLICATION_RESULT),
                          AnalysisKeys.APPLICATION_RESULT, errors)
    applied = _as_list(result_raw.get(AnalysisKeys.APPLIED_ITEMS),
                       "application_result.applied_items", errors)
    out[AnalysisKeys.APPLICATION_RESULT][AnalysisKeys.APPLIED_ITEMS] = [
        ApplicationEntry.from_json(
            e, f"application_result.applied_items[{i}]", errors).to_json()
        for i, e in enumerate(applied)
    ]
    out[AnalysisKeys.APPLICATION_RESULT][AnalysisKeys.REVISION_ID] = _as_opt_str(
        result_raw.get(AnalysisKeys.REVISION_ID),
        "application_result.revision_id", errors)
    out[AnalysisKeys.APPLICATION_RESULT][AnalysisKeys.EVENT_IDS] = _as_str_list(
        result_raw.get(AnalysisKeys.EVENT_IDS),
        "application_result.event_ids", errors)
    out[AnalysisKeys.APPLICATION_RESULT][AnalysisKeys.APPLIED_AT] = _as_opt_str(
        result_raw.get(AnalysisKeys.APPLIED_AT),
        "application_result.applied_at", errors)
    result_extra = _extras(
        result_raw,
        (AnalysisKeys.APPLIED_ITEMS, AnalysisKeys.REVISION_ID,
         AnalysisKeys.EVENT_IDS, AnalysisKeys.APPLIED_AT))
    out[AnalysisKeys.APPLICATION_RESULT].update(result_extra)

    known_top = {
        AnalysisKeys.SCHEMA_VERSION, AnalysisKeys.ANALYSIS_VERSION,
        AnalysisKeys.PROVIDER, AnalysisKeys.MODEL, AnalysisKeys.PROMPT_VERSION,
        AnalysisKeys.SYNONYM_DICT_VERSION, AnalysisKeys.ANALYZED_AT,
        AnalysisKeys.MESSAGES, AnalysisKeys.OVERLAP, AnalysisKeys.AI_ANALYSIS,
        AnalysisKeys.USER_REVIEW, AnalysisKeys.APPLICATION_RESULT,
    }
    out.update(_extras(raw, known_top))
    return out


def load_analysis(raw: dict | None) -> AnalysisDocument:
    """어떤 버전으로 저장됐든 현재 구조로 올려서 돌려준다.

    - 빈 값/None → v1 기본 객체
    - 과거 버전 → 순차 마이그레이션
    - 현재 버전 → 정규화 후 반환
    - 미래 버전 → `_unmigrated_raw`에 원본 보존 (예외 없음)

    **입력 dict를 수정하지 않는다.**
    """
    if not raw:
        return AnalysisDocument(empty_analysis(), [])
    if not isinstance(raw, dict):
        return AnalysisDocument(_wrap_unknown({"value": raw}), [
            f"analysis_json이 객체가 아님({type(raw).__name__}) → 원본 보존"])

    work = copy.deepcopy(raw)
    version = _detect_version(work)

    if _is_future_version(version):
        return AnalysisDocument(_wrap_unknown(raw), [])

    seen: set[str] = set()
    while version != CURRENT_SCHEMA_VERSION:
        if version in seen or version not in _MIGRATIONS:
            return AnalysisDocument(_wrap_unknown(raw), [
                f"알 수 없는 analysis_json 버전: {version} → 원본 보존"])
        seen.add(version)
        work = _MIGRATIONS[version](work)
        version = _detect_version(work)

    errors: list[str] = []
    return AnalysisDocument(normalize_v1(work, errors), errors)


# ---------------------------------------------------------------------------
# DB 직렬화 — TEXT 컬럼과의 유일한 접점
# ---------------------------------------------------------------------------


def dumps_analysis(doc: "AnalysisDocument | dict | None") -> str | None:
    """`analysis_json` TEXT 컬럼에 넣을 문자열로 만든다.

    직렬화 옵션이 **계약의 일부다.**

    - ``ensure_ascii=False`` — 한글이 ``\\uXXXX``로 부풀지 않는다. DB를
      직접 열어 봤을 때 사람이 읽을 수 있어야 한다.
    - ``sort_keys=True`` — 같은 내용이면 항상 같은 문자열이 나온다.
      "내용이 바뀌었나"를 문자열 비교만으로 판단할 수 있다.
    - ``separators=(",", ":")`` — 불필요한 공백을 넣지 않는다. 들여쓰기는
      화면에 보여줄 때만 쓰고 DB에는 저장하지 않는다.

    셋 중 하나라도 빠지면 내용이 같은데 문자열이 달라져서, 변경 감지와
    테스트가 조용히 어긋난다.
    """
    if doc is None:
        return None
    data = doc.to_json() if isinstance(doc, AnalysisDocument) else doc
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads_analysis(text: str | None) -> AnalysisDocument:
    """`analysis_json` TEXT 컬럼을 읽어 문서로 되돌린다.

    **깨진 JSON이 저장돼 있어도 예외를 던지지 않는다.** 대화 목록을 여는
    것만으로 앱 전체가 멈추면 안 되기 때문이다. 해석에 실패하면 원문
    문자열을 `_unmigrated_raw`에 그대로 담아 돌려주므로, 나중에 원인을
    찾거나 손으로 복구할 수 있다 — 이 경우 `is_unmigrated`가 True다.
    """
    if text is None or not text.strip():
        return AnalysisDocument(empty_analysis(), [])
    try:
        raw = json.loads(text)
    except ValueError as exc:
        return AnalysisDocument(
            _wrap_unknown({AnalysisKeys.CORRUPTED_TEXT: text}),
            [f"analysis_json을 해석하지 못해 원본을 보존했습니다: {exc}"],
        )
    return load_analysis(raw)


def iter_items(ai_analysis: dict) -> Iterator[dict]:
    """ai_analysis 원본 dict에서 제안 항목만 순회한다 (Parser 편의용)."""
    for bucket in ITEM_BUCKETS:
        for entry in ai_analysis.get(bucket, []) or []:
            if isinstance(entry, dict):
                yield entry
