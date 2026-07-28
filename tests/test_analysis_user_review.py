"""AI 분석 / 사용자 판단 / 실제 반영의 3계층 분리 검증 (설계 문서 §27).

이 파일이 지키는 것:
- 재분석해도 사용자 판단이 사라지지 않는다 (이게 깨지면 재분석 기능을
  아무도 쓰지 않는다 — 대화 12개짜리 발명에서 예전에 거절한 제안 40개를
  매번 다시 검토할 수는 없다)
- 유사하다는 이유만으로 승인을 자동 복사하지 않는다
- 승인과 실제 반영은 다르다
"""
from __future__ import annotations

import copy

from src.conversations.analysis_schema import (
    ACTOR_USER,
    AnalysisItem,
    AnalysisKeys,
    ApplicationEntry,
    ApplicationStatus,
    DeclaredStatus,
    DecisionStatus,
    UserDecision,
    load_analysis,
)
from src.conversations.hashing import (
    build_item_id,
    merge_user_reviews_after_reanalysis,
)


def _item(item_id: str, text: str, **kw) -> dict:
    base = {
        "item_id": item_id,
        "change_type": "added",
        "target_field": "core_principle",
        "text": text,
    }
    base.update(kw)
    return base


def _review(item_id: str, decision: str, **kw) -> dict:
    base = {"item_id": item_id, "decision": decision, "edited_text": None}
    base.update(kw)
    return base


def _exact_similarity(a: str, b: str) -> float:
    """테스트용 유사도: 완전히 같으면 1.0, 아니면 0.0."""
    return 1.0 if a == b else 0.0


def _fixed_similarity(score: float):
    def fn(a: str, b: str) -> float:
        return 1.0 if a == b else score
    return fn


# ---------------------------------------------------------------------------
# 재분석 — 1등급: 동일 item_id
# ---------------------------------------------------------------------------


def test_same_item_id_keeps_previous_decision():
    prev_items = [_item("id-a", "그래핀 섬유를 관통 배치")]
    prev_reviews = [_review("id-a", DecisionStatus.APPROVED)]
    new_items = [_item("id-a", "그래핀 섬유를 관통 배치")]

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, new_items, similarity_fn=_exact_similarity)

    assert merged.items[0]["match_type"] == "exact"
    assert merged.items[0]["carried_over"] is True
    assert [d["item_id"] for d in merged.carried_decisions] == ["id-a"]
    assert merged.orphaned_decisions == []


def test_previously_rejected_item_is_not_asked_again():
    """거절 판단이 유지되는 것이 재분석의 실질적 가치다."""
    prev_items = [_item("id-a", "공정 30% 감소")]
    prev_reviews = [_review("id-a", DecisionStatus.REJECTED, user_note="근거 부족")]
    new_items = [_item("id-a", "공정 30% 감소")]

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, new_items, similarity_fn=_exact_similarity)

    carried = merged.carried_decisions[0]
    assert carried["decision"] == DecisionStatus.REJECTED
    assert carried["user_note"] == "근거 부족"


def test_edited_text_survives_reanalysis():
    prev_items = [_item("id-a", "레이저로 가공")]
    prev_reviews = [_review("id-a", DecisionStatus.EDITED,
                            edited_text="펨토초 레이저로 개질 후 식각")]
    new_items = [_item("id-a", "레이저로 가공")]

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, new_items, similarity_fn=_exact_similarity)

    assert merged.carried_decisions[0]["edited_text"] == "펨토초 레이저로 개질 후 식각"


def test_carried_decision_records_analysis_version():
    prev_items = [_item("id-a", "본문")]
    prev_reviews = [_review("id-a", DecisionStatus.APPROVED)]

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, [_item("id-a", "본문")],
        similarity_fn=_exact_similarity, analysis_version=2)

    assert merged.carried_decisions[0]["carried_from_analysis_version"] == 2


# ---------------------------------------------------------------------------
# 재분석 — 2등급: 유사하지만 다른 id
# ---------------------------------------------------------------------------


def test_similar_item_does_not_auto_copy_decision():
    """유사도만으로 승인을 옮기면 사용자가 승인한 적 없는 내용이 본문에 들어간다."""
    prev_items = [_item("id-old", "상온에서 섬유를 삽입한다")]
    prev_reviews = [_review("id-old", DecisionStatus.APPROVED)]
    new_items = [_item("id-new", "상온에서 섬유를 삽입하지 않는다")]

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, new_items,
        similarity_fn=_fixed_similarity(0.93), similar_threshold=0.85)

    item = merged.items[0]
    assert item["match_type"] == "similar"
    assert item["carried_over"] is False, "유사하다고 판단을 복사하면 안 된다"
    assert merged.carried_decisions == [], "이어받은 판단이 없어야 한다"


def test_similar_item_links_previous_item_id_for_user_question():
    prev_items = [_item("id-old", "그래핀 섬유를 장력 상태로 관통 배치한다")]
    prev_reviews = [_review("id-old", DecisionStatus.APPROVED)]
    new_items = [_item("id-new", "장력을 유지한 그래핀 섬유를 관통시켜 배치한다")]

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, new_items,
        similarity_fn=_fixed_similarity(0.91), similar_threshold=0.85)

    item = merged.items[0]
    assert item["related_previous_item_id"] == "id-old"
    assert item["similarity_score"] == 0.91
    assert merged.similar_pairs == [("id-new", "id-old", 0.91)]


