"""analysis_json의 DB 왕복 — 저장했다 읽으면 잃는 것이 없어야 한다.

0단계에서 만든 계약(`analysis_schema`)과 1단계의 TEXT 컬럼 사이에
손실이 생기면, 그건 계약이 지켜지지 않는다는 뜻이다. 특히 다음 셋은
잃기 쉬워서 따로 확인한다.

- 모르는 필드 (다음 버전이 추가한 것)
- `_unmigrated_raw` (미래 스키마 원본)
- 사용자 판단 (`user_review`) — 이건 사람이 손으로 넣은 값이라
  잃으면 복구할 방법이 없다
"""
from __future__ import annotations

import json

import pytest

from src.conversations.analysis_schema import (
    AnalysisItem,
    ApplicationEntry,
    SourceReference,
    UserDecision,
    dumps_analysis,
    load_analysis,
    loads_analysis,
)
from src.conversations.service import ConversationImportService
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService

RAW = "그래핀 섬유 관통 배치에 대한 대화 원문. " * 20


def _setup(db_session):
    invention = InventionService(db_session).quick_create(
        QuickIdeaInput(memo="유리 기판 관통 전극")
    )
    service = ConversationImportService(db_session)
    return service, service.create(invention.id, RAW)


def _roundtrip(db_session, document):
    """저장 → commit → 세션 만료 → 다시 읽기까지 실제로 왕복시킨다."""
    service, record = _setup(db_session)
    service.update_analysis(record.id, document)
    db_session.commit()
    db_session.expire_all()
    return service.load_document(service.get(record.id))


# ---------------------------------------------------------------------------
# 기본 왕복
# ---------------------------------------------------------------------------


def test_empty_analysis_survives_roundtrip(db_session):
    restored = _roundtrip(db_session, load_analysis(None))

    assert restored.all_items() == []
    assert restored.decisions() == []
    assert restored.is_unmigrated is False


def test_items_survive_roundtrip(db_session):
    document = load_analysis(None)
    document.set_items(
        "new_elements",
        [
            AnalysisItem(
                item_id="a1b2c3d4e5f60718",
                text="그래핀 섬유를 장력 상태로 관통 배치한다",
                change_type="new",
                target_field="core_principle",
                confidence=82,
            )
        ],
    )

    restored = _roundtrip(db_session, document)

    item = restored.all_items()[0]
    assert item.item_id == "a1b2c3d4e5f60718"
    assert item.text == "그래핀 섬유를 장력 상태로 관통 배치한다"
    assert item.confidence == 82


def test_korean_is_stored_readable_not_escaped(db_session):
    """DB를 직접 열어 봤을 때 사람이 읽을 수 있어야 한다."""
    service, record = _setup(db_session)
    document = load_analysis(None)
    document.set_items(
        "new_elements",
        [AnalysisItem(item_id="k1", text="유리 기판 관통 전극", change_type="new")],
    )

    service.update_analysis(record.id, document)

    assert "유리 기판 관통 전극" in record.analysis_json
    assert "\\u" not in record.analysis_json


def test_emoji_survives_roundtrip(db_session):
    document = load_analysis(None)
    document.set_items(
        "new_elements",
        [AnalysisItem(item_id="e1", text="핵심 아이디어 🔬✨ 확정", change_type="new")],
    )

    restored = _roundtrip(db_session, document)

    assert restored.all_items()[0].text == "핵심 아이디어 🔬✨ 확정"


def test_long_text_survives_roundtrip(db_session):
    long_text = "장력을 유지한 그래핀 섬유를 관통시킨다. " * 2_000
    document = load_analysis(None)
    document.set_items(
        "new_elements", [AnalysisItem(item_id="L1", text=long_text, change_type="new")]
    )

    restored = _roundtrip(db_session, document)

    assert restored.all_items()[0].text == long_text


def test_source_references_survive_roundtrip(db_session):
    document = load_analysis(None)
    document.set_items(
        "new_elements",
        [
            AnalysisItem(
                item_id="s1",
                text="상온에서 삽입한다",
                change_type="new",
                sources=[
                    SourceReference(
                        conversation_import_id="imp-1",
                        message_index=7,
                        source_start=120,
                        source_end=140,
                        source_excerpt="상온에서 삽입한다",
                        matched=True,
                    )
                ],
            )
        ],
    )

    restored = _roundtrip(db_session, document)

    ref = restored.all_items()[0].sources[0]
    assert ref.message_index == 7
    assert (ref.source_start, ref.source_end) == (120, 140)
    assert ref.source_excerpt == "상온에서 삽입한다"
    assert ref.matched is True


# ---------------------------------------------------------------------------
# 세 계층
# ---------------------------------------------------------------------------


def test_user_decisions_survive_roundtrip(db_session):
    document = load_analysis(None)
    document.set_items(
        "new_elements", [AnalysisItem(item_id="d1", text="제안", change_type="new")]
    )
    document.set_decision(
        UserDecision(
            item_id="d1",
            decision="edited",
            edited_text="사용자가 고친 문장",
            user_note="표현만 다듬음",
        )
    )

    restored = _roundtrip(db_session, document)

    decision = restored.decision_of("d1")
    assert decision.decision == "edited"
    assert decision.edited_text == "사용자가 고친 문장"
    assert decision.user_note == "표현만 다듬음"


def test_application_result_survives_roundtrip(db_session):
    document = load_analysis(None)
    document.set_items(
        "new_elements", [AnalysisItem(item_id="p1", text="제안", change_type="new")]
    )
    document.record_application(
        [
            ApplicationEntry(
                item_id="p1",
                status="skipped_duplicate",
                target_field="core_principle",
                error_message="이미 같은 문장이 있습니다",
            )
        ],
        revision_id="rev-1",
    )

    restored = _roundtrip(db_session, document)

    entry = restored.application_of("p1")
    assert entry.status == "skipped_duplicate"
    assert entry.error_message == "이미 같은 문장이 있습니다"
    assert restored.application_revision_id() == "rev-1"


