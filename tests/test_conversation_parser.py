"""Clipboard Parser — 붙여넣은 대화를 메시지로 자르기 (2-1).

여기서 고정하는 계약은 넷이다.

1. 원문 offset이 실제로 맞는다 (`raw[start:end] == text`)
2. 화자 마커가 있으면 정확히 구분한다
3. 마커가 없어도 포기하지 않는다 — 다만 추정했다고 말한다
4. 어떤 입력에도 예외를 던지지 않는다
"""
from __future__ import annotations

import pytest

from src.conversations.hashing import classify_overlap, hash_message
from src.conversations.parser import (
    ROLE_ASSISTANT,
    ROLE_UNKNOWN,
    ROLE_USER,
    SOURCE_CHATGPT,
    SOURCE_CLAUDE,
    SOURCE_OTHER,
    SPLIT_HEURISTIC,
    SPLIT_MARKER,
    SPLIT_SINGLE,
    parse_conversation,
)

CHATGPT_PASTE = """You said:
그래핀 섬유를 유리 기판에 관통시키는 방법이 있을까요?

ChatGPT said:
몇 가지 접근이 있습니다. 첫째, 레이저로 미세 구멍을 뚫은 뒤 섬유를 삽입합니다.
둘째, 유리 성형 단계에서 함께 인서트하는 방법도 있습니다.

You said:
상온에서 삽입하는 건 어떤가요?

ChatGPT said:
상온 삽입은 열응력을 피할 수 있어 유리합니다.
"""

CLAUDE_PASTE = """나: 유리 기판 관통 전극에 그래핀 섬유를 쓰면 어떤 장점이 있나요?

Claude: 전기 전도도가 높고 열팽창 계수가 유리와 가까워 균열 위험이 줄어듭니다.

나: 단점은요?

Claude: 섬유와 구멍 사이 밀착도 확보가 어렵습니다.
"""

NO_MARKER_PASTE = """그래핀 섬유를 유리에 관통시킬 수 있을까요?

가능합니다. 다만 열팽창 계수 차이 때문에 냉각 과정에서 균열이 생길 수 있습니다.
이를 피하려면 상온 삽입이나 단계적 냉각을 고려해야 합니다. 실제 공정에서는
레이저 드릴링 후 섬유를 밀어 넣는 방식이 가장 널리 쓰입니다.

상온 삽입은 어때요?

상온 삽입은 열응력을 원천적으로 피할 수 있어 유리합니다. 다만 구멍과 섬유
사이의 밀착도가 떨어질 수 있어 별도의 접합재가 필요합니다.
"""


def _assert_offsets_are_exact(raw: str, parsed) -> None:
    for message in parsed.messages:
        assert raw[message.source_start : message.source_end] == message.text


# ---------------------------------------------------------------------------
# 1) 화자 마커
# ---------------------------------------------------------------------------


def test_chatgpt_paste_is_split_by_markers():
    parsed = parse_conversation(CHATGPT_PASTE)

    assert parsed.split_method == SPLIT_MARKER
    assert parsed.message_count == 4
    assert [m.role for m in parsed.messages] == [
        ROLE_USER,
        ROLE_ASSISTANT,
        ROLE_USER,
        ROLE_ASSISTANT,
    ]


def test_chatgpt_source_is_detected():
    assert parse_conversation(CHATGPT_PASTE).source_type == SOURCE_CHATGPT


def test_claude_source_is_detected():
    assert parse_conversation(CLAUDE_PASTE).source_type == SOURCE_CLAUDE


def test_korean_markers_are_recognized():
    parsed = parse_conversation(CLAUDE_PASTE)

    assert parsed.split_method == SPLIT_MARKER
    assert [m.role for m in parsed.messages] == [
        ROLE_USER,
        ROLE_ASSISTANT,
        ROLE_USER,
        ROLE_ASSISTANT,
    ]


def test_marker_text_is_not_part_of_the_message():
    """`You said:`는 화자 표시지 사용자가 한 말이 아니다."""
    parsed = parse_conversation(CHATGPT_PASTE)

    for message in parsed.messages:
        assert "said:" not in message.text.lower()
    assert parsed.messages[0].text.startswith("그래핀 섬유를")


