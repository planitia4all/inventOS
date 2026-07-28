"""원문/메시지 해시, item_id, 중복 판정, 원문 위치 찾기 검증.

설계 문서 §6.4(전체 해시), §6.5(메시지 중복/재복사), §12(Source Trace),
§27.2(item_id 정규화와 동의어 사전 remap).

전부 순수 함수라 DB·AI 없이 계약을 고정할 수 있다.
"""
from __future__ import annotations

import copy
import time

import pytest

from src.conversations.constants import MIN_OVERLAP_MESSAGES
from src.conversations.hashing import (
    EXACT_DUPLICATE,
    NEW,
    PARTIAL_OVERLAP,
    SUPERSET,
    build_item_id,
    classify_overlap,
    hash_message,
    hash_raw_content,
    locate_excerpt,
    normalize_item_text,
    normalize_raw_content,
    remap_item_ids,
    strip_ui_noise,
)


def _item(item_id: str, text: str, change_type: str = "added",
          target_field: str = "core_principle") -> dict:
    return {
        "item_id": item_id,
        "change_type": change_type,
        "target_field": target_field,
        "text": text,
    }


def _review(item_id: str, decision: str, **kw) -> dict:
    base = {"item_id": item_id, "decision": decision, "edited_text": None}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# 원문 정규화 / 전체 해시 (§6.4)
# ---------------------------------------------------------------------------


def test_newline_differences_produce_same_hash():
    assert hash_raw_content("가\r\n나\r다") == hash_raw_content("가\n나\n다")


def test_whitespace_differences_produce_same_hash():
    assert hash_raw_content("가   나") == hash_raw_content("가 나")
    assert hash_raw_content("  가 나  ") == hash_raw_content("가 나")


def test_trailing_blank_lines_produce_same_hash():
    assert hash_raw_content("가\n\n\n\n나") == hash_raw_content("가\n\n나")


def test_bom_is_ignored_in_hash():
    assert hash_raw_content("﻿대화 내용") == hash_raw_content("대화 내용")


def test_ui_noise_only_difference_produces_same_hash():
    with_noise = "You said:\n유리에 홀을 뚫는 방법\nChatGPT said:\n레이저를 씁니다\nCopy code"
    without = "유리에 홀을 뚫는 방법\n레이저를 씁니다"
    assert hash_raw_content(with_noise) == hash_raw_content(without)


def test_different_content_produces_different_hash():
    assert hash_raw_content("레이저 가공") != hash_raw_content("그래핀 섬유")


def test_empty_input_is_handled():
    assert normalize_raw_content("") == ""
    assert strip_ui_noise("") == ""
    assert hash_raw_content("") == hash_raw_content("   \n\n  ")


def test_normalize_raw_content_does_not_strip_ui_noise():
    """두 정규화는 수명이 달라 분리해 두었다 (§8)."""
    assert "Copy code" in normalize_raw_content("본문\nCopy code")


# ---------------------------------------------------------------------------
# 메시지 해시 (§6.5)
# ---------------------------------------------------------------------------


def test_message_hash_includes_role():
    """같은 문장이라도 사용자 발언과 AI 발언은 다른 메시지다."""
    assert hash_message("user", "그래핀을 씁시다") != hash_message("assistant", "그래핀을 씁시다")


def test_message_hash_ignores_whitespace_and_case_of_role():
    assert hash_message("USER", "본문") == hash_message(" user ", "본문")


def test_message_hash_ignores_whitespace_differences():
    assert hash_message("user", "가   나") == hash_message("user", "가 나")


# ---------------------------------------------------------------------------
# item_id 정규화 (§27.2.1)
# ---------------------------------------------------------------------------


def test_item_id_is_deterministic():
    a = build_item_id("added", "core_principle", "그래핀 섬유")
    b = build_item_id("added", "core_principle", "그래핀 섬유")
    assert a == b and len(a) == 16


def test_item_id_changes_with_change_type_and_field():
    text = "그래핀 섬유"
    assert (build_item_id("added", "core_principle", text)
            != build_item_id("modified", "core_principle", text))
    assert (build_item_id("added", "core_principle", text)
            != build_item_id("added", "operating_principle", text))


def test_whitespace_and_punctuation_do_not_change_item_id():
    a = build_item_id("added", "f", "- 그래핀 섬유를 관통 배치한다.")
    b = build_item_id("added", "f", "그래핀  섬유를\n관통 배치한다")
    assert a == b


