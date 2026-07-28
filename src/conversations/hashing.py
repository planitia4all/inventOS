"""원문/메시지 해시, item_id 생성, 중복 판정, 원문 위치 찾기.

전부 **순수 함수**다 — DB도 AI도 건드리지 않는다. 그래서 Parser·Service·UI가
아직 없어도 계약을 테스트로 고정할 수 있다.

여기서 정하는 계약 (설계 문서 §6.4, §6.5, §12, §27.2):

- 표시용 원문은 절대 바꾸지 않는다. 정규화는 **해시/비교 계산에만** 쓴다.
- `item_id`는 내용 기반이라 재분석해도 같은 제안이면 같은 값이 나온다.
- 동의어 사전이 바뀌면 `item_id`도 바뀌므로 `remap_item_ids()`로 이관한다.
- 원문 위치(offset)는 AI가 세지 않는다. 앱이 `str.find()`로 계산한다.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from typing import Callable

from src.conversations.constants import MIN_OVERLAP_MESSAGES, SIMILAR_THRESHOLD

# ---------------------------------------------------------------------------
# 내장 약어 사전 (§10.4)
# ---------------------------------------------------------------------------

# 대표어 → 같은 뜻의 표기들. 전부 소문자·단일공백 기준으로 적는다
# (정규화 3단계까지 끝난 문자열에 적용되기 때문).
# 프로젝트가 내장하는 값이며 사용자가 편집하지 않는다 (오염 방지).
BUILTIN_ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    "tgv": ("through glass via", "throughglassvia", "유리 관통 비아",
            "유리관통비아", "글라스 비아", "글라스비아", "유리 비아", "유리비아"),
    "pcb": ("printed circuit board", "인쇄 회로 기판", "인쇄회로기판"),
    "cte": ("coefficient of thermal expansion", "열팽창 계수", "열팽창계수"),
    "sem": ("scanning electron microscope", "주사 전자 현미경"),
}

# 의미를 바꾸지 않는 군더더기 표현 (정규화 7단계).
_FILLER_WORDS = (
    "그러니까", "말하자면", "다시 말해", "다시말해", "결국", "사실상",
    "어쨌든", "요컨대", "이를테면",
)

# 붙여넣기에 딸려오는 UI 부스러기. 대화 내용이 아니므로 해시 계산에서 뺀다.
_UI_NOISE_PATTERNS = (
    r"you said:", r"chatgpt said:", r"claude said:", r"assistant said:",
    r"copy code", r"copy", r"복사(하기)?", r"코드 복사",
    r"regenerate( response)?", r"edit", r"편집", r"공유하기", r"share",
    r"\bnew chat\b", r"이 대화 공유",
)
# 줄바꿈까지 함께 먹는다. 그러지 않으면 UI 문구를 지운 자리에 빈 줄이 남아,
# "UI 문구만 다른 대화"가 다른 해시를 갖게 된다.
_UI_NOISE_RE = re.compile(
    r"^[ \t]*(?:" + "|".join(_UI_NOISE_PATTERNS) + r")[ \t]*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)

# 한국어 조사. 긴 것부터 검사한다 (§10.4).
# 주의: 어간이 2자 미만으로 줄어들면 떼지 않는다 — 이 가드가 없으면
# "정도"→"정", "결과"→"결", "온도"→"온" 같은 오작동이 난다.
_PARTICLES: tuple[str, ...] = (
    "으로써", "으로서", "에서는", "에게서", "이라고", "라고",
    "으로", "에서", "까지", "부터", "에게", "한테", "이나", "라도",
    "보다", "처럼", "마다", "만큼", "조차", "밖에",
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만", "로",
)
_MIN_STEM_LEN = 2

_LIST_MARKER_RE = re.compile(r"^[\s]*(?:[-•*▪□○●·]+|\d+[.)]|[가-힣][.)])\s*", re.MULTILINE)
_PUNCTUATION_RE = re.compile(r"[.,;:!?()\[\]{}\"'`~…·″“”‘’]")
_REPEAT_WORD_RE = re.compile(r"\b(\S+)(?:\s+\1\b)+")
_FILLER_RE = re.compile("|".join(re.escape(w) for w in _FILLER_WORDS))

_BOM = "﻿"


# ---------------------------------------------------------------------------
# 원문 정규화 / 해시 (§6.4)
# ---------------------------------------------------------------------------


def normalize_raw_content(text: str) -> str:
    """해시 계산용 원문 정규화. **표시용 원문은 이 함수를 거치지 않는다.**

    - BOM 제거
    - 줄바꿈 통일 (CRLF/CR → LF)
    - 줄 끝 공백 제거, 연속 공백 1칸으로
    - 빈 줄 3개 이상 → 2개
    - 앞뒤 공백 제거
    """
    if not text:
        return ""
    s = text.replace(_BOM, "")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def strip_ui_noise(text: str) -> str:
    """붙여넣기에 딸려온 UI 문구를 지운다.

    `normalize_raw_content()`와 분리해 둔 이유: UI 문구 목록은 서비스가
    화면을 바꿀 때마다 흔들리는 값이라, 순수한 공백 정규화와 수명이 다르다.
    """
    if not text:
        return ""
    s = _UI_NOISE_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def hash_raw_content(text: str) -> str:
    """전체 원문의 SHA-256 (§6.4 1단계 중복 검사).

    공백·줄바꿈·UI 문구만 다른 대화는 **같은 해시**가 나온다.
    """
    normalized = strip_ui_noise(normalize_raw_content(text))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_message(role: str, text: str) -> str:
    """메시지 하나의 SHA-256 (§6.5 2단계 중복 검사).

    **역할(role)을 포함한다** — 같은 문장이라도 사용자가 말한 것과 AI가
    말한 것은 발명 기록에서 전혀 다른 의미를 갖기 때문이다 (§9.5).
    """
    normalized = strip_ui_noise(normalize_raw_content(text))
    payload = f"{(role or '').strip().lower()}\n{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# item_id 정규화 (§27.2.1)
# ---------------------------------------------------------------------------


def strip_particle(token: str) -> str:
    """조사로 보이는 꼬리를 뗀다. 어간이 2자 미만이 되면 원본을 유지한다 (§10.4).

    형태소 분석기 없이 하는 근사치라 완벽하지 않다. **과하게 떼는 것보다
    덜 떼는 편이 안전하므로** 가드를 두었다.
    """
    for particle in sorted(_PARTICLES, key=len, reverse=True):
        if token.endswith(particle) and len(token) - len(particle) >= _MIN_STEM_LEN:
            return token[: -len(particle)]
    return token


def strip_particles(text: str) -> str:
    """공백으로 나눈 각 토큰에서 조사를 뗀다."""
    return " ".join(strip_particle(t) for t in text.split(" ") if t)


def _apply_phrase_map(text: str, canonical_to_variants: dict[str, tuple[str, ...]]) -> str:
    """긴 표기부터 대표어로 치환한다 (짧은 것이 먼저 걸려 부분 치환되지 않게)."""
    pairs: list[tuple[str, str]] = []
    for canonical, variants in canonical_to_variants.items():
        for variant in variants:
            if variant:
                pairs.append((variant, canonical))
    for variant, canonical in sorted(pairs, key=lambda p: len(p[0]), reverse=True):
        text = re.sub(re.escape(variant), canonical, text)
    return text


def normalize_item_text(
    text: str,
    synonym_map: dict[str, tuple[str, ...]] | None = None,
    synonym_dict_version: int = 0,
) -> str:
    """item_id 계산용 정규화 (7단계).

    순서가 계약이다 — 바뀌면 같은 제안이 다른 id를 갖게 된다.

    1. 유니코드 정규화(NFKC)  — 전각 문장부호가 ASCII로 바뀌어 4단계가 잡는다
    2. 영문 소문자화
    3. 줄바꿈·공백 통합
    4. 문장부호·목록기호 제거
    4.5 한국어 조사 제거          ← 아래 주석 참고
    5. 대표 용어 치환 (내장 약어 사전)
    6. 사용자 동의어 사전 적용
    7. 반복 표현 정리

    **4.5/6.5단계(조사 제거)는 계약에 없던 것을 구현 중에 추가한 것이다.**
    한국어 조사는 앞 음절의 받침에 따라 형태가 바뀌어서, 조사를 두면
    동의어 치환이 제 역할을 못 한다::

        "그래핀 실을 사용"   → 치환 → "그래핀 섬유을 사용"   (을)
        "그래핀 섬유를 사용" → 그대로 "그래핀 섬유를 사용"   (를)
        → 같은 뜻인데 item_id가 달라진다

    치환 **전후로 두 번** 떼야 하는 이유: "실을"은 어간이 1자라 2자 가드에
    걸려 앞에서 못 뗀다. 치환으로 "섬유을"이 되고 나서야 어간이 2자가 되어
    뗄 수 있다. 두 번 돌리면 양쪽 다 "그래핀 섬유 사용"으로 수렴한다.

    설계 문서 §10.4에 조사 제거가 이미 있었으나 §27.2.1의 7단계 목록에는
    빠져 있었다 — 문서를 이 구현에 맞춰 갱신해야 한다.

    `synonym_dict_version`은 **해시 입력에 들어가지 않는다.** 사전이 바뀌면
    5·6단계 결과가 달라져 자연히 다른 id가 되고, 버전을 해시에 넣으면
    내용이 그대로인 항목까지 id가 바뀌어 버리기 때문이다. 버전은
    `analysis_json`에 따로 기록해 두었다가 remap 시점 판단에만 쓴다 (§27.2.2).
    """
    if not text:
        return ""

    s = unicodedata.normalize("NFKC", text)          # 1
    s = s.lower()                                     # 2
    s = s.replace("\r\n", "\n").replace("\r", "\n")   # 3
    s = _LIST_MARKER_RE.sub("", s)                    # 4 (목록기호)
    s = _PUNCTUATION_RE.sub("", s)                    # 4 (문장부호)
    s = re.sub(r"\s+", " ", s).strip()                # 3 마무리
    s = strip_particles(s)                            # 4.5
    s = _apply_phrase_map(s, BUILTIN_ABBREVIATIONS)   # 5
    if synonym_map:
        s = _apply_phrase_map(s, synonym_map)         # 6
    s = strip_particles(s)                            # 6.5 (치환으로 생긴 조사 정리)
    s = _FILLER_RE.sub(" ", s)                        # 7
    s = _REPEAT_WORD_RE.sub(r"\1", s)                 # 7
    return re.sub(r"\s+", " ", s).strip()


def build_item_id(
    change_type: str,
    target_field: str,
    text: str,
    synonym_map: dict[str, tuple[str, ...]] | None = None,
    synonym_dict_version: int = 0,
) -> str:
    """재분석을 견디는 결정론적 식별자 (§27.2).

    해시 입력은 문서 계약과 동일하다::

        change_type | target_field | normalized_text

    `synonym_dict_version`은 해시에 넣지 않는다(이유는
    `normalize_item_text()` 참고). 인자로 받는 것은 정규화에 넘기기 위해서다.
    """
    normalized = normalize_item_text(text, synonym_map, synonym_dict_version)
    payload = f"{change_type}|{target_field}|{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 동의어 사전 변경 remap (§27.2.2)
# ---------------------------------------------------------------------------


@dataclass
class RemapConflict:
    """여러 옛 항목이 하나의 새 id로 합쳐졌는데 사용자 판단이 서로 다른 경우.

    **임의로 하나를 고르지 않는다.** 사용자가 직접 정해야 한다.
    """

    new_item_id: str
    old_item_ids: list[str]
    decisions: list[dict]


@dataclass
class RemapResult:
    mapping: dict[str, str] = field(default_factory=dict)
    migrated_reviews: list[dict] = field(default_factory=list)
    conflicts: list[RemapConflict] = field(default_factory=list)
    merged_groups: dict[str, list[str]] = field(default_factory=dict)
    orphaned_reviews: list[dict] = field(default_factory=list)


def _decision_signature(review: dict) -> tuple:
    """두 판단이 '같다'고 볼 수 있는지 비교하기 위한 값."""
    return (review.get("decision"), review.get("edited_text"))


def _is_real_decision(review: dict) -> bool:
    return review.get("decision") not in (None, "", "unreviewed")


def remap_item_ids(
    items: list[dict],
    user_reviews: list[dict],
    old_synonym_map: dict[str, tuple[str, ...]] | None,
    new_synonym_map: dict[str, tuple[str, ...]] | None,
    old_version: int,
    new_version: int,
) -> RemapResult:
    """동의어 사전이 바뀌었을 때 사용자 판단을 새 item_id로 옮긴다.

    결정론적이고 AI 호출이 없다. 자동 이관은 **동일성이 확실할 때만** 한다:

    - 옛 id 하나 → 새 id 하나  : 그대로 이관
    - 옛 id 여럿 → 새 id 하나  : 판단이 서로 같으면 이관, 다르면 `conflicts`
    - 매핑에 없는 판단          : `orphaned_reviews`로 보관 (삭제하지 않음)

    `items`/`user_reviews`는 `AnalysisItem.to_json()` /
    `UserDecision.to_json()` 형태의 dict 목록이다. 입력을 수정하지 않는다.
    """
    result = RemapResult()

    old_to_new: dict[str, str] = {}
    new_to_old: dict[str, list[str]] = {}
    for item in items:
        old_id = item.get("item_id") or build_item_id(
            item.get("change_type", ""), item.get("target_field", ""),
            item.get("text", ""), old_synonym_map, old_version)
        new_id = build_item_id(
            item.get("change_type", ""), item.get("target_field", ""),
            item.get("text", ""), new_synonym_map, new_version)
        old_to_new[old_id] = new_id
        new_to_old.setdefault(new_id, []).append(old_id)

    result.mapping = old_to_new
    result.merged_groups = {
        new_id: olds for new_id, olds in new_to_old.items() if len(olds) > 1
    }

    reviews_by_old: dict[str, dict] = {}
    for review in user_reviews:
        item_id = review.get("item_id")
        if item_id is not None:
            reviews_by_old[item_id] = review

    handled: set[str] = set()

    for new_id, old_ids in new_to_old.items():
        group_reviews = [reviews_by_old[o] for o in old_ids if o in reviews_by_old]
        real = [r for r in group_reviews if _is_real_decision(r)]
        handled.update(o for o in old_ids if o in reviews_by_old)

        if not real:
            continue

        signatures = {_decision_signature(r) for r in real}
        if len(signatures) > 1:
            result.conflicts.append(RemapConflict(
                new_item_id=new_id,
                old_item_ids=[o for o in old_ids if o in reviews_by_old],
                decisions=[dict(r) for r in real],
            ))
            continue

        carried = dict(real[0])
        carried["original_item_id"] = carried.get("item_id")
        carried["item_id"] = new_id
        result.migrated_reviews.append(carried)

    for old_id, review in reviews_by_old.items():
        if old_id not in handled:
            result.orphaned_reviews.append(dict(review))

    return result


# ---------------------------------------------------------------------------
# 재분석 시 사용자 판단 이어받기 (§27.3)
# ---------------------------------------------------------------------------


@dataclass
class ReanalysisMerge:
    """재분석 결과에 이전 판단을 어떻게 이어붙일지 계산한 결과.

    `items`는 `match_type` / `related_previous_item_id` / `similarity_score` /
    `carried_over`가 채워진 새 항목 목록이다.
    """

    items: list[dict] = field(default_factory=list)
    carried_decisions: list[dict] = field(default_factory=list)
    orphaned_decisions: list[dict] = field(default_factory=list)
    similar_pairs: list[tuple[str, str, float]] = field(default_factory=list)


def merge_user_reviews_after_reanalysis(
    previous_items: list[dict],
    previous_reviews: list[dict],
    new_items: list[dict],
    *,
    similarity_fn: Callable[[str, str], float],
    similar_threshold: float = SIMILAR_THRESHOLD,
    analysis_version: int | None = None,
) -> ReanalysisMerge:
    """재분석 결과에 이전 사용자 판단을 세 등급으로 이어붙인다 (§27.3).

    1. **동일** (`item_id` 일치) → 이전 판단을 그대로 이어받는다
    2. **유사** (유사도 ≥ 임계값) → **판단을 복사하지 않는다.**
       `related_previous_item_id`만 연결해 사용자에게 물어볼 수 있게 한다
    3. **신규** → 미검토 상태

    2등급에서 자동 복사하지 않는 이유: 유사도 0.87은 "거의 같다"가 아니라
    "꽤 비슷하다"일 뿐이다. `"상온에서 삽입한다"`와
    `"상온에서 삽입하지 않는다"`는 유사도가 매우 높다. 여기서 이전 승인을
    자동으로 옮기면 **사용자가 승인한 적 없는 내용이 본문에 들어간다.**

    `similarity_fn`을 주입받는 이유: 0단계에서는 유사도 구현(TF-IDF 등)에
    의존하지 않고 **병합 규칙 자체만** 계약으로 고정하기 위해서다.
    입력 목록은 수정하지 않는다.
    """
    reviews_by_id = {
        r["item_id"]: r for r in previous_reviews if r.get("item_id") is not None
    }
    prev_items = [i for i in previous_items if i.get("item_id")]

    merged: list[dict] = []
    carried: list[dict] = []
    similar_pairs: list[tuple[str, str, float]] = []
    matched_prev_ids: set[str] = set()

    for raw_item in new_items:
        item = dict(raw_item)
        item_id = item.get("item_id", "")

        if item_id in reviews_by_id:
            item["match_type"] = "exact"
            item["carried_over"] = _is_real_decision(reviews_by_id[item_id])
            matched_prev_ids.add(item_id)
            decision = dict(reviews_by_id[item_id])
            if analysis_version is not None:
                decision["carried_from_analysis_version"] = analysis_version
            carried.append(decision)
            merged.append(item)
            continue

        best_id, best_score = "", 0.0
        for prev in prev_items:
            score = similarity_fn(item.get("text", ""), prev.get("text", ""))
            if score > best_score:
                best_id, best_score = prev.get("item_id", ""), score

        if best_id and best_score >= similar_threshold:
            item["match_type"] = "similar"
            item["related_previous_item_id"] = best_id
            item["similarity_score"] = best_score
            item["carried_over"] = False          # ← 자동 복사 금지
            similar_pairs.append((item_id, best_id, best_score))
        else:
            item["match_type"] = "new"
            item["carried_over"] = False

        merged.append(item)

    orphaned = [
        dict(review) for old_id, review in reviews_by_id.items()
        if old_id not in matched_prev_ids and _is_real_decision(review)
    ]

    return ReanalysisMerge(
        items=merged,
        carried_decisions=carried,
        orphaned_decisions=orphaned,
        similar_pairs=similar_pairs,
    )


# ---------------------------------------------------------------------------
# 메시지 중복 / superset 판정 (§6.5)
# ---------------------------------------------------------------------------

EXACT_DUPLICATE = "exact_duplicate"
SUPERSET = "superset"
PARTIAL_OVERLAP = "partial_overlap"
NEW = "new"


@dataclass
class OverlapReport:
    """두 대화의 메시지 해시 나열을 비교한 결과.

    `newly_added_indices`가 **권위 있는 값**이다. `analyzed_range`는
    [처음, 마지막]을 요약한 편의값일 뿐이며, 신규 구간이 앞뒤로 흩어져
    있으면(예: 앞에 UI 머리말이 붙은 경우) 그 사이에 기존 메시지가
    섞여 있을 수 있다.
    """

    match_type: str = NEW
    already_imported_indices: list[int] = field(default_factory=list)
    newly_added_indices: list[int] = field(default_factory=list)
    analyzed_range: list[int] = field(default_factory=list)
    overlap_count: int = 0


def _find_sublist(haystack: list[str], needle: list[str]) -> int:
    """needle이 haystack 안에 순서 그대로 연속으로 들어 있으면 시작 위치."""
    if not needle or len(needle) > len(haystack):
        return -1
    first = needle[0]
    for start in range(len(haystack) - len(needle) + 1):
        if haystack[start] == first and haystack[start:start + len(needle)] == needle:
            return start
    return -1


def classify_overlap(
    existing_hashes: list[str],
    new_hashes: list[str],
    min_overlap: int = MIN_OVERLAP_MESSAGES,
) -> OverlapReport:
    """새 대화가 기존 대화와 어떻게 겹치는지 판정한다.

    - `exact_duplicate` : 완전히 같은 나열
    - `superset`        : 기존 나열이 순서 그대로 안에 들어 있고 뒤에 더 있음
                          (앞에 UI 머리말이 붙어도 인정한다)
    - `partial_overlap` : 겹치지만 순서가 맞지 않음
    - `new`             : 겹침이 `min_overlap`에 못 미침

    겹침이 `min_overlap`보다 적으면 우연의 일치로 본다 — 두 대화가 모두
    "안녕하세요"로 시작한다고 이어진 대화는 아니기 때문이다.
    """
    existing = list(existing_hashes or [])
    new = list(new_hashes or [])

    existing_set = set(existing)
    already = [i for i, h in enumerate(new) if h in existing_set]
    newly = [i for i, h in enumerate(new) if h not in existing_set]
    overlap_count = len(already)

    if new and new == existing:
        match_type = EXACT_DUPLICATE
    elif (overlap_count >= min_overlap
            and _find_sublist(new, existing) >= 0
            and len(new) > len(existing)):
        match_type = SUPERSET
    elif overlap_count >= min_overlap:
        match_type = PARTIAL_OVERLAP
    else:
        match_type = NEW
        already = []
        newly = list(range(len(new)))

    analyzed_range = [newly[0], newly[-1]] if newly else []
    return OverlapReport(
        match_type=match_type,
        already_imported_indices=already,
        newly_added_indices=newly,
        analyzed_range=analyzed_range,
        overlap_count=overlap_count,
    )


# ---------------------------------------------------------------------------
# 원문 위치 찾기 (§12.1.1)
# ---------------------------------------------------------------------------


@dataclass
class ExcerptLocation:
    """원문에서 발췌를 찾은 결과.

    Offset은 **Python 문자열(유니코드 코드포인트) 기준**이다.
    UTF-8 바이트 오프셋이 아니므로, 한글이든 이모지든 1글자가 1이다.
    """

    source_start: int = -1
    source_end: int = -1
    matched: bool = False
    ambiguous: bool = False
    occurrences: int = 0


def locate_excerpt(raw_content: str, source_excerpt: str,
                   search_from: int = 0) -> ExcerptLocation:
    """발췌가 원문의 어디에 있는지 찾는다.

    AI에게 문자 위치를 세게 하지 않는 이유: LLM은 그걸 거의 틀린다.
    대신 프롬프트에서 발췌를 **원문 그대로 인용**하게 하고, 위치는 여기서
    `str.find()`로 계산한다.

    - 원문을 고쳐서 억지로 맞추지 않는다. 못 찾으면 `(-1, -1)`이다.
    - 같은 문장이 여러 번 나오면 첫 위치를 쓰고 `ambiguous=True`로 표시한다.
    """
    if not raw_content or not source_excerpt:
        return ExcerptLocation()

    start = raw_content.find(source_excerpt, max(0, search_from))
    if start < 0 and search_from > 0:
        start = raw_content.find(source_excerpt)
    if start < 0:
        return ExcerptLocation(occurrences=0)

    occurrences = raw_content.count(source_excerpt)
    return ExcerptLocation(
        source_start=start,
        source_end=start + len(source_excerpt),
        matched=True,
        ambiguous=occurrences > 1,
        occurrences=occurrences,
    )