def test_similar_case_keeps_previous_decision_as_orphaned_not_deleted():
    prev_items = [_item("id-old", "예전 표현")]
    prev_reviews = [_review("id-old", DecisionStatus.APPROVED)]
    new_items = [_item("id-new", "새 표현")]

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, new_items,
        similarity_fn=_fixed_similarity(0.90), similar_threshold=0.85)

    assert [d["item_id"] for d in merged.orphaned_decisions] == ["id-old"]


def test_score_below_threshold_is_treated_as_new():
    prev_items = [_item("id-old", "예전 표현")]
    prev_reviews = [_review("id-old", DecisionStatus.APPROVED)]
    new_items = [_item("id-new", "전혀 다른 내용")]

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, new_items,
        similarity_fn=_fixed_similarity(0.40), similar_threshold=0.85)

    assert merged.items[0]["match_type"] == "new"
    assert merged.items[0].get("related_previous_item_id") is None


# ---------------------------------------------------------------------------
# 재분석 — 3등급: 신규
# ---------------------------------------------------------------------------


def test_brand_new_item_is_unreviewed():
    merged = merge_user_reviews_after_reanalysis(
        [], [], [_item("id-new", "완전히 새로운 제안")],
        similarity_fn=_exact_similarity)

    assert merged.items[0]["match_type"] == "new"
    assert merged.items[0]["carried_over"] is False
    assert merged.carried_decisions == []


def test_unreviewed_previous_decision_is_not_reported_as_orphan():
    prev_items = [_item("id-old", "본문")]
    prev_reviews = [_review("id-old", DecisionStatus.UNREVIEWED)]

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, [_item("id-new", "다른 본문")],
        similarity_fn=_exact_similarity)

    assert merged.orphaned_decisions == []


def test_merge_does_not_mutate_inputs():
    prev_items = [_item("id-a", "본문")]
    prev_reviews = [_review("id-a", DecisionStatus.APPROVED)]
    new_items = [_item("id-a", "본문")]
    snapshot = copy.deepcopy((prev_items, prev_reviews, new_items))

    merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, new_items, similarity_fn=_exact_similarity)

    assert (prev_items, prev_reviews, new_items) == snapshot


def test_mixed_batch_is_classified_into_three_grades():
    prev_items = [_item("id-same", "유지될 항목"), _item("id-old", "예전 표현")]
    prev_reviews = [
        _review("id-same", DecisionStatus.APPROVED),
        _review("id-old", DecisionStatus.REJECTED),
    ]
    new_items = [
        _item("id-same", "유지될 항목"),      # 1등급
        _item("id-new1", "예전 표현과 비슷"),  # 2등급
        _item("id-new2", "완전 신규"),         # 3등급
    ]

    def sim(a: str, b: str) -> float:
        if a == b:
            return 1.0
        return 0.9 if (a == "예전 표현과 비슷" and b == "예전 표현") else 0.1

    merged = merge_user_reviews_after_reanalysis(
        prev_items, prev_reviews, new_items,
        similarity_fn=sim, similar_threshold=0.85)

    by_id = {i["item_id"]: i for i in merged.items}
    assert by_id["id-same"]["match_type"] == "exact"
    assert by_id["id-new1"]["match_type"] == "similar"
    assert by_id["id-new2"]["match_type"] == "new"
    assert [d["item_id"] for d in merged.carried_decisions] == ["id-same"]
    assert [d["item_id"] for d in merged.orphaned_decisions] == ["id-old"]


# ---------------------------------------------------------------------------
# 승인 != 반영 (§27.1)
# ---------------------------------------------------------------------------


def test_approved_item_can_end_up_not_applied():
    """승인해도 중복이면 본문에 들어가지 않는다."""
    doc = load_analysis(None)
    doc.set_items(AnalysisKeys.NEW_ELEMENTS, [
        AnalysisItem(item_id="id-a", text="이미 본문에 있는 내용")])
    doc.set_decision(UserDecision(item_id="id-a", decision=DecisionStatus.APPROVED))

    doc.record_application([ApplicationEntry(
        item_id="id-a", status=ApplicationStatus.SKIPPED_DUPLICATE,
        target_field="core_principle")])

    assert doc.decision_of("id-a").decision == DecisionStatus.APPROVED
    assert doc.application_of("id-a").status == ApplicationStatus.SKIPPED_DUPLICATE


def test_transaction_failure_is_recorded_separately_from_approval():
    doc = load_analysis(None)
    doc.set_items(AnalysisKeys.NEW_ELEMENTS, [AnalysisItem(item_id="id-a")])
    doc.set_decision(UserDecision(item_id="id-a", decision=DecisionStatus.APPROVED))

    doc.record_application([ApplicationEntry(
        item_id="id-a", status=ApplicationStatus.FAILED_TRANSACTION,
        error_message="DB 쓰기 실패")])

    entry = doc.application_of("id-a")
    assert entry.status == ApplicationStatus.FAILED_TRANSACTION
    assert entry.error_message == "DB 쓰기 실패"
    assert doc.decision_of("id-a").decision == DecisionStatus.APPROVED