def test_case_and_fullwidth_do_not_change_item_id():
    assert (build_item_id("added", "f", "Graphene Fiber")
            == build_item_id("added", "f", "ｇｒａｐｈｅｎｅ ｆｉｂｅｒ"))


def test_list_markers_are_removed():
    for marker in ("- ", "• ", "1. ", "1) ", "가. "):
        assert (build_item_id("added", "f", f"{marker}그래핀 섬유")
                == build_item_id("added", "f", "그래핀 섬유"))


def test_builtin_abbreviation_maps_variants_to_canonical():
    canonical = normalize_item_text("TGV 홀 가공")
    for variant in ("Through Glass Via 홀 가공", "유리 관통 비아 홀 가공",
                    "글라스 비아 홀 가공"):
        assert normalize_item_text(variant) == canonical


def test_filler_words_are_removed():
    assert (build_item_id("added", "f", "결국 그래핀 섬유")
            == build_item_id("added", "f", "그래핀 섬유"))


def test_repeated_words_are_collapsed():
    assert (build_item_id("added", "f", "그래핀 그래핀 섬유")
            == build_item_id("added", "f", "그래핀 섬유"))


def test_user_synonyms_change_normalized_text():
    synonyms = {"그래핀 섬유": ("그래핀 실", "graphene fiber")}
    assert (normalize_item_text("그래핀 실을 사용", synonyms)
            == normalize_item_text("그래핀 섬유를 사용", synonyms))


def test_item_id_differs_before_and_after_applying_synonyms():
    """동의어 사전을 적용하면 id가 바뀐다 — 그래서 remap이 필요하다 (§27.2.2)."""
    synonyms = {"그래핀 섬유": ("그래핀 실",)}
    before = build_item_id("added", "f", "그래핀 실을 사용", None, 0)
    after = build_item_id("added", "f", "그래핀 실을 사용", synonyms, 1)
    assert before != after


def test_synonym_dict_version_is_not_part_of_the_hash():
    """버전을 해시에 넣으면 내용이 그대로인 항목까지 id가 바뀐다."""
    a = build_item_id("added", "f", "레이저 가공", None, 0)
    b = build_item_id("added", "f", "레이저 가공", None, 7)
    assert a == b


def test_empty_text_is_handled():
    assert normalize_item_text("") == ""
    assert len(build_item_id("added", "f", "")) == 16


def test_korean_and_english_mixed_text():
    a = build_item_id("added", "f", "Graphene 섬유를 사용")
    b = build_item_id("added", "f", "graphene 섬유를 사용")
    assert a == b


# ---------------------------------------------------------------------------
# 동의어 사전 변경 remap (§27.2.2)
# ---------------------------------------------------------------------------


def test_remap_carries_decision_to_new_item_id():
    new_syn = {"그래핀 섬유": ("그래핀 실",)}
    items = [_item(build_item_id("added", "core_principle", "그래핀 실을 사용"),
                   "그래핀 실을 사용")]
    reviews = [_review(items[0]["item_id"], "approved")]

    result = remap_item_ids(items, reviews, None, new_syn, 0, 1)

    old_id = items[0]["item_id"]
    new_id = result.mapping[old_id]
    assert new_id != old_id
    assert len(result.migrated_reviews) == 1
    assert result.migrated_reviews[0]["item_id"] == new_id
    assert result.migrated_reviews[0]["original_item_id"] == old_id
    assert result.conflicts == []


def test_remap_reports_merged_group_when_two_items_collapse():
    """동의어 병합으로 두 항목이 같은 id가 되는 경우."""
    new_syn = {"그래핀 섬유": ("그래핀 실",)}
    a = _item(build_item_id("added", "f", "그래핀 실"), "그래핀 실")
    b = _item(build_item_id("added", "f", "그래핀 섬유"), "그래핀 섬유")

    result = remap_item_ids([a, b], [], None, new_syn, 0, 1)

    merged_id = result.mapping[a["item_id"]]
    assert result.mapping[b["item_id"]] == merged_id
    assert sorted(result.merged_groups[merged_id]) == sorted(
        [a["item_id"], b["item_id"]])


def test_remap_merges_agreeing_decisions_without_conflict():
    new_syn = {"그래핀 섬유": ("그래핀 실",)}
    a = _item(build_item_id("added", "f", "그래핀 실"), "그래핀 실")
    b = _item(build_item_id("added", "f", "그래핀 섬유"), "그래핀 섬유")
    reviews = [_review(a["item_id"], "approved"), _review(b["item_id"], "approved")]

    result = remap_item_ids([a, b], reviews, None, new_syn, 0, 1)

    assert result.conflicts == []
    assert len(result.migrated_reviews) == 1


