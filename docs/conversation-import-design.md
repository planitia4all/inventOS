# Conversation Import Engine 설계

> **상태: 설계 초안 (미구현)**
> 대상 버전: `0.5.0` — `0.4.0` 정식 릴리스(UAT 완료) 이후 착수한다.
> 이 문서는 코드가 아니다. `0.4.0` 코드 동결에는 영향을 주지 않는다.

---

## 1. 목적

실제 발명 과정은 대부분 이렇게 흘러간다.

```
아이디어 발생 → AI와 수십~수백 번 대화 → 기술 검토 → 아이디어 발전 → 실험 계획 → 발명노트 작성
```

발명노트를 쓰기 시작하는 시점에는 이미 대화 안에 내용이 다 들어 있다.
현재 InventOS는 이 대화를 전혀 활용하지 못하고, 사용자가 손으로 다시
옮겨 적어야 한다.

Conversation Import는 그 대화를 통째로 붙여넣으면 발명노트로 바꿔주는
기능이다. 핵심은 **요약이 아니라 발전 과정의 복원**이다. 최종 아이디어만
뽑아내는 것은 요약기가 하는 일이고, InventOS가 해야 하는 것은
"레이저만 쓰다가 → 그래핀을 추가했고 → 결국 금속핀 방식으로 바꿨다"는
변화의 순서를 Timeline으로 세우는 것이다.

### 1.1 v1 범위

**포함**
- 대화 전체 텍스트 붙여넣기 (CTRL+V)
- 하나의 대화에서 여러 발명 후보 추출 + 사용자 선택
- 발명노트 필드 자동 분류 (제목/문제/기존기술/한계/핵심아이디어/작동원리/효과 등)
- 발전 과정 Timeline 자동 생성
- 실험 내용 추출
- 기술 키워드 → 태그 자동 생성
- 기존 발명과의 중복/유사 검사
- 기존 발명에 후속으로 연결(파생) 또는 신규 생성 선택
- 발명 성숙도 평가 + 부족한 정보 제안
- 원본 대화 보존

**제외 (v1 이후)**
- 대화 링크(URL) 입력 — 구조만 대비하고 구현하지 않음 (§4)
- 이미지/PDF 자동 첨부 — 붙여넣기로는 불가능 (§11)
- 파일 가져오기(.md/.txt/.html) — 어댑터 자리만 만들어 두고 v1.1에서 추가

---

## 2. 설계 원칙 (반드시 지킬 것)

이 기능은 **새로운 입력 방식일 뿐**이며, 최종 저장 구조는 기존과 완전히
동일하다.

```
Conversation → Conversation Parser → 기존 InventOS Service → DB
```

1. **새 테이블/새 모델을 만들지 않는다.** 결과는 전부 기존
   `Invention` / `InventionEvent` / `InventionRevision` /
   `InventionAIResult` / `Experiment` / `Tag` / `Attachment`에 들어간다.
2. **기존 서비스 계층을 우회하지 않는다.** `InventionService.create()`,
   `TimelineService.log()`, `TagService.add_tags()`,
   `ExperimentService.create()`, `AIResultService.create_draft()`를 그대로
   호출한다. Parser는 DB를 직접 만지지 않는다.
3. **AI 없이도 앱이 죽지 않는다.** Mock Provider에서도 구조적으로 유효한
   결과를 낸다 (§10).
4. **원본을 덮어쓰지 않는다.** 붙여넣은 대화 원문은 항상 보존한다 (§9.3).
5. **하나의 트랜잭션.** 가져오기 실행은 `run_and_rerun`으로 감싼 단일
   트랜잭션이다 — 중간에 실패하면 발명만 반쯤 만들어지는 일이 없어야 한다.
   (`InventionService.create_child()`가 이미 쓰는 방식과 동일)

---

## 3. 전체 구조

```
┌─────────────────────────────────────────────────────────┐
│ 입력 어댑터 (여러 개)                                     │
│  PasteAdapter / MarkdownFileAdapter / HtmlFileAdapter    │
│  → 전부 동일한 Conversation 객체를 만든다                  │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ ConversationParser (입력 형식과 무관하게 하나만 존재)       │
│  1) 턴 분리 (User / AI)                                   │
│  2) 청크 분할                                             │
│  3) [map]  청크별 신호(signal) 추출  ← AI 호출 N회         │
│  4) [reduce] 신호 → 발명 후보 클러스터링 ← AI 호출 1~3회    │
│  5) 후보별 구조화 + Timeline 조립                          │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ ImportPlan  (아직 DB에 아무것도 쓰지 않은 상태)             │
│  - 발명 후보 N개                                          │
│  - 후보별 중복 검사 결과                                   │
│  - 사용자 선택 대기                                        │
└───────────────────────┬─────────────────────────────────┘
                        ▼ (사용자가 선택 후 "가져오기")
┌─────────────────────────────────────────────────────────┐
│ ConversationImportService                                │
│  기존 서비스만 호출해서 저장 (단일 트랜잭션)                 │
└─────────────────────────────────────────────────────────┘
```