def test_all_application_statuses_roundtrip():
    doc = load_analysis(None)
    entries = [ApplicationEntry(item_id=f"id-{i}", status=status)
               for i, status in enumerate(ApplicationStatus.ALL)]
    doc.record_application(entries)

    reloaded = load_analysis(doc.to_json())
    assert [e.status for e in reloaded.application_entries()] == list(
        ApplicationStatus.ALL)


def test_not_selected_item_is_distinguishable_from_rejected():
    """사용자가 거절한 것과, 선택하지 않아 반영 대상이 아닌 것은 다르다."""
    doc = load_analysis(None)
    doc.set_items(AnalysisKeys.NEW_ELEMENTS, [
        AnalysisItem(item_id="rejected-1"), AnalysisItem(item_id="untouched-1")])
    doc.set_decision(UserDecision(item_id="rejected-1",
                                  decision=DecisionStatus.REJECTED))
    doc.record_application([
        ApplicationEntry(item_id="rejected-1", status=ApplicationStatus.NOT_SELECTED),
        ApplicationEntry(item_id="untouched-1", status=ApplicationStatus.NOT_SELECTED),
    ])

    assert doc.decision_of("rejected-1").decision == DecisionStatus.REJECTED
    assert doc.decision_of("untouched-1") is None
    assert doc.application_of("untouched-1").status == ApplicationStatus.NOT_SELECTED


# ---------------------------------------------------------------------------
# 판단 기록 자체
# ---------------------------------------------------------------------------


def test_setting_decision_twice_replaces_not_duplicates():
    doc = load_analysis(None)
    doc.set_decision(UserDecision(item_id="id-a", decision=DecisionStatus.APPROVED))
    doc.set_decision(UserDecision(item_id="id-a", decision=DecisionStatus.REJECTED))

    assert len(doc.decisions()) == 1
    assert doc.decision_of("id-a").decision == DecisionStatus.REJECTED


def test_all_decision_statuses_roundtrip():
    doc = load_analysis(None)
    doc.set_decisions([UserDecision(item_id=f"id-{i}", decision=status)
                       for i, status in enumerate(DecisionStatus.ALL)])

    reloaded = load_analysis(doc.to_json())
    assert [d.decision for d in reloaded.decisions()] == list(DecisionStatus.ALL)


def test_pending_items_excludes_reviewed_ones():
    doc = load_analysis(None)
    doc.set_items(AnalysisKeys.NEW_ELEMENTS, [
        AnalysisItem(item_id="id-a"), AnalysisItem(item_id="id-b")])
    doc.set_decision(UserDecision(item_id="id-a", decision=DecisionStatus.APPROVED))

    assert [i.item_id for i in doc.pending_items()] == ["id-b"]


def test_unreviewed_decision_still_counts_as_pending():
    doc = load_analysis(None)
    doc.set_items(AnalysisKeys.NEW_ELEMENTS, [AnalysisItem(item_id="id-a")])
    doc.set_decision(UserDecision(item_id="id-a", decision=DecisionStatus.UNREVIEWED))

    assert [i.item_id for i in doc.pending_items()] == ["id-a"]


def test_orphaned_decisions_survive_roundtrip():
    doc = load_analysis(None)
    doc.set_orphaned_decisions([
        UserDecision(item_id="old-1", decision=DecisionStatus.APPROVED)])

    reloaded = load_analysis(doc.to_json())
    assert [d.item_id for d in reloaded.orphaned_decisions()] == ["old-1"]


def test_user_notes_are_preserved():
    doc = load_analysis(None)
    doc.set_user_notes("이 대화는 실험 실패 뒤에 나눈 것")
    assert load_analysis(doc.to_json()).user_notes() == "이 대화는 실험 실패 뒤에 나눈 것"


def test_analysis_version_increases_and_decisions_survive():
    doc = load_analysis(None)
    doc.set_items(AnalysisKeys.NEW_ELEMENTS, [AnalysisItem(item_id="id-a")])
    doc.set_decision(UserDecision(item_id="id-a", decision=DecisionStatus.APPROVED))
    doc.set_declared_status("id-a", DeclaredStatus.ADOPTED, actor=ACTOR_USER)

    v2 = doc.replace_ai_analysis({
        AnalysisKeys.NEW_ELEMENTS: [AnalysisItem(item_id="id-a").to_json()]})

    assert v2.analysis_version == 2
    assert v2.decision_of("id-a").decision == DecisionStatus.APPROVED


def test_item_id_is_stable_for_identical_text():
    """병합 규칙 전체가 이 성질 위에 서 있다."""
    a = build_item_id("added", "core_principle", "그래핀 섬유를 관통 배치")
    b = build_item_id("added", "core_principle", "그래핀 섬유를 관통 배치")
    assert a == b
