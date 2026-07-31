"""붙여넣은 대화를 메시지 단위로 자른다 (2-1 Clipboard Parser).

AI를 부르지 않는 **순수 함수**다. 하는 일은 하나뿐이다: 사용자가
붙여넣은 평문 한 덩어리를 `(순번, 화자, 본문, 원문 위치)`의 목록으로
바꾼다.

왜 이게 먼저인가
----------------
- 재복사 판정(§6.5)은 메시지 단위 해시가 있어야 가능하다
- 출처 추적(§12)은 "몇 번째 메시지의 몇 번째 글자"가 있어야 가능하다
- 사용자/AI 구분(§9.5)이 없으면 "AI만 제안하고 사용자는 반응하지 않은
  내용"을 걸러낼 수 없다

세 가지 규칙 (§18.4)
--------------------
1. **원문을 바꾸지 않는다.** offset으로 가리키기만 한다.
2. **화자 분리에 실패해도 포기하지 않는다.** 순서(index)만 알아도
   Timeline은 만들어진다.
3. **추측했으면 추측했다고 말한다.** `speakers_detected`가 False면
   사용자 강조도(§11) 계산을 신뢰하면 안 된다.

설계 문서: `docs/conversation-engine-design.md` §6.5, §12, §18.3, §18.4
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from src.conversations.analysis_schema import MessageRef
from src.conversations.constants import SOURCE_EXCERPT_MAX_CHARS
from src.conversations.hashing import hash_message

# ---------------------------------------------------------------------------
# 값
# ---------------------------------------------------------------------------

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_UNKNOWN = "unknown"

# 어떤 방법으로 잘랐는지. 정확도가 이 순서대로 떨어진다 (§18.4).
SPLIT_MARKER = "marker"        # 1) 알려진 화자 마커
SPLIT_HEURISTIC = "heuristic"  # 2) 빈 줄 + 길이·문체 휴리스틱
SPLIT_SINGLE = "single"        # 3) 분리 포기, 전체를 한 흐름으로

SOURCE_CHATGPT = "chatgpt"
SOURCE_CLAUDE = "claude"
SOURCE_OTHER = "other"

# ---------------------------------------------------------------------------
# 화자 마커
# ---------------------------------------------------------------------------

# (역할, 출처, 정규식 조각). **긴 것을 먼저** 둔다 — "chatgpt said"가
# "chatgpt"보다 뒤에 오면 "said:"가 본문으로 남는다.
_MARKER_SPECS: tuple[tuple[str, str, str], ...] = (
    (ROLE_USER, SOURCE_CHATGPT, r"you\s+said"),
    (ROLE_ASSISTANT, SOURCE_CHATGPT, r"chatgpt\s+said"),
    (ROLE_ASSISTANT, SOURCE_CLAUDE, r"claude\s+said"),
    (ROLE_ASSISTANT, SOURCE_OTHER, r"assistant\s+said"),
    (ROLE_ASSISTANT, SOURCE_CHATGPT, r"chatgpt"),
    (ROLE_ASSISTANT, SOURCE_CLAUDE, r"claude"),
    (ROLE_ASSISTANT, SOURCE_OTHER, r"assistant"),
    (ROLE_ASSISTANT, SOURCE_OTHER, r"어시스턴트"),
    (ROLE_ASSISTANT, SOURCE_OTHER, r"답변"),
    (ROLE_ASSISTANT, SOURCE_OTHER, r"ai"),
    (ROLE_USER, SOURCE_OTHER, r"user"),
    (ROLE_USER, SOURCE_OTHER, r"human"),
    (ROLE_USER, SOURCE_OTHER, r"사용자"),
    (ROLE_USER, SOURCE_OTHER, r"질문"),
    (ROLE_USER, SOURCE_OTHER, r"나"),
)

# 마커 줄은 "마커 + 콜론" 이거나 "마커만 한 줄"이어야 한다. 이 조건이
# 없으면 본문 안의 "claude가 알려준 방법"까지 마커로 잡힌다.
_MARKER_RE = re.compile(
    r"^[ \t]*(?:"
    + "|".join(f"(?P<g{i}>{pattern})" for i, (_, _, pattern) in enumerate(_MARKER_SPECS))
    + r")[ \t]*(?:[:：][ \t]*|(?=\n)|$)",
    re.IGNORECASE | re.MULTILINE,
)

# 문단 경계 = 빈 줄 2개 이상 (휴리스틱 분리에서 사용).
_BLOCK_SPLIT_RE = re.compile(r"\n[ \t]*\n\s*")

# 의문형 판정. 물음표가 없는 한국어 질문도 잡아야 한다.
_QUESTION_TAIL_RE = re.compile(
    r"(?:\?|까요|나요|ㄹ까|을까|일까|인가요|가요|는지|어때|어떻게|왜|뭐야|뭔가요)"
    r"[\s.!]*$"
)

# 화자를 마커로 구분하지 못했을 때 사용자에게 보여줄 문구.
WARN_HEURISTIC = (
    "화자 표시를 찾지 못해 문단 길이와 말투로 추정했습니다 — "
    "사용자/AI 구분이 정확하지 않을 수 있습니다."
)
WARN_NO_SPEAKERS = (
    "화자를 구분하지 못했습니다 — 전체를 하나의 흐름으로 처리합니다. "
    "분석 정확도가 낮을 수 있습니다."
)


# ---------------------------------------------------------------------------
# 결과
# ---------------------------------------------------------------------------


@dataclass
class ParsedMessage:
    """메시지 한 개.

    `source_start`/`source_end`는 **사용자가 붙여넣은 원문 문자열 기준**
    이다(Python 코드포인트). 정규화한 문자열 기준이 아니다 — 화면에서
    "이 문장이 원문 어디에서 나왔는지" 되짚으려면 원문 좌표여야 한다.
    """

    index: int
    role: str
    text: str
    source_start: int
    source_end: int
    content_hash: str

    @property
    def excerpt(self) -> str:
        """목록 화면에 보여줄 짧은 발췌."""
        flat = " ".join(self.text.split())
        if len(flat) <= SOURCE_EXCERPT_MAX_CHARS:
            return flat
        return flat[: SOURCE_EXCERPT_MAX_CHARS - 1] + "…"

    def to_message_ref(self) -> MessageRef:
        return MessageRef(
            message_index=self.index,
            role=self.role,
            content_hash=self.content_hash,
            source_start=self.source_start,
            source_end=self.source_end,
            source_excerpt=self.excerpt,
        )


@dataclass
class ParsedConversation:
    """대화 한 건의 분리 결과."""

    messages: list[ParsedMessage] = field(default_factory=list)
    split_method: str = SPLIT_SINGLE
    source_type: str = SOURCE_OTHER
    warnings: list[str] = field(default_factory=list)

    @property
    def speakers_detected(self) -> bool:
        """화자를 **확실히** 구분했는가.

        휴리스틱으로 추정한 경우는 False다. 추정을 확신처럼 다루면
        "AI만 제안한 내용"이 사용자 발언으로 둔갑해 중요도가 부풀려진다
        (§9.5, §11.1.1). 이 값이 False면 사용자 강조도 가중치를 0으로
        두고 나머지를 재정규화해야 한다.
        """
        return self.split_method == SPLIT_MARKER

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def hashes(self) -> list[str]:
        """재복사 판정(§6.5)에 넘길 해시 배열."""
        return [m.content_hash for m in self.messages]

    def to_message_refs(self) -> list[MessageRef]:
        """`analysis_json.messages`에 저장할 형태."""
        return [m.to_message_ref() for m in self.messages]

    def role_counts(self) -> dict[str, int]:
        counts = {ROLE_USER: 0, ROLE_ASSISTANT: 0, ROLE_UNKNOWN: 0}
        for message in self.messages:
            counts[message.role] = counts.get(message.role, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def parse_conversation(raw_content: str) -> ParsedConversation:
    """붙여넣은 원문을 메시지 목록으로 자른다.

    §18.4의 3단계 폴백을 그대로 따른다. 위 단계가 실패하면 아래로
    내려가되, **어느 단계에서도 예외를 던지지 않는다** — 형식이 이상한
    붙여넣기 하나 때문에 저장 자체가 막히면 안 된다.
    """
    if not raw_content or not raw_content.strip():
        return ParsedConversation(messages=[], split_method=SPLIT_SINGLE)

    by_marker = _split_by_markers(raw_content)
    if by_marker is not None:
        return by_marker

    by_heuristic = _split_by_blocks(raw_content)
    if by_heuristic is not None:
        return by_heuristic

    return _single_message(raw_content)


# ---------------------------------------------------------------------------
# 1) 화자 마커
# ---------------------------------------------------------------------------


def _split_by_markers(raw: str) -> ParsedConversation | None:
    """`You said:` 같은 표시로 자른다. 마커가 2개 미만이면 실패로 본다."""
    hits = [
        (match.start(), match.end(), *_marker_meta(match))
        for match in _MARKER_RE.finditer(raw)
    ]
    if len(hits) < 2:
        return None

    messages: list[ParsedMessage] = []
    for position, (marker_start, body_start, role, _) in enumerate(hits):
        body_end = hits[position + 1][0] if position + 1 < len(hits) else len(raw)
        message = _make_message(raw, len(messages), role, body_start, body_end)
        if message is not None:
            messages.append(message)

    if len(messages) < 2:
        # 마커는 있는데 알맹이가 없다 — 화자 표시만 복사된 경우.
        return None

    return ParsedConversation(
        messages=messages,
        split_method=SPLIT_MARKER,
        source_type=_detect_source(hits),
    )


def _marker_meta(match: re.Match) -> tuple[str, str]:
    """어느 마커가 걸렸는지 찾아 (역할, 출처)를 돌려준다."""
    for index, (role, source, _) in enumerate(_MARKER_SPECS):
        if match.group(f"g{index}") is not None:
            return role, source
    return ROLE_UNKNOWN, SOURCE_OTHER


def _detect_source(hits: list[tuple]) -> str:
    """어느 서비스에서 복사했는지. 판단이 갈리면 `other`로 둔다."""
    found = {hit[3] for hit in hits} - {SOURCE_OTHER}
    if len(found) == 1:
        return found.pop()
    return SOURCE_OTHER


# ---------------------------------------------------------------------------
# 2) 빈 줄 + 길이·문체 휴리스틱
# ---------------------------------------------------------------------------


def _split_by_blocks(raw: str) -> ParsedConversation | None:
    """문단으로 자르고 길이·말투로 화자를 **추정**한다.

    추정 규칙은 하나뿐이다 — 사용자 턴은 대체로 짧고 질문이다.
    중앙값 길이를 기준으로 삼는 이유: 평균은 유난히 긴 AI 답변 하나에
    끌려가서 나머지를 전부 "짧다"로 만들어 버린다.

    문단이 2개 미만이면 나눌 것이 없으므로 실패로 본다.
    """
    blocks = _blocks_with_offsets(raw)
    if len(blocks) < 2:
        return None

    lengths = [len(text) for _, _, text in blocks]
    median = statistics.median(lengths)

    roles = [_guess_role(text, median) for _, _, text in blocks]
    merged = _merge_adjacent_same_role(blocks, roles)

    if len(merged) < 2:
        # 전부 같은 화자로 추정됐다 — 추정에 실패한 것과 다르지 않다.
        return None

    messages: list[ParsedMessage] = []
    for role, start, end in merged:
        message = _make_message(raw, len(messages), role, start, end)
        if message is not None:
            messages.append(message)

    if len(messages) < 2:
        return None

    return ParsedConversation(
        messages=messages,
        split_method=SPLIT_HEURISTIC,
        source_type=SOURCE_OTHER,
        warnings=[WARN_HEURISTIC],
    )


def _blocks_with_offsets(raw: str) -> list[tuple[int, int, str]]:
    """빈 줄로 나눈 문단들의 (시작, 끝, 본문). 빈 문단은 버린다."""
    out: list[tuple[int, int, str]] = []
    cursor = 0
    for piece in _BLOCK_SPLIT_RE.split(raw):
        start = raw.find(piece, cursor) if piece else -1
        if start < 0:
            continue
        end = start + len(piece)
        cursor = end
        if piece.strip():
            out.append((start, end, piece))
    return out


def _guess_role(text: str, median_length: float) -> str:
    """사용자 턴은 대체로 짧고 의문형이다 (§18.4)."""
    stripped = text.strip()
    is_question = bool(_QUESTION_TAIL_RE.search(stripped))
    is_short = len(stripped) <= median_length

    if is_question and is_short:
        return ROLE_USER
    # 질문이 아니어도 눈에 띄게 짧으면 사용자 발언으로 본다.
    if len(stripped) <= median_length * 0.5:
        return ROLE_USER
    return ROLE_ASSISTANT


def _merge_adjacent_same_role(
    blocks: list[tuple[int, int, str]], roles: list[str]
) -> list[tuple[str, int, int]]:
    """같은 화자의 연속 문단은 한 턴이다 — 붙여서 하나로 만든다."""
    merged: list[tuple[str, int, int]] = []
    for (start, end, _), role in zip(blocks, roles):
        if merged and merged[-1][0] == role:
            previous_role, previous_start, _ = merged[-1]
            merged[-1] = (previous_role, previous_start, end)
        else:
            merged.append((role, start, end))
    return merged


# ---------------------------------------------------------------------------
# 3) 분리 포기
# ---------------------------------------------------------------------------


def _single_message(raw: str) -> ParsedConversation:
    """화자도 턴도 못 나눴다. 그래도 원문 한 덩어리는 남긴다.

    빈손으로 돌려주지 않는 이유: 순번만 있어도 Timeline은 만들어지고,
    출처 추적도 "이 대화의 이 위치"까지는 여전히 가리킬 수 있다.
    """
    message = _make_message(raw, 0, ROLE_UNKNOWN, 0, len(raw))
    return ParsedConversation(
        messages=[message] if message else [],
        split_method=SPLIT_SINGLE,
        source_type=SOURCE_OTHER,
        warnings=[WARN_NO_SPEAKERS],
    )


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------


def _make_message(
    raw: str, index: int, role: str, start: int, end: int
) -> ParsedMessage | None:
    """구간을 메시지로 만든다. 알맹이가 없으면 None.

    앞뒤 공백은 offset에서 **제외**한다 — 그러지 않으면 화면에서 발췌를
    강조할 때 빈 줄까지 같이 칠해진다.
    """
    segment = raw[start:end]
    stripped = segment.strip()
    if not stripped:
        return None

    offset = start + (len(segment) - len(segment.lstrip()))
    return ParsedMessage(
        index=index,
        role=role,
        text=stripped,
        source_start=offset,
        source_end=offset + len(stripped),
        content_hash=hash_message(role, stripped),
    )