### 3.1 새로 만들 파일

```
src/conversations/
├─ __init__.py
├─ schemas.py          # Conversation, Turn, Signal, InventionCandidate, ImportPlan
├─ adapters.py         # 입력 형식별 → Conversation 변환
├─ chunking.py         # 턴 단위 청크 분할
├─ parser.py           # ConversationParser (map/reduce 오케스트레이션)
├─ prompts.py          # map/reduce 프롬프트 + JSON 스키마
└─ import_service.py   # ImportPlan → 기존 서비스 호출해서 저장

src/ui/pages/conversation_import.py   # 3단계 UI

tests/test_conversation_adapters.py
tests/test_conversation_chunking.py
tests/test_conversation_parser.py
tests/test_conversation_import.py
tests/e2e/test_conversation_import_flow.py
```

### 3.2 기존 파일 수정 (최소)

| 파일 | 변경 | 이유 |
|---|---|---|
| `src/ai/base.py` | `AIProvider` Protocol에 메서드 2개 추가 | map/reduce 호출용 |
| `src/ai/mock_provider.py` | 위 2개 규칙 기반 구현 | 키 없이도 동작 |
| `src/ai/providers/anthropic_provider.py` | 위 2개 구현 | 실제 파싱 |
| `src/timeline/service.py` | `EVENT_LABELS`에 항목 추가 | 새 event_type 표시용 (스키마 변경 아님) |
| `src/similarity/tfidf.py` | 범용 `calculate_text_similarity(a, b)` 추가 | 발명↔발명 비교 (§8) |
| `src/attachments/service.py` | `ALLOWED_EXTENSIONS`에 `.md`, `.txt` 추가 | 원본 대화 저장 (§9.3) |
| `app.py` | 라우트 1개 추가 | 새 화면 |

**DB 스키마 변경 없음. 마이그레이션 없음.**

---

## 4. 입력 어댑터 — 입력은 여러 개, Parser는 하나

모든 어댑터의 출력은 동일한 `Conversation`이다. 그래서 나중에 입력
방식이 늘어나도 Parser와 그 뒤 파이프라인은 손대지 않는다.

```python
class ConversationAdapter(Protocol):
    name: str
    def can_handle(self, raw: str | bytes, filename: str | None) -> bool: ...
    def to_conversation(self, raw: str | bytes, filename: str | None) -> Conversation: ...
```

| 어댑터 | 입력 | 상태 |
|---|---|---|
| `PasteAdapter` | 브라우저에서 전체 복사한 평문 | **v1** |
| `MarkdownFileAdapter` | `.md` 내보내기 파일 | v1.1 |
| `PlainTextFileAdapter` | `.txt` | v1.1 |
| `HtmlExportAdapter` | `.html` 내보내기 | v1.2 |
| `ChatGptExportAdapter` | ChatGPT `conversations.json` | v2 |
| `ClaudeExportAdapter` | Claude 내보내기 | v2 |
| `UrlAdapter` | 대화 공유 링크 | v2 (§4.1) |

### 4.1 URL 입력에 대한 사전 검토

요청하신 대로 구조는 대비하되, v1에서는 만들지 않는다. 실제로 막히는
지점을 미리 적어 둔다.

- ChatGPT/Claude 공유 링크는 **로그인 세션이 있어야 열리는 경우가 많다.**
  공개 공유 링크만 가져올 수 있고, 그것도 서비스가 HTML 구조를 바꾸면
  즉시 깨진다.
- 서버가 외부 네트워크로 나가야 한다 — 지금 InventOS는 특허 API를
  제외하면 외부 호출이 없고, 사용자의 발명 데이터는 로컬에만 있다.
  이 성질을 깨는 결정이므로 별도 판단이 필요하다.
- 따라서 `UrlAdapter`는 "HTML을 받아온 뒤 `HtmlExportAdapter`에 넘기는
  얇은 껍데기"로만 설계한다. 파싱 로직은 재사용하고, 네트워크 부분만
  추가된다.