def test_marker_split_reports_speakers_as_detected():
    parsed = parse_conversation(CHATGPT_PASTE)

    assert parsed.speakers_detected is True
    assert parsed.warnings == []


def test_marker_without_colon_on_its_own_line_is_recognized():
    raw = "You said\n첫 질문입니다\n\nChatGPT said\n첫 답변입니다\n"

    parsed = parse_conversation(raw)

    assert parsed.split_method == SPLIT_MARKER
    assert parsed.messages[0].text == "첫 질문입니다"


def test_marker_word_inside_a_sentence_is_not_a_marker():
    """본문 한가운데의 'claude'까지 화자 표시로 잡으면 대화가 조각난다."""
    raw = (
        "You said:\n"
        "제가 claude에게 물어본 내용인데요, 이 방식이 맞나요?\n"
        "\n"
        "ChatGPT said:\n"
        "네, 접근 방식은 타당합니다.\n"
    )

    parsed = parse_conversation(raw)

    assert parsed.message_count == 2
    assert "claude에게 물어본" in parsed.messages[0].text


def test_single_marker_is_not_enough_to_split():
    """마커가 하나뿐이면 대화가 아니라 그냥 본문일 가능성이 높다."""
    raw = "ChatGPT said:\n" + "긴 답변 본문입니다. " * 20

    assert parse_conversation(raw).split_method != SPLIT_MARKER


def test_markers_with_no_content_fall_through():
    """화자 표시만 복사된 경우 — 마커 분리를 성공으로 치면 빈 대화가 된다."""
    raw = "You said:\n\nChatGPT said:\n\nYou said:\n"

    parsed = parse_conversation(raw)

    assert parsed.split_method != SPLIT_MARKER


# ---------------------------------------------------------------------------
# 2) 휴리스틱
# ---------------------------------------------------------------------------


def test_paste_without_markers_falls_back_to_blocks():
    parsed = parse_conversation(NO_MARKER_PASTE)

    assert parsed.split_method == SPLIT_HEURISTIC
    assert parsed.message_count == 4


def test_heuristic_guesses_short_questions_as_user():
    parsed = parse_conversation(NO_MARKER_PASTE)

    assert [m.role for m in parsed.messages] == [
        ROLE_USER,
        ROLE_ASSISTANT,
        ROLE_USER,
        ROLE_ASSISTANT,
    ]


def test_heuristic_does_not_claim_speakers_are_known():
    """추정을 확신처럼 다루면 AI 발언이 사용자 발언으로 둔갑한다 (§9.5)."""
    parsed = parse_conversation(NO_MARKER_PASTE)

    assert parsed.speakers_detected is False
    assert parsed.warnings
    assert "정확하지 않을 수 있습니다" in parsed.warnings[0]


def test_adjacent_blocks_of_the_same_speaker_are_merged():
    """한 턴이 여러 문단일 수 있다 — 문단마다 메시지를 만들면 턴 수가 뻥튄다."""
    raw = (
        "이 방법이 가능할까요?\n\n"
        + "가능합니다. 첫 번째 이유는 열팽창 계수가 비슷하기 때문입니다. " * 3
        + "\n\n"
        + "두 번째 이유는 전기 전도도가 충분히 높기 때문입니다. " * 3
    )

    parsed = parse_conversation(raw)

    assert parsed.message_count == 2
    assert parsed.messages[1].role == ROLE_ASSISTANT
    assert "첫 번째 이유" in parsed.messages[1].text
    assert "두 번째 이유" in parsed.messages[1].text


def test_question_without_question_mark_is_still_a_question():
    """한국어는 물음표 없이도 질문이 된다."""
    raw = (
        "상온 삽입이 가능한지 궁금한데요\n\n"
        + "가능합니다. 열응력을 피할 수 있다는 점에서 유리한 접근입니다. " * 5
    )

    parsed = parse_conversation(raw)

    assert parsed.messages[0].role == ROLE_USER