def test_approval_and_application_stay_separate_across_roundtrip(db_session):
    """승인했다고 반영된 게 아니다 — DB를 왕복해도 이 구분이 남아야 한다."""
    document = load_analysis(None)
    document.set_items(
        "new_elements", [AnalysisItem(item_id="x1", text="제안", change_type="new")]
    )
    document.set_decision(UserDecision(item_id="x1", decision="approved"))

    restored = _roundtrip(db_session, document)

    assert restored.decision_of("x1").decision == "approved"
    assert restored.application_of("x1") is None


# ---------------------------------------------------------------------------
# 모르는 데이터 보존
# ---------------------------------------------------------------------------


def test_unknown_fields_survive_roundtrip(db_session):
    """다음 버전이 추가한 필드를 지금 버전이 지워 버리면 안 된다."""
    raw = load_analysis(None).to_json()
    raw["ai_analysis"]["new_elements"] = [
        {
            "item_id": "u1",
            "text": "제안",
            "change_type": "new",
            "미래에_추가된_필드": {"중첩": [1, 2, 3]},
        }
    ]

    restored = _roundtrip(db_session, load_analysis(raw))

    assert restored.all_items()[0].extra["미래에_추가된_필드"] == {"중첩": [1, 2, 3]}


def test_future_schema_is_preserved_in_unmigrated_raw(db_session):
    service, record = _setup(db_session)
    future = {"schema_version": "99.0", "무엇인가": "미래 데이터"}

    service.update_analysis(record.id, load_analysis(future))
    db_session.commit()
    db_session.expire_all()

    restored = service.load_document(service.get(record.id))
    assert restored.is_unmigrated is True
    assert restored.unmigrated_raw["무엇인가"] == "미래 데이터"


def test_legacy_v0_analysis_is_migrated_on_read(db_session):
    service, record = _setup(db_session)
    # 버전 표시가 없는 예전 구조를 직접 밀어 넣는다.
    record.analysis_json = json.dumps(
        {"new_elements": [{"item_id": "old1", "text": "예전 제안"}]},
        ensure_ascii=False,
    )
    db_session.commit()
    db_session.expire_all()

    restored = service.load_document(service.get(record.id))

    assert restored.schema_version == "1.0"
    assert [i.item_id for i in restored.all_items()] == ["old1"]


# ---------------------------------------------------------------------------
# 깨진 JSON
# ---------------------------------------------------------------------------


def test_corrupted_json_does_not_raise(db_session):
    """대화 목록을 여는 것만으로 앱 전체가 멈추면 안 된다."""
    service, record = _setup(db_session)
    record.analysis_json = '{"ai_analysis": {"new_elements": [ 깨진'
    db_session.commit()
    db_session.expire_all()

    restored = service.load_document(service.get(record.id))

    assert restored.all_items() == []
    assert restored.coercion_errors  # 왜 실패했는지는 남는다


def test_corrupted_json_keeps_the_original_text_for_recovery(db_session):
    service, record = _setup(db_session)
    broken = '{"ai_analysis": 되살릴 수 있어야 하는 원문'
    record.analysis_json = broken
    db_session.commit()
    db_session.expire_all()

    restored = service.load_document(service.get(record.id))

    assert restored.is_unmigrated is True
    assert restored.unmigrated_raw["corrupted_text"] == broken


def test_empty_string_json_is_treated_as_empty_analysis(db_session):
    assert loads_analysis("").all_items() == []
    assert loads_analysis("   ").all_items() == []
    assert loads_analysis(None).all_items() == []


# ---------------------------------------------------------------------------
# 직렬화 형식 자체가 계약이다
# ---------------------------------------------------------------------------


def test_serialization_is_deterministic(db_session):
    """같은 내용이면 항상 같은 문자열 — 변경 감지를 문자열 비교로 할 수 있다."""
    first = load_analysis(None)
    first.set_items(
        "new_elements",
        [AnalysisItem(item_id="z1", text="가나다", change_type="new")],
    )
    second = load_analysis(first.to_json())

    assert dumps_analysis(first) == dumps_analysis(second)


def test_serialization_sorts_keys(db_session):
    text = dumps_analysis(load_analysis(None))
    keys = [k for k in json.loads(text)]

    assert keys == sorted(keys)


def test_serialization_has_no_padding_whitespace(db_session):
    text = dumps_analysis(load_analysis(None))

    assert ", " not in text
    assert ": " not in text
    assert "\n" not in text


def test_dumps_analysis_of_none_is_none():
    assert dumps_analysis(None) is None


def test_columns_are_synced_from_the_document(db_session):
    """문서가 정본이고 컬럼은 사본이다 — 저장할 때 한 번에 맞춘다."""
    service, record = _setup(db_session)
    document = load_analysis(None)
    document.set_meta(provider="anthropic", model="claude-sonnet-5")
    updated = document.replace_ai_analysis({})

    service.update_analysis(record.id, updated)

    assert record.analysis_version == updated.analysis_version
    assert record.analysis_schema_version == updated.schema_version
    assert record.provider == "anthropic"
    assert record.model == "claude-sonnet-5"
    assert record.analysis_status == "analyzed"


def test_update_analysis_rejects_unknown_status(db_session):
    service, record = _setup(db_session)

    with pytest.raises(ValueError, match="analysis_status"):
        service.update_analysis(record.id, load_analysis(None), status="무엇인가")