### 4.2 턴 분리 (PasteAdapter의 핵심 난제)

브라우저에서 CTRL+A/CTRL+C 하면 화자 표시가 일정하지 않다. 실제로 나오는
형태는 대략 이렇다.

```
You said:
...
ChatGPT said:
...
```

```
나
...
Claude
...
```

전략은 **다단계 폴백**이다.

1. 알려진 화자 마커 정규식으로 시도
   (`You said:` / `ChatGPT said:` / `사용자` / `나` / `Claude` 등)
2. 실패하면 빈 줄 2개 이상으로 블록 분리 후, 블록 길이/문체 휴리스틱으로
   추정 (사용자 턴은 대체로 짧고 물음표로 끝남)
3. 그것도 실패하면 **화자 분리를 포기하고 전체를 하나의 흐름으로 처리한다.**
   화자를 몰라도 순서는 알 수 있으므로 Timeline 생성은 여전히 가능하다.

> 화자 분리 실패는 오류가 아니다. 정확도가 조금 떨어질 뿐이며,
> 사용자에게 "화자를 구분하지 못했습니다 — 결과 정확도가 낮을 수 있습니다"
> 라고 안내만 한다.

---

## 5. 중간 표현 (schemas.py)

```python
@dataclass
class Turn:
    index: int                 # 0부터. 대화 내 순서 = 시간축
    speaker: str               # "user" | "assistant" | "unknown"
    text: str

@dataclass
class Conversation:
    turns: list[Turn]
    source: str                # "paste" | "markdown" | ...
    title_hint: str = ""       # 대화 제목이 있으면
    speaker_detection_failed: bool = False

    @property
    def full_text(self) -> str: ...
    def char_count(self) -> int: ...


SIGNAL_TYPES = (
    "idea_introduced",   # 새 아이디어가 처음 등장
    "idea_changed",      # 방식이 바뀜 (레이저 → 금속핀)
    "component_added",   # 요소 추가 (그래핀 추가)
    "problem_raised",    # 문제/한계 지적
    "experiment_planned",# 실험 제안
    "constraint_found",  # 제약 발견
)

@dataclass
class Signal:
    """대화 한 구간에서 뽑아낸 '발명적으로 의미 있는 사건' 하나."""
    turn_index: int            # 몇 번째 턴에서 나왔는지 = 순서 보존의 핵심
    signal_type: str
    topic: str                 # 클러스터링용 주제어 (예: "TGV 홀 가공")
    summary: str               # 한 줄 요약
    detail: str = ""

@dataclass
class InventionCandidate:
    title: str
    signals: list[Signal]              # turn_index 오름차순
    structured: InventionReviewResult  # 기존 dataclass 재사용 (§7)
    experiments: list[ExperimentInput] # 기존 dataclass 재사용
    tags: list[str]
    maturity: MaturityRating
    missing_info: list[str]
    # 중복 검사 결과 (파싱 후 채워짐)
    similar_to_invention_id: str | None = None
    similarity_score: float = 0.0

@dataclass
class MaturityRating:
    idea: int          # 0~5
    experiment: int    # 0~5
    patent_ready: int  # 0~5
    reason: str = ""

@dataclass
class ImportPlan:
    """아직 DB에 아무것도 쓰지 않은 상태의 '가져오기 계획'."""
    conversation: Conversation
    candidates: list[InventionCandidate]
    parse_warnings: list[str]
    ai_calls_made: int
    provider_name: str
```

`InventionCandidate.structured`가 기존 `InventionReviewResult`를 그대로
쓰는 것이 중요하다. 필드가 이미 발명노트 항목과 1:1로 맞춰져 있고
(`problem` / `existing_method` / `limitations` / `core_idea` /
`working_principle` / `differentiation` / `expected_effects` /
`implementation` / `experiment_plan` / `patent_keywords`), "일부만 반영"
로직과 `STRUCTURED_RESULT_SCHEMA`를 그대로 재사용할 수 있다.

---

## 6. Parser — map/reduce

### 6.1 왜 map/reduce인가

"수십~수백 번 대화"는 수십만 토큰이 될 수 있다. 통째로 한 번에 보내면
컨텍스트 초과로 실패하거나, 성공해도 비용이 크고 중간 내용이 뭉개진다.

더 중요한 이유가 있다. **한 번에 요약하면 발전 과정이 사라진다.**
LLM은 긴 입력을 요약할 때 최종 상태로 수렴시키는 경향이 있어서,
"레이저 → 그래핀 추가 → 금속핀으로 변경"이 그냥 "금속핀 방식"으로
납작해진다. 이 기능의 존재 이유가 바로 그 과정인데 말이다.

