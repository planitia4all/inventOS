"""ConversationImport 모델·제약·회차 번호 (Conversation Engine 1단계).

여기서 확인하는 것은 "DB가 잘못된 데이터를 실제로 막는가"다. ORM이
막아 주는 것과 DB가 막아 주는 것은 다르다 — 나중에 스크립트로 직접
INSERT하는 상황이 오면 DB 제약만 남는다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.conversations.service import (
    ConversationImportError,
    ConversationImportService,
    RawContentTooLongError,
    RawContentTooShortError,
)
from src.database.models import ConversationImport
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService

RAW = "그래핀 섬유를 유리 기판에 관통 배치하는 방법에 대해 이야기했다. " * 10


def _invention(session, memo="유리 기판 관통 전극 아이디어"):
    return InventionService(session).quick_create(QuickIdeaInput(memo=memo))


def _service(session):
    return ConversationImportService(session)


# ---------------------------------------------------------------------------
# 생성
# ---------------------------------------------------------------------------


def test_create_stores_raw_content_and_metadata(db_session):
    invention = _invention(db_session)

    record = _service(db_session).create(
        invention.id, RAW, title="1차 대화", source_type="chatgpt"
    )

    assert record.invention_id == invention.id
    assert record.sequence_no == 1
    assert record.raw_content == RAW  # 원문은 한 글자도 바뀌지 않는다
    assert record.raw_content_length == len(RAW)
    assert len(record.raw_content_hash) == 64
    assert record.analysis_status == "pending"
    assert record.analysis_json is None
    assert record.analysis_version == 0
    assert record.is_deleted is False
    assert record.summary_status == "not_generated"
    # Timeline 연결은 다음 단계 몫이라 아직 비어 있다.
    assert record.created_event_id is None
    assert record.created_revision_id is None


def test_create_rejects_unknown_invention(db_session):
    with pytest.raises(ConversationImportError, match="발명을 찾을 수 없"):
        _service(db_session).create("없는-발명-id", RAW)


def test_db_rejects_unknown_invention_id_even_without_service(db_session):
    """서비스를 건너뛰고 직접 넣어도 FK가 막아야 한다 (PRAGMA foreign_keys=ON)."""
    db_session.add(
        ConversationImport(
            invention_id="없는-발명-id",
            sequence_no=1,
            raw_content=RAW,
            raw_content_hash="x" * 64,
            raw_content_length=len(RAW),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_valid_invention_id_is_accepted(db_session):
    invention = _invention(db_session)
    record = _service(db_session).create(invention.id, RAW)
    db_session.commit()

    assert _service(db_session).get(record.id) is not None


# ---------------------------------------------------------------------------
# 회차 번호
# ---------------------------------------------------------------------------


def test_sequence_increases_per_invention(db_session):
    invention = _invention(db_session)
    service = _service(db_session)

    numbers = [service.create(invention.id, RAW + str(i)).sequence_no for i in range(3)]

    assert numbers == [1, 2, 3]


def test_sequence_is_independent_between_inventions(db_session):
    first = _invention(db_session, "첫 번째 발명")
    second = _invention(db_session, "두 번째 발명")
    service = _service(db_session)

    service.create(first.id, RAW)
    service.create(first.id, RAW + "2")
    other = service.create(second.id, RAW)

    assert other.sequence_no == 1


def test_duplicate_sequence_is_rejected_by_db(db_session):
    invention = _invention(db_session)
    _service(db_session).create(invention.id, RAW)

    db_session.add(
        ConversationImport(
            invention_id=invention.id,
            sequence_no=1,  # 이미 있는 회차
            raw_content=RAW,
            raw_content_hash="y" * 64,
            raw_content_length=len(RAW),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_sequence_is_not_reused_after_soft_delete(db_session):
    """삭제된 회차 번호를 다시 쓰면 복원했을 때 두 대화가 같은 자리를 다툰다."""
    invention = _invention(db_session)
    service = _service(db_session)

    first = service.create(invention.id, RAW)
    second = service.create(invention.id, RAW + "2")
    service.soft_delete(second.id)

    third = service.create(invention.id, RAW + "3")

    assert third.sequence_no == 3
    assert first.sequence_no == 1
    # 삭제된 2회차는 그대로 남아 있어 번호를 계속 붙잡고 있다.
    assert service.get(second.id).sequence_no == 2


def test_sequence_collision_is_retried(db_session, monkeypatch):
    """회차 계산은 잠금이 없어서 같은 번호가 나올 수 있다 — 재시도로 넘긴다."""
    invention = _invention(db_session)
    service = _service(db_session)
    service.create(invention.id, RAW)

    calls = {"n": 0}
    real = service.repo.next_sequence_no

    def flaky(invention_id: str) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            return 1  # 이미 쓰인 번호 → IntegrityError
        return real(invention_id)

    monkeypatch.setattr(service.repo, "next_sequence_no", flaky)

    record = service.create(invention.id, RAW + "2")

    assert calls["n"] == 2
    assert record.sequence_no == 2


# ---------------------------------------------------------------------------
# 이전 대화 연결
# ---------------------------------------------------------------------------


def test_create_links_to_previous_import(db_session):
    invention = _invention(db_session)
    service = _service(db_session)

    first = service.create(invention.id, RAW)
    service.update_summary(first.id, "1차까지의 누적 요약")
    second = service.create(invention.id, RAW + "2")

    assert second.previous_conversation_import_id == first.id
    assert second.rolling_summary_before_hash == first.rolling_summary_after_hash


def test_self_reference_is_blocked_by_service(db_session):
    invention = _invention(db_session)
    service = _service(db_session)
    record = service.create(invention.id, RAW)

    with pytest.raises(ConversationImportError, match="자기 자신"):
        service.set_previous(record.id, record.id)


def test_self_reference_is_blocked_by_db_check_constraint(db_session):
    """서비스를 건너뛰어도 DB가 막는다 — CHECK 제약을 실제로 확인한다."""
    invention = _invention(db_session)
    record = _service(db_session).create(invention.id, RAW)
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "UPDATE conversation_imports "
                "SET previous_conversation_import_id = id WHERE id = :id"
            ),
            {"id": record.id},
        )


def test_previous_from_another_invention_is_blocked(db_session):
    """FK로는 못 막는다 — 다른 발명의 대화도 유효한 참조이기 때문이다."""
    first = _invention(db_session, "첫 번째 발명")
    second = _invention(db_session, "두 번째 발명")
    service = _service(db_session)

    a = service.create(first.id, RAW)
    b = service.create(second.id, RAW)

    with pytest.raises(ConversationImportError, match="다른 발명"):
        service.set_previous(b.id, a.id)

    assert service.get(b.id).previous_conversation_import_id is None


def test_previous_pointing_at_missing_record_is_rejected(db_session):
    invention = _invention(db_session)
    service = _service(db_session)
    record = service.create(invention.id, RAW)

    with pytest.raises(ConversationImportError, match="이전 대화를 찾을 수 없"):
        service.set_previous(record.id, "없는-대화-id")


def test_db_rejects_previous_id_that_does_not_exist(db_session):
    invention = _invention(db_session)
    record = _service(db_session).create(invention.id, RAW)

    record.previous_conversation_import_id = "존재하지-않는-id"
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# 분량 제한 (§9)
# ---------------------------------------------------------------------------


def test_too_short_content_is_rejected_with_both_numbers(db_session):
    invention = _invention(db_session)

    with pytest.raises(RawContentTooShortError) as exc:
        _service(db_session).create(invention.id, "짧다")

    message = str(exc.value)
    assert "2자" in message  # 현재 길이
    assert "200자" in message  # 허용 길이


def test_exactly_300k_chars_is_allowed(db_session):
    invention = _invention(db_session)

    record = _service(db_session).create(invention.id, "가" * 300_000)

    assert record.raw_content_length == 300_000


def test_over_300k_chars_is_blocked_before_saving(db_session):
    invention = _invention(db_session)
    service = _service(db_session)

    with pytest.raises(RawContentTooLongError):
        service.create(invention.id, "가" * 300_001)

    assert service.list_for_invention(invention.id) == []


def test_length_is_counted_in_characters_not_bytes(db_session):
    """한글은 UTF-8에서 3바이트다 — 바이트로 재면 한글 대화가 3배 빨리 막힌다."""
    invention = _invention(db_session)
    korean = "가" * 200_000

    record = _service(db_session).create(invention.id, korean)

    assert record.raw_content_length == 200_000
    assert len(korean.encode("utf-8")) == 600_000  # 바이트 기준이면 이미 초과


def test_long_content_is_never_truncated(db_session):
    invention = _invention(db_session)
    long_text = "가" * 299_999 + "끝"

    record = _service(db_session).create(invention.id, long_text)

    assert record.raw_content.endswith("끝")
    assert len(record.raw_content) == 300_000