def test_all_blocks_guessed_as_one_speaker_falls_through():
    """전부 같은 화자로 추정됐다면 추정에 실패한 것과 다르지 않다."""
    raw = "\n\n".join(["똑같은 길이의 평서문 문단입니다. " * 5] * 4)

    assert parse_conversation(raw).split_method == SPLIT_SINGLE


# ---------------------------------------------------------------------------
# 3) 분리 포기
# ---------------------------------------------------------------------------


def test_single_block_becomes_one_unknown_message():
    raw = "그래핀 섬유 관통 배치에 대한 메모. 구조가 전혀 없는 한 덩어리 텍스트."

    parsed = parse_conversation(raw)

    assert parsed.split_method == SPLIT_SINGLE
    assert parsed.message_count == 1
    assert parsed.messages[0].role == ROLE_UNKNOWN


def test_giving_up_still_keeps_order_and_offsets():
    """순번만 있어도 Timeline은 만들어진다 — 빈손으로 돌려주지 않는다."""
    raw = "  구조가 없는 한 덩어리 원문입니다.  \n"

    parsed = parse_conversation(raw)

    assert parsed.messages[0].index == 0
    _assert_offsets_are_exact(raw, parsed)


def test_giving_up_warns_the_user():
    parsed = parse_conversation("구조가 없는 한 덩어리 원문입니다.")

    assert parsed.speakers_detected is False
    assert "화자를 구분하지 못했습니다" in parsed.warnings[0]


# ---------------------------------------------------------------------------
# Offset (§12)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw", [CHATGPT_PASTE, CLAUDE_PASTE, NO_MARKER_PASTE], ids=["chatgpt", "claude", "plain"]
)
def test_offsets_point_at_the_original_text(raw):
    _assert_offsets_are_exact(raw, parse_conversation(raw))


def test_offsets_survive_emoji_and_korean():
    """offset은 바이트가 아니라 Python 코드포인트 기준이어야 한다."""
    raw = "You said:\n🔬 그래핀 섬유 실험 결과는요?\n\nChatGPT said:\n✨ 성공했습니다.\n"

    parsed = parse_conversation(raw)

    _assert_offsets_are_exact(raw, parsed)
    assert parsed.messages[0].text.startswith("🔬")


def test_offsets_exclude_surrounding_blank_lines():
    raw = "You said:\n\n\n   첫 질문   \n\n\nChatGPT said:\n\n   첫 답변   \n\n"

    parsed = parse_conversation(raw)

    assert parsed.messages[0].text == "첫 질문"
    _assert_offsets_are_exact(raw, parsed)


def test_indices_are_contiguous_from_zero():
    parsed = parse_conversation(CHATGPT_PASTE)

    assert [m.index for m in parsed.messages] == list(range(parsed.message_count))


# ---------------------------------------------------------------------------
# 해시 — 2-2 Overlap Detector가 쓸 입력
# ---------------------------------------------------------------------------


def test_content_hash_matches_hash_message():
    parsed = parse_conversation(CHATGPT_PASTE)
    first = parsed.messages[0]

    assert first.content_hash == hash_message(first.role, first.text)


def test_same_message_from_different_speakers_hashes_differently():
    """같은 문장이라도 사용자가 한 말과 AI가 한 말은 다르다 (§9.5)."""
    raw = "You said:\n상온에서 삽입한다\n\nChatGPT said:\n상온에서 삽입한다\n"

    parsed = parse_conversation(raw)

    assert parsed.messages[0].text == parsed.messages[1].text
    assert parsed.messages[0].content_hash != parsed.messages[1].content_hash


def test_ui_noise_difference_does_not_change_the_hash():
    """복사할 때 딸려온 버튼 문구 때문에 같은 대화가 다르게 잡히면 안 된다."""
    clean = parse_conversation(CHATGPT_PASTE)
    noisy = parse_conversation(CHATGPT_PASTE.replace("ChatGPT said:", "Copy code\nChatGPT said:"))

    assert clean.hashes() == noisy.hashes()