청크별로 나눠서 처리하면 **각 신호가 자기 `turn_index`를 달고 나오기
때문에 순서가 구조적으로 보존된다.** Timeline이 사후 추론이 아니라
파싱의 부산물로 자연히 얻어진다.

### 6.2 청크 분할 (chunking.py)

```python
def split_into_chunks(
    conversation: Conversation,
    target_chars: int = 12_000,   # 대략 4~6K 토큰
    overlap_turns: int = 1,       # 경계에서 맥락이 끊기지 않게
) -> list[ConversationChunk]
```

- **턴 경계에서만 자른다.** 문장 중간에서 자르면 맥락이 깨진다.
- 한 턴이 `target_chars`보다 길면 그 턴만 단독 청크로 둔다 (강제 분할 안 함).
- 인접 청크는 턴 1개를 겹쳐서 경계 신호를 놓치지 않는다.

### 6.3 map 단계 — 청크별 신호 추출

각 청크마다 AI 호출 1회. 출력은 `Signal` 배열의 JSON.

```
[프롬프트 요지]
아래는 발명 관련 대화의 일부다 (턴 {start}~{end}).
이 구간에서 "발명적으로 의미 있는 사건"만 뽑아라.
- 새 아이디어 등장 / 방식 변경 / 요소 추가 / 문제 제기 / 실험 제안 / 제약 발견
- 각 사건마다: 몇 번째 턴인지, 어떤 주제(topic)인지, 한 줄 요약
- 잡담·인사·코드 설명 등 발명과 무관한 내용은 제외
- 없으면 빈 배열
```

**부분 실패 허용.** 13개 청크 중 7번이 실패해도 나머지 12개 결과로
계속 진행하고, `parse_warnings`에 기록한다. 기존
"AI 실패해도 발명 데이터에는 영향 없음" 원칙과 같은 태도다.

### 6.4 reduce 단계 — 신호 → 발명 후보

모든 청크의 신호를 모으면 (보통 수십~수백 개) 이건 원본 대화보다 훨씬
작다. 이제 한 번에 처리할 수 있다.

```
[프롬프트 요지]
아래는 하나의 대화에서 시간 순으로 추출한 신호 목록이다.
1) 같은 발명에 속하는 신호끼리 묶어라 (TGV / 분리막 / 프랙탈 구조는 별개 발명)
2) 각 묶음에 발명 제목을 붙여라
3) 각 묶음이 실제로 하나의 발명인지, 아니면 한 발명의 하위 논의인지 판단하라
```

주제 수가 많으면 (신호 200개 초과 등) reduce도 2단계로 나눈다.
호출 횟수는 보통 1회, 최대 3회.

### 6.5 후보별 구조화

발명 후보마다, 그 후보에 속한 신호들만 모아서 AI 호출 1회.
출력은 **기존 `STRUCTURED_RESULT_SCHEMA` 그대로**다. 즉 이 단계는
사실상 기존 "AI로 검토하기 → 아이디어 정리"와 같은 일을, 입력만
대화 신호로 바꿔서 하는 것이다. 새 스키마를 만들 필요가 없다.

동시에 같은 호출에서 성숙도(`MaturityRating`)와 부족한 정보
(`missing_info`)도 함께 받는다 — 별도 호출로 나누면 비용만 2배가 된다.

### 6.6 Timeline 조립 (AI 호출 없음)

여기가 이 기능의 핵심 가치인데, **AI를 추가로 부르지 않는다.**
후보에 속한 신호를 `turn_index` 오름차순으로 정렬하면 그게 곧 Timeline이다.

```
signals (정렬됨)
  turn 3   idea_introduced   "레이저로 유리에 홀 가공"
  turn 27  problem_raised    "열 손상으로 크랙 발생"
  turn 41  component_added   "그래핀 열확산층 추가"
  turn 88  idea_changed      "금속핀 선배열 방식으로 전환"
  turn 95  experiment_planned "핀 직경별 성형 테스트"
        ↓ 그대로 InventionEvent 6개로 저장
```

### 6.7 호출 횟수 요약

| 단계 | 호출 수 |
|---|---|
| map | 청크 수 (N) |
| reduce | 1~3 |
| 후보별 구조화 | 발명 후보 수 (M) |
| Timeline | 0 |
| **합계** | **N + M + (1~3)** |

12만 자 대화 = 청크 10개, 발명 후보 3개 → 약 14회 호출.

