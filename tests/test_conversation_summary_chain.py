"""누적 요약 체인 무결성 + Soft Delete (Conversation Engine 1단계).

1단계에서는 요약을 **생성하지 않는다.** 대신 고정된 Fixture 요약을
넣어 두고, 체인이 끊겼는지 판정하는 규칙만 확정한다 — AI 호출이 전혀
없어야 이 검사가 언제든 돌 수 있기 때문이다.
"""
from __future__ import annotations

import pytest

from src.conversations.hashing import hash_summary_text
from src.conversations.service import ConversationImportService
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService

RAW = "대화 원문. 그래핀 섬유와 유리 기판에 대해 이야기했다. " * 15


def _setup(db_session, count: int = 3):
    invention = InventionService(db_session).quick_create(
        QuickIdeaInput(memo="유리 기판 관통 전극")
    )
    service = ConversationImportService(db_session)
    records = []
    for i in range(count):
        record = service.create(invention.id, RAW + str(i))
        service.update_summary(record.id, f"{i + 1}회차까지의 누적 요약")
        records.append(record)
    return invention, service, records


def _statuses(service, invention_id):
    return [check.status for check in service.validate_summary_chain(invention_id)]


# ---------------------------------------------------------------------------
# 정상 체인
# ---------------------------------------------------------------------------


def test_healthy_chain_is_valid(db_session):
    invention, service, records = _setup(db_session)

    assert _statuses(service, invention.id) == ["valid", "valid", "valid"]


def test_first_record_has_no_previous_link(db_session):
    invention, service, records = _setup(db_session, count=1)

    first = records[0]
    assert first.previous_conversation_import_id is None
    assert first.rolling_summary_before_hash is None
    assert _statuses(service, invention.id) == ["valid"]


def test_each_record_points_at_the_previous_after_hash(db_session):
    invention, service, records = _setup(db_session)

    for earlier, later in zip(records, records[1:]):
        assert later.previous_conversation_import_id == earlier.id
        assert later.rolling_summary_before_hash == earlier.rolling_summary_after_hash


def test_summary_hash_is_content_based(db_session):
    invention, service, records = _setup(db_session, count=1)

    expected = hash_summary_text("1회차까지의 누적 요약")
    assert records[0].rolling_summary_after_hash == expected


def test_summary_hash_ignores_only_line_endings_and_padding(db_session):
    """무결성 해시라 의미 정규화는 하지 않는다 — 줄바꿈·BOM·앞뒤 공백만."""
    assert hash_summary_text("한 줄\r\n두 줄") == hash_summary_text("한 줄\n두 줄")
    assert hash_summary_text("  요약  ") == hash_summary_text("요약")
    assert hash_summary_text("﻿요약") == hash_summary_text("요약")
    # 내용이 다르면 반드시 달라야 한다 (동의어 치환 같은 걸 하면 안 된다).
    assert hash_summary_text("그래핀 실") != hash_summary_text("그래핀 섬유")


def test_summary_hash_of_empty_is_none():
    assert hash_summary_text(None) is None
    assert hash_summary_text("") is None
    assert hash_summary_text("   \n  ") is None


# ---------------------------------------------------------------------------
# 깨진 체인
# ---------------------------------------------------------------------------


def test_missing_previous_link_is_detected(db_session):
    invention, service, records = _setup(db_session)

    records[1].previous_conversation_import_id = None
    db_session.flush()

    assert _statuses(service, invention.id)[1] == "missing_previous"


def test_before_hash_mismatch_is_detected(db_session):
    """1회차 요약을 나중에 고치면 2회차는 다른 요약 위에 얹혀 있게 된다."""
    invention, service, records = _setup(db_session)

    service.update_summary(records[0].id, "1회차 요약을 나중에 고쳤다")

    statuses = _statuses(service, invention.id)
    assert statuses[0] == "valid"
    assert statuses[1] == "before_hash_mismatch"


def test_first_record_with_stale_before_hash_is_detected(db_session):
    invention, service, records = _setup(db_session, count=1)

    records[0].rolling_summary_before_hash = "a" * 64
    db_session.flush()

    assert _statuses(service, invention.id) == ["before_hash_mismatch"]


def test_missing_after_summary_is_detected(db_session):
    invention = InventionService(db_session).quick_create(QuickIdeaInput(memo="발명"))
    service = ConversationImportService(db_session)
    service.create(invention.id, RAW)  # 요약을 만들지 않은 상태

    assert _statuses(service, invention.id) == ["missing_after_summary"]