def test_remap_reports_conflict_when_merged_decisions_disagree():
    """서로 다른 판단이 하나로 합쳐지면 임의로 고르지 않는다."""
    new_syn = {"그래핀 섬유": ("그래핀 실",)}
    a = _item(build_item_id("added", "f", "그래핀 실"), "그래핀 실")
    b = _item(build_item_id("added", "f", "그래핀 섬유"), "그래핀 섬유")
    reviews = [_review(a["item_id"], "approved"), _review(b["item_id"], "rejected")]

    result = remap_item_ids([a, b], reviews, None, new_syn, 0, 1)

    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert sorted(conflict.old_item_ids) == sorted([a["item_id"], b["item_id"]])
    assert {d["decision"] for d in conflict.decisions} == {"approved", "rejected"}
    assert result.migrated_reviews == [], "충돌 시에는 아무것도 자동 이관하지 않는다"


def test_remap_keeps_unmatched_decision_as_orphan():
    items = [_item("id-a", "본문 A")]
    reviews = [_review("id-a", "approved"), _review("사라진-항목", "rejected")]

    result = remap_item_ids(items, reviews, None, None, 0, 1)

    assert [r["item_id"] for r in result.orphaned_reviews] == ["사라진-항목"]


def test_remap_ignores_unreviewed_decisions():
    items = [_item("id-a", "본문 A")]
    reviews = [_review("id-a", "unreviewed")]

    result = remap_item_ids(items, reviews, None, None, 0, 1)

    assert result.migrated_reviews == []
    assert result.conflicts == []


def test_remap_does_not_mutate_inputs():
    items = [_item("id-a", "본문")]
    reviews = [_review("id-a", "approved")]
    snapshot = copy.deepcopy((items, reviews))

    remap_item_ids(items, reviews, None, {"x": ("본문",)}, 0, 1)

    assert (items, reviews) == snapshot


# ---------------------------------------------------------------------------
# 메시지 중복 / superset (§6.5)
# ---------------------------------------------------------------------------


def test_exact_duplicate_is_detected():
    report = classify_overlap(["A", "B", "C"], ["A", "B", "C"])
    assert report.match_type == EXACT_DUPLICATE


def test_superset_is_detected_and_new_range_extracted():
    """가장 흔한 패턴: 같은 대화창에서 이어서 복사."""
    report = classify_overlap(["A", "B", "C"], ["A", "B", "C", "D", "E"])

    assert report.match_type == SUPERSET
    assert report.already_imported_indices == [0, 1, 2]
    assert report.newly_added_indices == [3, 4]
    assert report.analyzed_range == [3, 4]


def test_superset_detected_even_with_leading_ui_header():
    """앞에 UI 머리말이 한 줄 붙어도 이어진 대화로 인정한다."""
    report = classify_overlap(["A", "B", "C"], ["X", "A", "B", "C", "D"])

    assert report.match_type == SUPERSET
    assert report.already_imported_indices == [1, 2, 3]
    assert report.newly_added_indices == [0, 4]


def test_partial_overlap_when_order_does_not_match():
    report = classify_overlap(["A", "B", "C"], ["A", "B", "X", "C", "D"])
    assert report.match_type == PARTIAL_OVERLAP
    assert report.overlap_count == 3


def test_unrelated_conversation_is_new():
    report = classify_overlap(["A", "B", "C"], ["X", "Y", "Z"])
    assert report.match_type == NEW
    assert report.newly_added_indices == [0, 1, 2]
    assert report.already_imported_indices == []


def test_small_accidental_overlap_is_treated_as_new():
    """두 대화가 모두 '안녕하세요'로 시작한다고 이어진 대화는 아니다."""
    report = classify_overlap(["GREET", "A", "B"], ["GREET", "X", "Y"],
                              min_overlap=MIN_OVERLAP_MESSAGES)
    assert report.match_type == NEW
    assert report.newly_added_indices == [0, 1, 2]


def test_min_overlap_threshold_is_adjustable():
    report = classify_overlap(["A", "B"], ["A", "B", "C"], min_overlap=2)
    assert report.match_type == SUPERSET


def test_empty_sequences_are_handled():
    assert classify_overlap([], []).match_type == NEW
    assert classify_overlap([], ["A"]).match_type == NEW
    assert classify_overlap(["A"], []).newly_added_indices == []