---

## 7. 발명노트 필드 매핑

`InventionReviewResult` → `Invention` 매핑은 **이미 존재하는
`src/ai/review.py`의 `PARTIAL_APPLY_FIELDS` 매핑을 그대로 쓴다.**
새로 정의하지 않는다.

| 구조화 필드 | Invention 필드 |
|---|---|
| `problem` | `problem_to_solve` |
| `existing_method` | `conventional_method` |
| `limitations` | `conventional_problems` |
| `core_idea` | `core_principle` |
| `working_principle` | `operating_principle` |
| `differentiation` | `differentiation` |
| `expected_effects` | `expected_effects` |
| `implementation` | `implementation_method` |
| `experiment_plan` | `experiment_notes` |
| `patent_keywords` | `review_notes` + Tag |

제목은 후보의 `title`을 쓰고, 비어 있으면 기존
`generate_title()` 폴백을 그대로 탄다.

---

## 8. 중복 검사와 기존 발명 업데이트

### 8.1 유사도 계산

기존 `src/similarity/tfidf.py`를 재사용한다. 다만 현재 함수는
`calculate_similarity(invention_text, patent_title, patent_abstract)`로
특허 비교 전용 시그니처라, 범용 함수를 하나 추가한다.

```python
def calculate_text_similarity(text_a: str, text_b: str) -> float:
    """0~100. 기존 calculate_similarity()는 이 함수를 호출하도록 정리."""
```

이건 기존 동작을 바꾸지 않는 최소 리팩터링이다 (기존 테스트가 그대로
통과해야 한다).

AI 호출 없이 동작하므로 **API 키가 없어도 중복 검사는 항상 작동한다.**

### 8.2 판정과 사용자 선택

각 후보를 기존 발명 전체(휴지통 제외)와 비교해서 최고 점수를 찾는다.

| 유사도 | 기본 제안 |
|---|---|
| 85% 이상 | "기존 발명의 후속 아이디어입니다" → **파생으로 연결** 제안 |
| 60~85% | "비슷한 발명이 있습니다" → 사용자가 선택 |
| 60% 미만 | 신규 발명으로 생성 |

사용자가 고를 수 있는 것은 3가지다.

1. **새 발명으로 생성** — `InventionService.create()`
2. **기존 발명의 파생으로 생성** — `InventionService.create_child()`
   (부모/자식 양쪽 Timeline이 이미 자동으로 기록된다)
3. **기존 발명에 내용 추가** — `AIResultService.create_draft()`로 넣고,
   사용자가 상세 화면에서 "반영"을 눌러야 본문이 바뀐다

> 3번이 중요하다. 가져오기가 기존 발명 본문을 **직접 덮어쓰지 않는다.**
> 기존 "AI 결과는 사용자가 반영을 눌러야 본문에 들어간다"는 원칙을
> 그대로 지킨다.

---

## 9. 저장 매핑 (import_service.py)

선택된 후보 하나를 저장할 때, 기존 서비스만 호출한다.

```python
# 전부 하나의 트랜잭션 안에서 (run_and_rerun)
invention = InventionService(session).create(...)        # 또는 create_child()
TagService(session).add_tags(invention.id, candidate.tags)
for exp in candidate.experiments:
    ExperimentService(session).create(invention.id, exp)
for signal in candidate.signals:                         # Timeline
    TimelineService(session).log(invention.id, _event_type(signal), ...)
AIResultService(session).create_draft(...)               # 파싱 결과 원본 보존
AttachmentService(session).save(...)                     # 대화 원문 (§9.3)
```

### 9.1 Timeline event_type

`InventionEvent.event_type`은 자유 문자열이고 `EVENT_LABELS`는 표시용
사전일 뿐이므로, **스키마 변경 없이** 항목만 추가하면 된다.

```python
"conversation_imported":   "AI 대화에서 가져옴"
"idea_introduced":         "아이디어 최초 등장"
"idea_changed":            "아이디어 방식 변경"
"component_added":         "구성 요소 추가"
"problem_raised":          "문제점 발견"
"experiment_planned":      "실험 제안"
"constraint_found":        "제약 조건 발견"
```

각 이벤트의 `meta_json`에 `{"turn_index": 41, "source": "conversation_import"}`를
넣어 두면 나중에 원본 대화의 어느 지점인지 되짚을 수 있다.

### 9.2 Revision

가져오기로 **기존 발명을 수정하는 경우에만** 사전 스냅샷을 남긴다.
신규 생성은 남길 이전 상태가 없으므로 만들지 않는다.
(기존 `AIResultService.apply()`가 이미 이렇게 동작한다)

