"""analysis_json 스키마 계약 검증 (설계 문서 §26).

이 파일이 지키는 것: **구조가 무너지지 않는다.**
- 어떤 입력이 와도 예외로 앱이 죽지 않는다
- 없는 필드는 기본값, 모르는 필드는 보존
- 미래 버전은 원본을 잃지 않는다
- JSON 키 문자열은 analysis_schema.py 밖에 존재하지 않는다 (AST 검사)
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from src.conversations.analysis_schema import (
    ACTOR_SYSTEM,
    ACTOR_USER,
    AnalysisDocument,
    AnalysisItem,
    AnalysisKeys,
    ApplicationEntry,
    ApplicationStatus,
    DeclaredStatus,
    DeclaredStatusProtectedError,
    DerivedStatus,
    ITEM_BUCKETS,
    LEGACY_VERSION,
    MessageRef,
    OriginStance,
    OverlapInfo,
    SourceReference,
    UserDecision,
    empty_analysis,
    load_analysis,
    migrate_v0_to_v1,
    normalize_v1,
)
from src.conversations.constants import CURRENT_SCHEMA_VERSION


def _doc_with_item(**item_overrides) -> AnalysisDocument:
    """new_elements에 항목 1개가 든 문서를 만든다."""
    doc = load_analysis(None)
    item = AnalysisItem(
        item_id="item-1",
        change_type="added",
        target_field="core_principle",
        text="그래핀 섬유를 장력 상태로 관통 배치",
        **item_overrides,
    )
    doc.set_items(AnalysisKeys.NEW_ELEMENTS, [item])
    return doc


# ---------------------------------------------------------------------------
# 빈 값 / 기본 구조
# ---------------------------------------------------------------------------


def test_load_none_returns_v1_default_document():
    doc = load_analysis(None)
    assert doc.schema_version == CURRENT_SCHEMA_VERSION
    assert doc.analysis_version == 1
    assert doc.all_items() == []
    assert doc.decisions() == []
    assert doc.application_entries() == []
    assert doc.is_unmigrated is False


def test_load_empty_dict_returns_v1_default_document():
    doc = load_analysis({})
    assert doc.schema_version == CURRENT_SCHEMA_VERSION
    assert doc.all_items() == []


def test_empty_analysis_has_all_three_layers():
    raw = empty_analysis()
    assert AnalysisKeys.AI_ANALYSIS in raw
    assert AnalysisKeys.USER_REVIEW in raw
    assert AnalysisKeys.APPLICATION_RESULT in raw


def test_missing_fields_fall_back_to_defaults_without_error():
    doc = load_analysis({AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION})
    assert doc.provider == ""
    assert doc.model is None
    assert doc.messages() == []
    assert doc.all_items() == []


def test_item_missing_fields_get_defaults():
    doc = load_analysis({
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        AnalysisKeys.AI_ANALYSIS: {AnalysisKeys.NEW_ELEMENTS: [{"item_id": "x"}]},
    })
    item = doc.all_items()[0]
    assert item.item_id == "x"
    assert item.confidence == 0
    assert item.declared_status == DeclaredStatus.PROPOSED
    assert item.origin_stance == OriginStance.AI_PROPOSED
    assert item.derived_status == []
    assert item.sources == []


# ---------------------------------------------------------------------------
# 잘못된 타입
# ---------------------------------------------------------------------------


def test_wrong_types_are_coerced_with_recorded_errors():
    doc = load_analysis({
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        AnalysisKeys.ANALYSIS_VERSION: "이건 숫자가 아님",
        AnalysisKeys.PROVIDER: 12345,
        AnalysisKeys.MESSAGES: "배열이 아님",
    })
    assert doc.analysis_version == 1        # 안전한 기본값
    assert doc.provider == ""
    assert doc.messages() == []
    assert doc.coercion_errors, "잘못된 타입이 오류 정보로 남아야 한다"


def test_numeric_string_is_accepted_as_int():
    doc = load_analysis({
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        AnalysisKeys.ANALYSIS_VERSION: "3",
    })
    assert doc.analysis_version == 3


def test_bool_is_not_accepted_as_int():
    """bool은 int의 하위형이라 그냥 두면 True가 1로 새어 들어간다."""
    doc = load_analysis({
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        AnalysisKeys.ANALYSIS_VERSION: True,
    })
    assert doc.analysis_version == 1
    assert doc.coercion_errors


def test_item_list_entry_that_is_not_a_dict_does_not_crash():
    doc = load_analysis({
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        AnalysisKeys.AI_ANALYSIS: {AnalysisKeys.NEW_ELEMENTS: ["문자열", 42, None]},
    })
    assert len(doc.all_items()) == 3       # 기본값으로 채워진 항목들
    assert doc.coercion_errors


def test_non_dict_analysis_json_is_preserved_not_raised():
    doc = load_analysis(["예상치 못한 배열"])  # type: ignore[arg-type]
    assert doc.is_unmigrated is True
    assert doc.coercion_errors


# ---------------------------------------------------------------------------
# 알 수 없는 필드 보존
# ---------------------------------------------------------------------------


def test_unknown_top_level_fields_are_preserved():
    doc = load_analysis({
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        "미래에_추가될_필드": {"a": 1},
    })
    assert doc.to_json()["미래에_추가될_필드"] == {"a": 1}


def test_unknown_item_fields_are_preserved():
    doc = load_analysis({
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        AnalysisKeys.AI_ANALYSIS: {
            AnalysisKeys.NEW_ELEMENTS: [{"item_id": "x", "새필드": "값"}]
        },
    })
    assert doc.all_items()[0].extra == {"새필드": "값"}
    dumped = doc.to_json()[AnalysisKeys.AI_ANALYSIS][AnalysisKeys.NEW_ELEMENTS][0]
    assert dumped["새필드"] == "값"


def test_unknown_nested_layer_fields_are_preserved():
    doc = load_analysis({
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        AnalysisKeys.USER_REVIEW: {"미래_판단_필드": [1, 2]},
    })
    assert doc.to_json()[AnalysisKeys.USER_REVIEW]["미래_판단_필드"] == [1, 2]


# ---------------------------------------------------------------------------
# 마이그레이션
# ---------------------------------------------------------------------------


def test_v0_fixture_migrates_to_v1_three_layer_structure():
    """가상 v0: 버전 표기가 없고 항목이 최상위에 평평하게 있던 형식."""
    v0 = {
        "new_elements": [{"item_id": "a", "text": "그래핀 섬유"}],
        "open_questions": [{"text": "장력 유지가 되는가?"}],
        "provider": "mock",
    }
    doc = load_analysis(v0)

    assert doc.schema_version == CURRENT_SCHEMA_VERSION
    assert doc.is_unmigrated is False
    assert [i.item_id for i in doc.new_elements()] == ["a"]
    assert len(doc.open_questions()) == 1
    assert doc.provider == "mock"
    assert doc.decisions() == []           # v0에는 사용자 판단 개념이 없었다


def test_migrate_v0_keeps_unknown_v0_fields():
    v0 = {"new_elements": [], "예전에만_있던_필드": "값"}
    migrated = migrate_v0_to_v1(v0)
    assert migrated[AnalysisKeys.EXTRA]["예전에만_있던_필드"] == "값"


def test_migrate_v0_does_not_mutate_input():
    v0 = {"new_elements": [{"item_id": "a"}]}
    snapshot = copy.deepcopy(v0)
    migrate_v0_to_v1(v0)
    assert v0 == snapshot


def test_future_version_is_preserved_in_unmigrated_raw():
    future = {
        AnalysisKeys.SCHEMA_VERSION: "99.0",
        "완전히_새로운_구조": {"중요한": "데이터"},
    }
    doc = load_analysis(future)

    assert doc.is_unmigrated is True
    assert doc.unmigrated_raw == future     # 원본이 통째로 살아 있다
    assert doc.all_items() == []            # 해석은 못 하지만 죽지도 않는다


def test_unparseable_version_is_treated_as_future_and_preserved():
    doc = load_analysis({AnalysisKeys.SCHEMA_VERSION: "알수없음", "x": 1})
    assert doc.is_unmigrated is True
    assert doc.unmigrated_raw["x"] == 1


def test_migration_chain_cannot_loop_forever(monkeypatch):
    """버전이 제자리를 도는 마이그레이션이 등록돼도 무한루프에 빠지지 않는다."""
    import src.conversations.analysis_schema as schema

    monkeypatch.setitem(schema._MIGRATIONS, "0.5", lambda raw: raw)
    doc = load_analysis({AnalysisKeys.SCHEMA_VERSION: "0.5"})
    assert doc.is_unmigrated is True        # 루프 대신 원본 보존으로 빠진다


# ---------------------------------------------------------------------------
# 불변성 / 왕복
# ---------------------------------------------------------------------------


def test_load_analysis_does_not_mutate_input():
    raw = {
        AnalysisKeys.SCHEMA_VERSION: CURRENT_SCHEMA_VERSION,
        AnalysisKeys.AI_ANALYSIS: {AnalysisKeys.NEW_ELEMENTS: [{"item_id": "a"}]},
    }
    snapshot = copy.deepcopy(raw)

    doc = load_analysis(raw)
    doc.set_items(AnalysisKeys.NEW_ELEMENTS, [AnalysisItem(item_id="바뀜")])

    assert raw == snapshot, "load_analysis()가 입력 dict를 수정하면 안 된다"


def test_to_json_returns_a_copy_not_internal_state():
    doc = _doc_with_item()
    dumped = doc.to_json()
    dumped[AnalysisKeys.AI_ANALYSIS][AnalysisKeys.NEW_ELEMENTS].clear()
    assert len(doc.all_items()) == 1, "to_json() 결과를 바꿔도 문서가 바뀌면 안 된다"


def test_roundtrip_preserves_content():
    doc = _doc_with_item(confidence=94, derived_status=[DerivedStatus.NEWLY_PROPOSED])
    doc.set_decision(UserDecision(item_id="item-1", decision="approved"))
    doc.record_application([ApplicationEntry(
        item_id="item-1", status=ApplicationStatus.APPLIED,
        target_field="core_principle")], revision_id="rev-7")

    reloaded = load_analysis(doc.to_json())

    assert reloaded.all_items()[0].confidence == 94
    assert reloaded.all_items()[0].derived_status == [DerivedStatus.NEWLY_PROPOSED]
    assert reloaded.decision_of("item-1").decision == "approved"
    assert reloaded.application_of("item-1").status == ApplicationStatus.APPLIED
    assert reloaded.application_revision_id() == "rev-7"


def test_roundtrip_is_stable_across_two_passes():
    doc = _doc_with_item(confidence=50)
    once = load_analysis(doc.to_json()).to_json()
    twice = load_analysis(once).to_json()
    assert once == twice


# ---------------------------------------------------------------------------
# 세 계층 분리 (§27.1)
# ---------------------------------------------------------------------------


def test_recording_a_decision_does_not_touch_ai_analysis():
    doc = _doc_with_item()
    before = copy.deepcopy(doc.to_json()[AnalysisKeys.AI_ANALYSIS])

    doc.set_decision(UserDecision(item_id="item-1", decision="rejected"))

    assert doc.to_json()[AnalysisKeys.AI_ANALYSIS] == before


def test_recording_application_does_not_touch_user_review():
    doc = _doc_with_item()
    doc.set_decision(UserDecision(item_id="item-1", decision="approved"))
    before = copy.deepcopy(doc.to_json()[AnalysisKeys.USER_REVIEW])

    doc.record_application([ApplicationEntry(
        item_id="item-1", status=ApplicationStatus.SKIPPED_DUPLICATE)])

    assert doc.to_json()[AnalysisKeys.USER_REVIEW] == before


def test_replace_ai_analysis_returns_new_document_and_keeps_original():
    doc = _doc_with_item()
    doc.set_decision(UserDecision(item_id="item-1", decision="approved"))

    new_doc = doc.replace_ai_analysis({AnalysisKeys.NEW_ELEMENTS: []})

    assert doc.all_items(), "원본 문서는 그대로여야 한다"
    assert new_doc.all_items() == []
    assert new_doc.analysis_version == doc.analysis_version + 1
    assert new_doc.decision_of("item-1") is not None, "판단은 이어져야 한다"


# ---------------------------------------------------------------------------
# declared_status 보호 / derived_status (§9.4)
# ---------------------------------------------------------------------------


def test_system_cannot_change_declared_status():
    doc = _doc_with_item()
    with pytest.raises(DeclaredStatusProtectedError):
        doc.set_declared_status("item-1", DeclaredStatus.REJECTED, actor=ACTOR_SYSTEM)
    assert doc.all_items()[0].declared_status == DeclaredStatus.PROPOSED


def test_user_can_change_declared_status():
    doc = _doc_with_item()
    doc.set_declared_status("item-1", DeclaredStatus.ADOPTED, actor=ACTOR_USER)
    assert doc.all_items()[0].declared_status == DeclaredStatus.ADOPTED


def test_setting_derived_status_never_touches_declared_status():
    """'최근 미언급'이라는 계산 결과가 사용자의 '채택'을 덮어쓰면 안 된다."""
    doc = _doc_with_item()
    doc.set_declared_status("item-1", DeclaredStatus.ADOPTED, actor=ACTOR_USER)

    doc.set_derived_status("item-1", [DerivedStatus.DORMANT])

    item = doc.all_items()[0]
    assert item.declared_status == DeclaredStatus.ADOPTED
    assert item.derived_status == [DerivedStatus.DORMANT]


def test_derived_status_supports_multiple_values_and_dedupes():
    doc = _doc_with_item()
    doc.set_derived_status(
        "item-1",
        [DerivedStatus.NEWLY_PROPOSED, DerivedStatus.DORMANT, DerivedStatus.NEWLY_PROPOSED],
    )
    assert doc.all_items()[0].derived_status == [
        DerivedStatus.NEWLY_PROPOSED, DerivedStatus.DORMANT]


def test_updating_unknown_item_raises():
    doc = _doc_with_item()
    with pytest.raises(KeyError):
        doc.set_derived_status("없는-항목", [DerivedStatus.DORMANT])


# ---------------------------------------------------------------------------
# 구조체 왕복
# ---------------------------------------------------------------------------


def test_source_reference_roundtrip():
    ref = SourceReference(
        conversation_import_id="conv-1", sequence_no=3, message_index=14,
        message_role="user", source_excerpt="실처럼 당겨서",
        source_start=100, source_end=107, confidence=91, matched=True)
    errors: list[str] = []
    back = SourceReference.from_json(ref.to_json(), "x", errors)
    assert back == ref
    assert errors == []


def test_message_ref_roundtrip():
    msg = MessageRef(message_index=2, role="assistant", content_hash="abc",
                     source_start=10, source_end=40)
    errors: list[str] = []
    assert MessageRef.from_json(msg.to_json(), "x", errors) == msg


def test_overlap_info_roundtrip():
    overlap = OverlapInfo(match_type="superset", overlap_with_import_id="conv-1",
                          already_imported_indices=[0, 1],
                          newly_added_indices=[2, 3], analyzed_range=[2, 3])
    errors: list[str] = []
    assert OverlapInfo.from_json(overlap.to_json(), "x", errors) == overlap


def test_document_stores_messages_and_overlap():
    doc = load_analysis(None)
    doc.set_messages([MessageRef(message_index=0, role="user", content_hash="h0")])
    doc.set_overlap(OverlapInfo(match_type="superset", newly_added_indices=[1]))

    reloaded = load_analysis(doc.to_json())
    assert reloaded.messages()[0].content_hash == "h0"
    assert reloaded.overlap().match_type == "superset"


def test_set_items_rejects_unknown_bucket():
    doc = load_analysis(None)
    with pytest.raises(ValueError):
        doc.set_items("존재하지_않는_버킷", [])


def test_all_item_buckets_are_reachable():
    doc = load_analysis(None)
    for i, bucket in enumerate(ITEM_BUCKETS):
        doc.set_items(bucket, [AnalysisItem(item_id=f"b{i}")])
    assert len(doc.all_items()) == len(ITEM_BUCKETS)


def test_normalize_v1_is_callable_directly():
    errors: list[str] = []
    out = normalize_v1({AnalysisKeys.PROVIDER: "mock"}, errors)
    assert out[AnalysisKeys.SCHEMA_VERSION] == CURRENT_SCHEMA_VERSION
    assert out[AnalysisKeys.PROVIDER] == "mock"


def test_legacy_version_constant_maps_to_v0_migration():
    assert LEGACY_VERSION in {"0"}


# ---------------------------------------------------------------------------
# AST 계약 검사 (§26.6) — JSON 키는 analysis_schema.py에만 존재한다
# ---------------------------------------------------------------------------

# 이 키들이 analysis_schema.py 밖에서 문자열 리터럴로 나타나면 접근자
# 계층을 우회한 것이다. 스키마를 바꿀 때 고쳐야 할 곳이 흩어지기 시작한다.
_GUARDED_KEYS = {
    "ai_analysis", "user_review", "application_result",
    "new_elements", "reinforced_elements", "modified_elements",
    "conflicting_elements", "rejected_elements",
    "open_questions", "source_references", "merge_proposals",
    "orphaned_decisions", "applied_items", "_unmigrated_raw",
}

# 검사 범위. 우선 Conversation Engine 안에서만 강제하고, Parser/Service/UI가
# 생기면 그 디렉터리도 여기에 추가한다.
_GUARDED_ROOTS = (Path(__file__).resolve().parents[1] / "src" / "conversations",)

_ALLOWED_FILES = {"analysis_schema.py"}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """docstring인 Constant 노드의 id 집합. 주석은 AST에 없으므로 신경 쓸 필요 없다."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def test_json_keys_are_not_referenced_outside_analysis_schema():
    """analysis_json의 키를 다른 파일에서 직접 문자열로 쓰지 않는다.

    AST로 검사하므로 주석·docstring 때문에 오탐하지 않는다
    (주석은 AST에 남지 않고, docstring은 명시적으로 제외한다).
    """
    violations: list[str] = []
    for root in _GUARDED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if path.name in _ALLOWED_FILES:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            skip = _docstring_nodes(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or id(node) in skip:
                    continue
                if isinstance(node.value, str) and node.value in _GUARDED_KEYS:
                    violations.append(
                        f"{path.name}:{node.lineno} — {node.value!r}를 직접 참조"
                    )

    assert not violations, (
        "analysis_schema.py 밖에서 JSON 키를 직접 썼습니다. "
        "AnalysisKeys 또는 접근자를 쓰세요:\n  " + "\n  ".join(violations)
    )


def test_ast_contract_check_actually_detects_a_violation(tmp_path):
    """계약 검사 자체가 동작하는지 확인한다 (검사기가 조용히 망가지면 무의미하다)."""
    offender = tmp_path / "offender.py"
    offender.write_text('def f(d):\n    return d["ai_analysis"]\n', encoding="utf-8")

    tree = ast.parse(offender.read_text(encoding="utf-8"))
    skip = _docstring_nodes(tree)
    found = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and id(n) not in skip
        and isinstance(n.value, str) and n.value in _GUARDED_KEYS
    ]
    assert found == ["ai_analysis"]


def test_ast_contract_check_ignores_docstrings():
    """docstring에 키 이름이 나와도 위반이 아니다."""
    source = '"""이 모듈은 ai_analysis 구조를 설명한다."""\nx = 1\n'
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    found = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and id(n) not in skip
        and isinstance(n.value, str) and n.value in _GUARDED_KEYS
    ]
    assert found == []