def test_needs_regeneration_flag_is_reported(db_session):
    invention, service, records = _setup(db_session, count=1)

    service.update_summary(
        records[0].id, "요약", status="needs_regeneration"
    )

    assert _statuses(service, invention.id) == ["needs_regeneration"]


def test_update_summary_rejects_unknown_status(db_session):
    invention, service, records = _setup(db_session, count=1)

    with pytest.raises(ValueError, match="summary_status"):
        service.update_summary(records[0].id, "요약", status="무엇인가")


# ---------------------------------------------------------------------------
# Soft Delete
# ---------------------------------------------------------------------------


def test_soft_delete_keeps_the_row_and_the_content(db_session):
    invention, service, records = _setup(db_session, count=1)

    service.soft_delete(records[0].id)

    stored = service.get(records[0].id)
    assert stored is not None
    assert stored.is_deleted is True
    assert stored.deleted_at is not None
    assert stored.raw_content.startswith("대화 원문")  # 원문은 그대로
    assert stored.rolling_summary_after == "1회차까지의 누적 요약"


def test_soft_deleted_import_is_hidden_from_the_default_list(db_session):
    invention, service, records = _setup(db_session)

    service.soft_delete(records[1].id)

    visible = [r.sequence_no for r in service.list_for_invention(invention.id)]
    everything = [
        r.sequence_no
        for r in service.list_for_invention(invention.id, include_deleted=True)
    ]
    assert visible == [1, 3]
    assert everything == [1, 2, 3]


def test_deleting_a_middle_node_marks_the_next_for_regeneration(db_session):
    """뒤 회차의 요약이 이제 없는 회차 위에 얹혀 있다 — 다시 만들어야 한다."""
    invention, service, records = _setup(db_session)

    service.soft_delete(records[1].id)

    assert service.get(records[2].id).summary_status == "needs_regeneration"
    statuses = _statuses(service, invention.id)
    assert statuses == ["valid", "needs_regeneration"]


def test_deleted_node_is_still_readable_as_evidence(db_session):
    """삭제된 행도 체인 검증의 근거로는 읽을 수 있어야 한다 (§12)."""
    invention, service, records = _setup(db_session)
    service.soft_delete(records[1].id)

    checks = service.validate_summary_chain(invention.id, include_deleted=True)

    assert [c.sequence_no for c in checks] == [1, 2, 3]
    # 삭제된 2회차 자체는 여전히 정상적인 고리다.
    assert checks[1].status == "valid"


def test_deleting_does_not_erase_the_summary_text(db_session):
    """복원하면 그대로 다시 유효해져야 하므로 요약을 지우지 않는다."""
    invention, service, records = _setup(db_session)

    service.soft_delete(records[1].id)

    assert service.get(records[1].id).rolling_summary_after is not None


def test_restore_puts_it_back_in_the_same_position(db_session):
    invention, service, records = _setup(db_session)
    service.soft_delete(records[1].id)

    restored = service.restore(records[1].id)

    assert restored.is_deleted is False
    assert restored.deleted_at is None
    assert restored.sequence_no == 2
    assert [r.sequence_no for r in service.list_for_invention(invention.id)] == [1, 2, 3]


def test_restore_marks_the_following_for_revalidation(db_session):
    invention, service, records = _setup(db_session)
    service.soft_delete(records[1].id)

    service.restore(records[1].id)

    # 체인이 한 번 흔들렸으니 그대로 믿지 않는다.
    assert service.get(records[2].id).summary_status == "needs_regeneration"


def test_chain_recovers_after_restore_and_regeneration(db_session):
    invention, service, records = _setup(db_session)
    service.soft_delete(records[1].id)
    service.restore(records[1].id)

    service.update_summary(records[2].id, "3회차까지의 누적 요약")

    assert _statuses(service, invention.id) == ["valid", "valid", "valid"]


def test_soft_delete_is_idempotent(db_session):
    invention, service, records = _setup(db_session, count=1)

    first = service.soft_delete(records[0].id)
    deleted_at = first.deleted_at
    second = service.soft_delete(records[0].id)

    assert second.deleted_at == deleted_at


def test_restore_of_a_live_record_is_a_noop(db_session):
    invention, service, records = _setup(db_session, count=1)

    assert service.restore(records[0].id).is_deleted is False


# ---------------------------------------------------------------------------
# 삭제 영향 미리보기 (§28.2)
# ---------------------------------------------------------------------------


def test_delete_impact_lists_the_following_conversations(db_session):
    invention, service, records = _setup(db_session)

    impact = service.delete_impact(records[1].id)

    assert impact.sequence_no == 2
    assert impact.following_sequence_nos == [3]
    assert impact.is_applied is False