### 9.3 원본 대화 보존

원본은 반드시 남긴다 — InventOS의 "원본을 덮어쓰지 않는다" 원칙의 연장이다.

**방식**: 대화 전문을 `.md` 파일로 만들어
`AttachmentService.save(invention_id, "conversation_20260727.md", ...)`,
카테고리는 `참고자료`.

- DB가 아니라 디스크에 저장되므로 대화가 수백 KB여도 DB가 부풀지 않는다.
- 기존 백업(전체 데이터 ZIP)에 자동으로 포함된다.
- 첨부파일 무결성 검사 대상에도 자동으로 포함된다.

**필요한 변경**: `ALLOWED_EXTENSIONS`에 `.md`, `.txt` 추가.
현재 목록은 png/jpg/jpeg/pdf/wav/mp3/m4a/ogg/webm/mp4/mov 뿐이라
텍스트 파일이 막힌다.

추가로 파싱 결과 자체는 `AIResultService.create_draft(
kind="conversation_import", structured_content=...)`로 저장해서,
사용자가 나중에 "AI가 뭘 어떻게 해석했는지" 확인할 수 있게 한다.

---

## 10. Mock Provider 정책

이게 걸려 있는 이유: 지금 InventOS는 **API 키가 없어도 모든 기능이
동작한다**는 성질이 있고, E2E 테스트도 전부 Mock으로 돈다. 이 기능이
실제 AI 없이 아무것도 못 하면 그 성질이 깨지고 E2E도 못 쓴다.

**결정: Mock은 규칙 기반으로 "구조적으로 유효하지만 얕은" 결과를 낸다.**

| 단계 | Mock 동작 |
|---|---|
| 신호 추출 | 턴 앞부분 문장을 뽑아 `idea_introduced` 신호 생성 (턴 N개당 1개) |
| 클러스터링 | 전부 1개 후보로 묶음 (여러 발명 분리는 안 함) |
| 구조화 | 첫 사용자 턴 → `core_idea`, 물음표 문장 → `problem` 등 단순 규칙 |
| 태그 | 빈도 상위 명사형 토큰 |
| 성숙도 | 대화 길이/실험 언급 여부 기반 고정 규칙 |
| 부족한 정보 | 비어 있는 구조화 필드를 그대로 나열 |

그리고 UI에 명확히 표시한다.

> ⚠️ 현재 Mock AI로 동작 중입니다. 대화 분석 품질이 크게 떨어집니다.
> 실제 결과를 보려면 `.env`에 `ANTHROPIC_API_KEY`를 설정하세요.

이렇게 하면 (a) 키 없이도 전체 흐름을 눌러볼 수 있고, (b) E2E 테스트가
네트워크 없이 돌고, (c) 사용자가 품질 차이를 오해하지 않는다.

---

## 11. 첨부파일 자동 연결 — 명세 수정 필요

요청서에는 "대화 안에 이미지/PDF/표가 있으면 자동으로 첨부 후보로
등록"이 있는데, **v1의 붙여넣기 방식으로는 불가능하다.**

브라우저에서 CTRL+A/CTRL+C를 하면 클립보드에 텍스트만 담긴다.
이미지는 따라오지 않는다. Streamlit이 받는 것도 텍스트 문자열이다.

실현 가능한 범위로 나누면 이렇다.

| 항목 | v1 (붙여넣기) | v1.1 (파일 가져오기) |
|---|---|---|
| 표(마크다운 테이블) | ✅ 텍스트로 보존됨 | ✅ |
| 이미지 | ❌ 불가능 | ✅ `.html`/내보내기에 포함 시 |
| PDF | ❌ 불가능 | ✅ |
| 이미지가 "있었다"는 사실 | ⚠️ 자리표시자 텍스트가 남으면 감지 가능 | ✅ |

**v1 대안**: 대화에 이미지 자리표시자가 감지되면 가져오기 완료 후
안내만 한다.

> 대화에 이미지 3개가 있었던 것으로 보입니다. 붙여넣기로는 이미지를
> 가져올 수 없습니다 — 발명 상세 화면에서 직접 첨부해 주세요.

---

## 12. UI 흐름

기존 화면은 건드리지 않고 새 화면 하나를 추가한다. 진입점은 홈의
버튼 1개 + 상단 내비게이션.

### 1단계 — 붙여넣기