def test_first_import_with_no_history_is_new():
    report = classify_overlap([], ["A", "B", "C", "D"])
    assert report.match_type == NEW
    assert report.newly_added_indices == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# 원문 위치 찾기 (§12.1.1)
# ---------------------------------------------------------------------------


def test_exact_match_returns_offsets():
    raw = "앞부분입니다. 그래핀 섬유를 씁니다. 뒷부분입니다."
    loc = locate_excerpt(raw, "그래핀 섬유를 씁니다")

    assert loc.matched is True
    assert raw[loc.source_start:loc.source_end] == "그래핀 섬유를 씁니다"
    assert loc.ambiguous is False


def test_no_match_returns_minus_one_without_altering_content():
    loc = locate_excerpt("원문입니다", "존재하지 않는 문장")
    assert loc.matched is False
    assert (loc.source_start, loc.source_end) == (-1, -1)


def test_repeated_sentence_is_flagged_as_ambiguous():
    raw = "같은 문장. 다른 내용. 같은 문장."
    loc = locate_excerpt(raw, "같은 문장")

    assert loc.matched is True
    assert loc.ambiguous is True
    assert loc.occurrences == 2
    assert loc.source_start == 0, "첫 위치를 쓴다"


def test_search_from_prefers_later_occurrence():
    raw = "반복. 중간. 반복."
    first = locate_excerpt(raw, "반복")
    later = locate_excerpt(raw, "반복", search_from=first.source_end)
    assert later.source_start > first.source_start


def test_search_from_falls_back_to_full_scan():
    raw = "반복 문장이 앞에만 있다"
    loc = locate_excerpt(raw, "반복", search_from=100)
    assert loc.matched is True
    assert loc.source_start == 0


def test_offsets_are_python_codepoint_based_for_korean():
    raw = "한글은 한 글자가 1이다"
    loc = locate_excerpt(raw, "한 글자")
    assert raw[loc.source_start:loc.source_end] == "한 글자"


def test_offsets_work_with_emoji():
    raw = "실험 결과 🔬 매우 좋았다 🎉 끝"
    loc = locate_excerpt(raw, "매우 좋았다")
    assert raw[loc.source_start:loc.source_end] == "매우 좋았다"


def test_emoji_itself_can_be_located():
    raw = "결과 🎉 좋음"
    loc = locate_excerpt(raw, "🎉")
    assert loc.matched is True
    assert raw[loc.source_start:loc.source_end] == "🎉"


def test_empty_inputs_return_unmatched():
    assert locate_excerpt("", "무엇이든").matched is False
    assert locate_excerpt("원문", "").matched is False


# ---------------------------------------------------------------------------
# 대용량 입력 안전성
# ---------------------------------------------------------------------------


def test_large_input_is_handled_within_reasonable_time():
    """30만 자 원문을 정규화·해시할 때 실용적인 시간 안에 끝나야 한다."""
    big = ("유리 기판에 홀을 뚫는 방법을 논의합니다.\n" * 12_000)[:300_000]

    start = time.monotonic()
    digest = hash_raw_content(big)
    elapsed = time.monotonic() - start

    assert len(digest) == 64
    assert elapsed < 5.0, f"30만 자 해시가 너무 느림: {elapsed:.2f}초"


def test_large_item_text_normalization_is_safe():
    big = "그래핀 섬유를 장력 상태로 관통 배치한다. " * 5_000

    start = time.monotonic()
    item_id = build_item_id("added", "core_principle", big)
    elapsed = time.monotonic() - start

    assert len(item_id) == 16
    assert elapsed < 5.0, f"대용량 item_id 계산이 너무 느림: {elapsed:.2f}초"


def test_large_overlap_comparison_is_safe():
    existing = [f"h{i}" for i in range(2_000)]
    new = existing + [f"n{i}" for i in range(500)]

    start = time.monotonic()
    report = classify_overlap(existing, new)
    elapsed = time.monotonic() - start

    assert report.match_type == SUPERSET
    assert len(report.newly_added_indices) == 500
    assert elapsed < 5.0, f"대용량 겹침 판정이 너무 느림: {elapsed:.2f}초"


@pytest.mark.parametrize("bad_input", [None, "", "   "])
def test_hash_functions_tolerate_blank_input(bad_input):
    assert len(hash_raw_content(bad_input or "")) == 64
    assert len(hash_message("user", bad_input or "")) == 64
