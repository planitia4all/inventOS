"""Conversation Engine의 조정 가능한 상수.

전부 한 곳에 모아 두는 이유: 이 값들은 설계로 확정된 것이 아니라
**실사용(UAT) 피드백으로 조정해야 하는 값**이다. 코드 여기저기에
흩어져 있으면 조정할 때 어디를 고쳐야 하는지 알 수 없게 된다.

설계 문서 `docs/conversation-engine-design.md` §29.3 참고.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 스키마 / 프롬프트 버전
# ---------------------------------------------------------------------------

# analysis_json 구조 버전. 필드를 추가/변경할 때 올린다 (§26).
CURRENT_SCHEMA_VERSION = "1.0"

# 프롬프트를 바꾸면 올린다 — 같은 대화라도 다른 프롬프트로 분석했으면
# 결과를 비교할 때 이 값으로 구분한다.
CURRENT_PROMPT_VERSION = "conversation-analysis-1.0"

# 동의어 사전이 비어 있는 초기 상태의 버전 (§27.2.2).
INITIAL_SYNONYM_DICT_VERSION = 0

# ---------------------------------------------------------------------------
# 중복 / 유사도 판정
# ---------------------------------------------------------------------------

# 재분석 결과가 이전 항목의 "수정본으로 보이는지" 판단하는 임계값 (§27.3).
# 이 값을 넘어도 사용자 판단을 자동 복사하지 않는다 — 질문만 한다.
SIMILAR_THRESHOLD = 0.85

# 두 대화가 겹친다고 인정하는 최소 메시지 수 (§6.5.2).
# 이보다 적게 겹치면 우연의 일치로 보고 `new`로 판정한다
# (예: 두 대화가 모두 "안녕하세요"로 시작하는 경우).
MIN_OVERLAP_MESSAGES = 3

# ---------------------------------------------------------------------------
# 상태 판정
# ---------------------------------------------------------------------------

# 최근 N회차 동안 언급이 없으면 `dormant`로 표시한다 (§9.4).
# 폐기가 아니라 "확인해 보라"는 힌트일 뿐이다.
DORMANT_AFTER_SEQUENCES = 3

# ---------------------------------------------------------------------------
# 분량 제한
# ---------------------------------------------------------------------------

# 한 번에 붙여넣을 수 있는 원문 상한. 넘으면 경고하고 사용자가 결정한다.
MAX_RAW_CONTENT_CHARS = 300_000

# 분석에 의미가 있는 최소 분량. 이보다 짧으면 분석 버튼을 막는다.
MIN_RAW_CONTENT_CHARS = 200

# SourceReference에 보관하는 원문 발췌 최대 길이 (§12).
# 길게 잡으면 analysis_json이 원문의 사본이 되어 버린다.
SOURCE_EXCERPT_MAX_CHARS = 200

# ---------------------------------------------------------------------------
# 중요도 가중치 (§11.2)
# ---------------------------------------------------------------------------

# 가중치를 바꾸면 이 버전을 올린다. 과거에 계산된 점수를 해석할 때
# "어떤 가중치로 계산된 값인가"를 알 수 있어야 하기 때문이다 (§11.3).
IMPORTANCE_WEIGHTS_VERSION = "v1"

IMPORTANCE_WEIGHTS: dict[str, float] = {
    "f": 0.15,  # 등장 빈도
    "s": 0.15,  # 대화 확산도
    "p": 0.10,  # 지속성
    "r": 0.15,  # 최근성
    "u": 0.20,  # 사용자 강조 (태도 가중, §11.1.1)
    "d": 0.10,  # 결정 영향도
    "c": 0.05,  # 연결도
    "e": 0.10,  # 증거 보유
}

# 발언 태도별 가중치 (§11.1.1).
# user_rejected가 0.0인 것이 핵심 — 사용자가 "아니다"라고 열 번 말한
# 개념이 중요도 상위에 오르면 안 된다.
STANCE_WEIGHT: dict[str, float] = {
    "user_adopted": 1.0,
    "user_proposed": 1.0,
    "user_agreed": 0.8,
    "user_asked": 0.6,
    "ai_proposed": 0.2,
    "user_deferred": 0.1,
    "user_rejected": 0.0,
}

# 태도의 강도 순서. 한 요소에 여러 태도가 나타나면 가장 강한 것을
# origin_stance로 삼는다 (§9.5).
STANCE_PRIORITY: tuple[str, ...] = (
    "user_adopted",
    "user_proposed",
    "user_agreed",
    "user_asked",
    "ai_proposed",
    "user_deferred",
    "user_rejected",
)


# ---------------------------------------------------------------------------
# ConversationImport 컬럼 값 (1단계, §18)
# ---------------------------------------------------------------------------
# DB Native Enum을 쓰지 않고 문자열 + Python 검증으로 둔다 — 값이 하나
# 늘어날 때마다 Migration을 돌려야 하는 상황을 피하기 위해서다.

ANALYSIS_STATUS_PENDING = "pending"
ANALYSIS_STATUS_ANALYZING = "analyzing"
ANALYSIS_STATUS_ANALYZED = "analyzed"
ANALYSIS_STATUS_FAILED = "failed"
ANALYSIS_STATUS_NEEDS_REANALYSIS = "needs_reanalysis"

ANALYSIS_STATUSES: tuple[str, ...] = (
    ANALYSIS_STATUS_PENDING,
    ANALYSIS_STATUS_ANALYZING,
    ANALYSIS_STATUS_ANALYZED,
    ANALYSIS_STATUS_FAILED,
    ANALYSIS_STATUS_NEEDS_REANALYSIS,
)

SUMMARY_STATUS_NOT_GENERATED = "not_generated"
SUMMARY_STATUS_VALID = "valid"
SUMMARY_STATUS_NEEDS_REGENERATION = "needs_regeneration"
SUMMARY_STATUS_FAILED = "failed"

SUMMARY_STATUSES: tuple[str, ...] = (
    SUMMARY_STATUS_NOT_GENERATED,
    SUMMARY_STATUS_VALID,
    SUMMARY_STATUS_NEEDS_REGENERATION,
    SUMMARY_STATUS_FAILED,
)

# 요약 체인 검증 결과 (§10). summary_status와 값이 겹치지만 다른 개념이다 —
# 이쪽은 "지금 검사해 보니 이렇더라"는 계산 결과고, summary_status는
# 레코드에 저장된 상태다.
CHAIN_VALID = "valid"
CHAIN_MISSING_PREVIOUS = "missing_previous"
CHAIN_BEFORE_HASH_MISMATCH = "before_hash_mismatch"
CHAIN_MISSING_AFTER_SUMMARY = "missing_after_summary"
CHAIN_NEEDS_REGENERATION = "needs_regeneration"

# 원문 중복 검사 결과 (§6).
DUPLICATE_NEW = "new"
DUPLICATE_SAME_INVENTION = "exact_duplicate_same_invention"
DUPLICATE_OTHER_INVENTION = "exact_duplicate_other_invention"

# 대화 출처.
SOURCE_TYPES: tuple[str, ...] = ("chatgpt", "claude", "other", "file")