```
📋 AI 대화 가져오기

ChatGPT나 Claude에서 대화 전체를 복사(CTRL+A → CTRL+C)한 뒤
아래에 붙여넣으세요(CTRL+V).

┌────────────────────────────────┐
│ (큰 텍스트 영역)                 │
└────────────────────────────────┘

붙여넣은 분량: 약 124,000자 (턴 87개)
예상 AI 호출: 약 14회 · 예상 소요: 1~2분
현재 Provider: anthropic / claude-sonnet-5

            [ 분석 시작 ]
```

**분량과 예상 호출 수를 먼저 보여주는 것이 중요하다.** 사용자가
비용/시간을 모른 채 큰 작업을 시작하지 않게 한다.

### 2단계 — 후보 검토 (아직 DB에 아무것도 안 씀)

```
발명 후보 3개를 찾았습니다.

☑ 1. 유리 기판 TGV 홀 형성 방법
     성숙도  아이디어 ★★★★☆  실험 ★★☆☆☆  특허준비 ★★★☆☆
     Timeline 6단계 · 실험 2건 · 태그 7개
     ⚠️ 기존 발명 INV-2026-00012와 유사도 94%
        ○ 새 발명으로 생성
        ● 기존 발명의 파생으로 연결   ← 기본 선택
        ○ 기존 발명에 내용 추가(검토 후 반영)
     [ 상세 보기 ▾ ]

☑ 2. 그래핀 열확산층 적용 분리막
     ...

☐ 3. 프랙탈 구조 방열판          ← 사용자가 제외함
     ...

            [ 선택한 항목 가져오기 ]
```

### 3단계 — 결과

가져온 발명 목록 + 각각 열기 버튼. 부족한 정보 제안은 발명 상세 화면의
기존 "AI 검토 결과" 영역에 들어가므로 별도 화면이 필요 없다.

### 12.1 긴 작업 처리

분석은 수십 초~수 분이 걸린다. Streamlit은 스크립트가 동기 실행되므로
그동안 화면이 멈춘다.

**v1 방침**: `st.progress`로 청크 진행률을 갱신하며 동기 실행한다.
백그라운드 스레드 + 폴링은 구조가 복잡해지고 세션 상태 관리가 까다로워
v1 범위에서 제외한다. 대신 분석 시작 전에 예상 시간을 명시한다.

---

## 13. 오류 처리

| 상황 | 동작 |
|---|---|
| 붙여넣기가 비었거나 너무 짧음 (< 200자) | 분석 시작 버튼 비활성 + 안내 |
| 화자 분리 실패 | 경고만 표시하고 계속 진행 (§4.2) |
| map 청크 일부 실패 | 성공한 청크로 계속, `parse_warnings`에 기록 |
| map 전부 실패 | 오류 표시, **DB에 아무것도 쓰지 않음** |
| reduce 실패 | 후보 1개(전체를 한 발명으로)로 폴백 |
| 구조화 실패 | 원문 보존 + `parse_error` 기록 (기존 `coerce_review_result` 방식 그대로) |
| 저장 중 실패 | 트랜잭션 전체 롤백 — 발명만 반쯤 생기는 일 없음 |
| API 키 없음 | Mock으로 동작 + 품질 경고 (§10) |

기존 원칙 그대로: **AI 관련 실패가 기존 발명 데이터를 훼손하지 않는다.**

---

## 14. 테스트 계획

### 단위 테스트 (AI 호출 없음 — Mock 또는 스텁)

```
test_conversation_adapters.py
  - ChatGPT 형식 화자 분리
  - Claude 형식 화자 분리
  - 한국어 화자 마커
  - 화자 마커 없는 평문 → speaker_detection_failed=True, 턴은 여전히 생성
  - 빈 입력 / 공백만 / 200자 미만

test_conversation_chunking.py
  - 턴 경계에서만 잘림
  - 한 턴이 target보다 길면 단독 청크
  - overlap이 실제로 겹침
  - 턴 1개짜리 대화

test_conversation_parser.py
  - 신호가 turn_index 순으로 정렬됨
  - map 일부 실패해도 나머지로 계속 + warning 기록
  - map 전부 실패 → 예외, DB 미변경
  - reduce 실패 → 단일 후보 폴백
  - 여러 주제 → 여러 후보 분리 (스텁 Provider로)

test_conversation_import.py
  - 후보 → Invention/Tag/Experiment/Timeline 전부 생성
  - Timeline이 신호 순서대로 저장됨
  - 파생 연결 시 부모/자식 양쪽 Timeline 기록
  - "기존 발명에 추가"는 본문을 직접 바꾸지 않음 (AIResult만 생성)
  - 저장 중 실패 시 전체 롤백 (발명/태그/실험 아무것도 안 남음)
  - 원본 대화가 첨부파일로 저장됨
  - 중복 검사: 유사 발명 탐지 / 무관한 발명 미탐지
```