def test_repasted_conversation_is_detected_as_superset():
    """1차에서 2문답, 2차에서 4문답을 붙여넣은 경우 (§6.5)."""
    first = parse_conversation(
        "You said:\n첫 질문입니다\n\nChatGPT said:\n첫 답변입니다\n"
        "\nYou said:\n두 번째 질문입니다\n\nChatGPT said:\n두 번째 답변입니다\n"
    )
    second = parse_conversation(
        "You said:\n첫 질문입니다\n\nChatGPT said:\n첫 답변입니다\n"
        "\nYou said:\n두 번째 질문입니다\n\nChatGPT said:\n두 번째 답변입니다\n"
        "\nYou said:\n세 번째 질문입니다\n\nChatGPT said:\n세 번째 답변입니다\n"
    )

    # 인자 순서에 주의: (기존, 새로 붙여넣은 것) 순이다.
    report = classify_overlap(first.hashes(), second.hashes())

    assert report.match_type == "superset"
    assert report.already_imported_indices == [0, 1, 2, 3]
    assert report.newly_added_indices == [4, 5]
    assert report.analyzed_range == [4, 5]


# ---------------------------------------------------------------------------
# analysis_json 계약과의 접점
# ---------------------------------------------------------------------------


def test_message_refs_match_the_schema_contract():
    parsed = parse_conversation(CHATGPT_PASTE)

    refs = parsed.to_message_refs()

    assert len(refs) == parsed.message_count
    first = refs[0]
    assert first.message_index == 0
    assert first.role == ROLE_USER
    assert first.content_hash == parsed.messages[0].content_hash
    assert first.source_start == parsed.messages[0].source_start
    assert first.source_excerpt


def test_message_refs_round_trip_through_the_document(db_session):
    from src.conversations.analysis_schema import load_analysis

    parsed = parse_conversation(CHATGPT_PASTE)
    document = load_analysis(None)
    document.set_messages(parsed.to_message_refs())

    restored = load_analysis(document.to_json())

    assert [m.content_hash for m in restored.messages()] == parsed.hashes()
    assert [m.role for m in restored.messages()] == [m.role for m in parsed.messages]


def test_excerpt_is_capped_and_flattened():
    from src.conversations.constants import SOURCE_EXCERPT_MAX_CHARS

    raw = "You said:\n" + "아주 긴 질문입니다.\n" * 200 + "\nChatGPT said:\n짧은 답변\n"

    parsed = parse_conversation(raw)

    excerpt = parsed.messages[0].excerpt
    assert len(excerpt) <= SOURCE_EXCERPT_MAX_CHARS
    assert "\n" not in excerpt


def test_role_counts_are_reported():
    counts = parse_conversation(CHATGPT_PASTE).role_counts()

    assert counts[ROLE_USER] == 2
    assert counts[ROLE_ASSISTANT] == 2
    assert counts[ROLE_UNKNOWN] == 0


# ---------------------------------------------------------------------------
# 이상한 입력에도 죽지 않는다
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "\n\n\n", "\r\n\r\n", ":", "You said:", "\t"],
    ids=["empty", "spaces", "newlines", "crlf", "colon", "marker-only", "tab"],
)
def test_degenerate_input_does_not_raise(raw):
    parsed = parse_conversation(raw)

    assert parsed.message_count >= 0
    _assert_offsets_are_exact(raw, parsed)


def test_empty_input_yields_no_messages():
    assert parse_conversation("").messages == []
    assert parse_conversation("   \n  ").messages == []


def test_crlf_paste_is_handled():
    raw = "You said:\r\n첫 질문입니다\r\n\r\nChatGPT said:\r\n첫 답변입니다\r\n"

    parsed = parse_conversation(raw)

    assert parsed.message_count == 2
    _assert_offsets_are_exact(raw, parsed)


def test_very_large_paste_is_parsed_in_reasonable_time():
    raw = ("You said:\n질문 {i}입니다\n\nChatGPT said:\n답변 {i}입니다\n" * 2_000)

    parsed = parse_conversation(raw)

    assert parsed.message_count == 4_000
    assert parsed.split_method == SPLIT_MARKER


def test_unknown_source_falls_back_to_other():
    raw = "User: 첫 질문입니다\n\nAssistant: 첫 답변입니다\n"

    assert parse_conversation(raw).source_type == SOURCE_OTHER