### E2E

```
tests/e2e/test_conversation_import_flow.py
  - 대화 붙여넣기 → 분석 → 후보 선택 → 가져오기 → 상세 화면 도달 (Mock)
  - 후보 일부만 선택하면 선택한 것만 생성됨
  - 빈 입력으로 분석 시도 시 오류 안내
```

### 회귀

기존 267개 + E2E 9개가 **전부 그대로 통과해야 한다.**
특히 `calculate_similarity` 리팩터링과 `ALLOWED_EXTENSIONS` 변경이
기존 테스트를 깨지 않는지 확인한다.

---

## 15. 구현 단계

각 단계가 끝날 때마다 전체 테스트가 통과해야 한다.

| 단계 | 내용 | 이 단계에서 되는 것 |
|---|---|---|
| 1 | schemas + PasteAdapter + chunking | 대화를 턴/청크로 쪼갤 수 있다 (AI 없음) |
| 2 | Mock Provider의 map/reduce 구현 | 키 없이 전체 파이프라인이 돈다 |
| 3 | ConversationParser (map/reduce 오케스트레이션) | ImportPlan이 나온다 |
| 4 | import_service (기존 서비스로 저장) | DB에 실제로 들어간다 |
| 5 | UI 3단계 | 사람이 쓸 수 있다 |
| 6 | Anthropic Provider 구현 | 실제 품질이 나온다 |
| 7 | 중복 검사 + 기존 발명 연결 | 파생/추가가 된다 |
| 8 | 성숙도 + 부족한 정보 | 제안 기능 완성 |
| 9 | E2E + 문서 | 릴리스 가능 |

1~5단계까지만 해도 Mock으로 동작하는 완결된 흐름이 된다.
6단계 전까지는 실제 AI 없이 개발/테스트가 가능하다.

---

## 16. 결정이 필요한 사항

구현 착수 전에 정해야 하는 것들.

1. **대화 원문을 어디에 저장할 것인가**
   §9.3은 첨부파일(.md)을 권장한다. 대신 `ALLOWED_EXTENSIONS` 변경이
   필요하다. DB 컬럼에 넣는 대안도 있지만 대화가 크면 DB가 부푼다.

2. **분량 상한을 둘 것인가**
   50만 자 대화를 붙여넣으면 청크 40개 = AI 호출 45회다. 상한(예: 30만 자)을
   두고 초과분은 잘라낼지, 경고만 하고 진행할지.

3. **분석 결과를 임시 저장할 것인가**
   2단계(후보 검토)에서 브라우저를 새로고침하면 분석 결과가 날아간다.
   기존 `DraftStore`(`data/drafts.json`)에 `ImportPlan`을 직렬화해 두면
   복구할 수 있지만, 크기가 커질 수 있다.

4. **여러 발명 후보를 한 번에 가져올 때 서로 연결할 것인가**
   같은 대화에서 나온 3개 발명이 서로 관련 있을 수 있다.
   부모-자식으로 묶을지, 태그만 공유할지, 아무 관계도 만들지 않을지.

5. **비용 표시를 어디까지 할 것인가**
   호출 횟수만 보여줄지, 토큰 추정치/예상 비용까지 보여줄지.

---

## 17. 이 기능이 지켜야 할 것

InventOS는 "가장 많은 기능"이 아니라 **"가장 빠르게 아이디어를 기록하고
발전시킬 수 있는 프로그램"**이다.

Conversation Import는 이 철학에 정확히 맞는다 — 이미 AI와 다 논의해 놓고
다시 손으로 옮겨 적는 시간을 없애는 기능이기 때문이다.

다만 그래서 다음을 지켜야 한다.

- **붙여넣기 → 가져오기까지 클릭 3번을 넘지 않는다.** 설정 화면이
  복잡해지면 이 기능의 존재 이유가 사라진다.
- **완벽한 분석보다 빠른 분석이 낫다.** 틀린 부분은 사용자가 상세
  화면에서 고치면 된다. 90% 정확도로 10초가, 99% 정확도로 5분보다 낫다.
- **자동으로 덮어쓰지 않는다.** 기존 발명 본문을 바꾸는 것은 항상
  사용자가 "반영"을 눌렀을 때만이다.
