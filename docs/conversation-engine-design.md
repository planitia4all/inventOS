# InventOS Conversation Engine / Idea Evolution 설계

> **상태: 설계 초안 (미구현)**
> 대상 버전: `0.5.0` — `0.4.0` 정식 릴리스(UAT 완료) 이후 별도 `0.5.0-dev` 브랜치에서 착수 여부를 결정한다.
> 이 문서는 코드가 아니다. `0.4.0-rc.1` 코드 동결에 영향을 주지 않는다.
> 이전 `conversation-import-design.md`를 대체하며 그 내용을 전부 흡수했다.

## 목차

| § | 내용 | § | 내용 |
|---|---|---|---|
| 1 | [기능 목적](#1-기능-목적) | 14 | [질문·사건·이미지 연결](#14-질문사건이미지-연결) |
| 2 | [사용자 시나리오](#2-사용자-시나리오) | 15 | [인포그래픽 화면 구조](#15-인포그래픽-화면-구조) |
| 3 | [새 발명 생성 흐름](#3-새-발명-생성-흐름) | 16 | [DB 변경 최소안](#16-db-변경-최소안) |
| 4 | [기존 발명 업데이트 흐름](#4-기존-발명-업데이트-흐름) | 17 | [향후 확장 DB안](#17-향후-확장-db안) |
| 5 | [N차 대화 누적 흐름](#5-n차-대화-누적-흐름) | 18 | [서비스 계층 구조](#18-서비스-계층-구조) |
| 6 | [원문 보존 구조](#6-원문-보존-구조) | 19 | [AI Prompt 및 JSON 스키마](#19-ai-prompt-및-json-스키마) |
| 7 | [대화 비교 및 병합 규칙](#7-대화-비교-및-병합-규칙) | 20 | [UI Wireframe](#20-ui-wireframe) |
| 8 | [중복·충돌 처리](#8-중복충돌-처리) | 21 | [Migration 영향](#21-migration-영향) |
| 9 | [Idea Element 개념](#9-idea-element-개념) | 22 | [테스트 전략](#22-테스트-전략) |
| 10 | [키워드 정규화](#10-키워드-정규화) | 23 | [0.5.0 MVP 범위](#23-050-mvp-범위) |
| 11 | [중요도 계산 방식](#11-중요도-계산-방식) | 24 | [후속 버전 범위](#24-후속-버전-범위) |
| 12 | [Source Traceability](#12-source-traceability) | 25 | [예상 위험 및 대응](#25-예상-위험-및-대응) |
| 13 | [Evolution Timeline](#13-evolution-timeline) | — | [부록: 파싱 파이프라인](#부록-파싱-파이프라인-mapreduce) |

---

## 1. 기능 목적

### 1.1 문제

실제 발명은 한 번의 대화로 완성되지 않는다.

```
1차 대화 → 기본 아이디어
  (며칠~몇 달)
2차 대화 → 새로운 방법
  (실험 수행 → 문제 발견)
3차 대화 → 문제 해결 시도
  (이미지·사건에서 영감)
4차 대화 → 방향 전환
  ...
N차 대화 → 비용·재료·구조 변경
```

지금 InventOS는 이 축적을 담지 못한다. 최종 상태만 저장하고 **어떻게
거기에 도달했는지**를 잃어버린다.

### 1.2 InventOS가 기록해야 하는 것

```
무엇을 생각했는가          → 아이디어 요소
왜 그 생각이 발생했는가     → 발생 계기
무엇을 보고 떠올렸는가      → 이미지·사건·논문 연결
어떤 질문을 했는가          → 질문 자산
어떤 방법이 제안되었는가    → 후보 방법 목록
무엇이 실패했는가          → 폐기된 접근법
어떤 방법이 변경되었는가    → 변화 기록
무엇이 반복해서 중요했는가  → 중요도 점수
최종 아이디어의 진화 경로   → Evolution Timeline
```

### 1.3 한 문장 정의

> 대화·질문·이미지·사건·실험과 영감의 흔적을 연결하여 **아이디어의
> 탄생과 진화를 기록하는** 발명 지식 시스템.

### 1.4 설계 원칙 (모든 결정의 기준)

1. 원문은 삭제하거나 덮어쓰지 않는다.
2. AI 분석과 사용자가 승인한 내용을 구분한다.
3. 새로운 대화는 기존 발명을 자동 변경하지 않는다.
4. 사용자가 항목별로 반영한다.
5. 모든 변경은 Revision과 Timeline에 남긴다.
6. 중복 표현은 통합하되 원문은 보존한다.
7. 최종안이 하나가 아닐 수 있다.
8. 질문·실패·사건·이미지도 아이디어 자산이다.
9. 모든 주요 내용은 출처를 추적할 수 있어야 한다.
10. 단순 키워드 빈도보다 의미와 변화가 중요하다.

**이 문서에서 새로 명시하는 원칙**

11. **"빠른 기록"을 훼손하지 않는다.** 이 기능은 전부 새 탭 안에
    격리한다. 홈 → 빠른 기록 → 저장 경로는 지금과 100% 동일하게
    유지한다. (§25 R1 — 가장 큰 위험)
12. **AI 없이도 앱이 죽지 않는다.** Mock에서도 구조적으로 유효한
    결과를 낸다.

---

## 2. 사용자 시나리오

### S1. 첫 대화로 발명 만들기

박 연구원이 ChatGPT와 TGV 홀 가공을 두 시간 논의했다. 대화를 전체
복사해 `AI 대화 가져오기`에 붙여넣는다. 발명 후보 3개(TGV / 분리막 /
프랙탈 방열판)가 나온다. 앞의 2개만 체크해 가져온다. 발명 2건이
생성되고, 각각 Timeline에 아이디어 변화 6단계가 들어 있다.

### S2. 며칠 뒤 후속 대화 누적

닷새 뒤 그래핀 섬유 아이디어가 떠올라 다시 AI와 대화한다.
**발명 상세 → 대화 기록 탭 → `+ 새 대화 추가`**에 붙여넣는다.
기본 선택은 `현재 발명에 후속 대화로 추가`다.

```
새로 추가 3   ☑ 그래핀 섬유 전도성 비아
수정 1        ☑ 금속핀 삽입 → 그래핀 섬유 장력 유지
강화 2        ☑ 레이저 → 펨토초 + 선택적 식각으로 구체화
폐기 1        ☐ 방사선 직접 천공 (현실성 부족)
충돌 1        ⚠ 기존 "고온 성형 중 삽입" ↔ 신규 "상온 후가공"
중복 5        (본문에 이미 있음 — 반영 안 함)
```

체크한 항목만 반영된다. Revision 1건 + Timeline 6건이 생긴다.

### S3. 실험 실패 후 3차 대화

실험에서 분리막 접합면이 떨어졌다. 실험 기록을 남기고 그 실패를 들고
다시 AI와 대화한 뒤 3차 대화를 누적한다. Evolution Timeline에
`실험 실패 → 기계적 얽힘 구조 검토`가 인과로 연결되어 보인다.

### S4. 3개월 뒤 통합 분석

대화 12건이 쌓였다. `아이디어 지도` 탭에서 본다.

```
핵심 개념     그래핀 섬유(92) · 장력 유지(88) · TGV(85)
최근 새 개념  냉각 수축 고정 (대화 #11)
미해결 질문   7개
후보 방법     5개 (유망 2 · 검토중 2 · 제외 1)
```

### S5. 특허 출원 준비

변리사가 "이 핵심 아이디어의 근거가 뭐냐"고 묻는다. 핵심 아이디어 옆
`출처`를 누르면:

```
- 대화 #2 사용자 발언 14  "실처럼 당겨서 유리에 박으면..."
- 대화 #3 사용자 발언 6
- 스케치 IMG-00012
- 실험 EXP-00004
```

원문 문장까지 즉시 확인된다.

---

## 3. 새 발명 생성 흐름

```
붙여넣기
  ↓ 어댑터 (형식 무관 → Conversation)
턴 분리 · 청크 분할
  ↓ map: 청크별 신호 추출            [AI × N]
신호 목록 (turn_index 보존)
  ↓ reduce: 발명 후보로 클러스터링    [AI × 1~3]
발명 후보 M개
  ↓ 후보별 구조화 + 성숙도 + 질문     [AI × M]
  ↓ 중복 검사 (TF-IDF — AI 불필요)
ImportPlan   ← 여기까지 DB에 아무것도 쓰지 않음
  ↓ 사용자 선택
저장 (단일 트랜잭션)
```

파이프라인 상세는 [부록](#부록-파싱-파이프라인-mapreduce) 참고.

저장 시 호출하는 것은 **전부 기존 서비스**다.

```python
inv = InventionService(s).create(...)          # 또는 create_child()
TagService(s).add_tags(inv.id, candidate.tags)
for exp in candidate.experiments:
    ExperimentService(s).create(inv.id, exp)
for sig in candidate.signals:                  # Evolution Timeline
    TimelineService(s).log(inv.id, sig.event_type, meta={...})
AttachmentService(s).save(inv.id, "conversation_001.md", raw_bytes)
# + ConversationImport 레코드 1건 (§16)
```

---

## 4. 기존 발명 업데이트 흐름

새 대화를 기존 발명에 붙일 때는 **다시 요약하는 것이 아니라 차이를
분석한다.**

```
                ┌─ 기존 발명 본문 (구조화 필드 10개)
비교 입력 3종 ──┼─ 과거 대화 누적 요약 (rolling summary, 원문 아님)
                └─ 새 대화에서 추출한 신호
                          ↓  [AI × 1~2]
                  ChangeProposal 목록
                          ↓
                  ① 중복 필터 (TF-IDF)
                  ② 신뢰도 정렬
                          ↓
                  사용자 항목별 승인
                          ↓
        Revision 1건 → 본문 반영 → Timeline N건
```

**과거 대화 원문을 다시 보내지 않는 것이 핵심이다.** 12차 대화 시점에
원문 11개를 전부 컨텍스트에 넣으면 비용과 토큰이 폭발한다. 대신 누적
요약 1개만 유지한다 (§5.2).

### 4.1 사용자 선택지

새 대화를 붙여넣을 때 항상 4가지 중 고른다.

| 선택 | 동작 | 기본값 조건 |
|---|---|---|
| 새로운 발명으로 생성 | `InventionService.create()` | 홈에서 시작했을 때 |
| **현재 발명에 후속 대화로 추가** | 차이 분석 → 항목별 반영 | **발명 상세에서 시작했을 때** |
| 현재 발명의 파생 아이디어로 생성 | `create_child()` | 유사도 60~85%일 때 제안 |
| 다른 기존 발명에 연결 | 발명 선택 후 차이 분석 | 유사도 85%+ 다른 발명 발견 시 제안 |

### 4.2 유사도 기반 자동 제안

TF-IDF로 계산하므로 **API 키 없이도 항상 동작한다** (§18.2).

| 유사도 | 기본 제안 |
|---|---|
| 85% 이상 | "기존 발명의 후속입니다" → 해당 발명에 누적 |
| 60~85% | "비슷한 발명이 있습니다" → 파생 생성 제안 |
| 60% 미만 | 신규 발명 생성 |

---

## 5. N차 대화 누적 흐름

### 5.1 회차 관리

각 대화는 발명별로 1부터 증가하는 `sequence_no`를 갖는다.
`ConversationImport` 레코드가 보관하는 정보:

| 항목 | 출처 |
|---|---|
| 회차 (`sequence_no`) | 발명별 자동 증가 |
| 입력일 (`imported_at`) | 시스템 시각 |
| 실제 대화일 (`conversation_date`) | 사용자 입력 (선택) |
| 출처 (`source`) | `chatgpt` / `claude` / `other` — 자동 추정 + 사용자 수정 |
| 제목 (`title`) | AI 생성 또는 사용자 입력 |
| 원문 길이 (`char_count`) | 계산 |
| 주요 주제 | AI (분석 JSON) |
| 새로 등장한 개념 | 차이 분석 결과 |
| 이전 대비 변화 | 차이 분석 결과 |
| 본문 반영 여부 (`status`) | 미반영 / 일부 반영 / 반영 완료 |
| 연결된 Revision | `revision_id` |
| 연결된 Timeline Event | 이벤트의 `meta_json` 역참조 |

### 5.2 누적 요약 (rolling summary)

N차 대화를 분석할 때 컨텍스트에 넣는 것:

```
[현재 발명 구조화 필드]   약 2~4K 토큰
[누적 요약 v(N-1)]        약 1~2K 토큰   ← 원문 아님
[새 대화 신호 목록]        약 1~3K 토큰
                          ─────────────
                          총 5~9K 토큰 (대화 수와 무관하게 일정)
```

반영이 끝나면 누적 요약을 v(N)으로 갱신한다. **대화가 50개가 되어도
컨텍스트 크기는 늘지 않는다.**

누적 요약은 `InventionAIResult(kind="rolling_summary")` 한 건을
갱신하며 유지한다.

### 5.3 통합 분석

발명에 연결된 모든 대화를 종합해 보여준다. **AI 재호출 없이** 저장된
분석 JSON들을 Python에서 집계한다.

```
발명 A 통합 분석
  총 대화 12 · 총 원문 48,320자
  최초 2026-07-25 · 최근 2026-10-03
  주요 변경 8회 · 실험 3건 · 파생 4건

  현재 핵심 아이디어    (최신 본문)
  발전 과정             (Evolution Timeline)
  주요 결정             (decision 신호)
  폐기된 접근법          (deprecated 상태 요소)
  남아 있는 후보         (candidate 목록)
  해결되지 않은 문제     (미해결 질문)
  다음 검토 과제         (missing_info 합집합)
  실험 필요 항목         (needs_experiment 질문)
  특허 검토 필요 항목    (needs_patent_search 질문)
```

전부 집계이므로 즉시 렌더링되고 비용이 0이다.

---

## 6. 원문 보존 구조

### 6.1 5계층 분리

```
① 원본 대화        디스크 (.md 첨부파일)                절대 불변
② AI 분석 결과     ConversationImport.analysis_json     불변 (재분석 시 새 레코드)
③ 사용자 승인 내용  Invention 본문 필드                  가변
④ 변경 전 스냅샷    InventionRevision                    불변
⑤ 변경 사건        InventionEvent                       불변
```

### 6.2 원문 저장 위치: 디스크

원문은 `AttachmentService.save()`로 `.md` 파일에 저장한다.

- 대화가 수백 KB여도 **DB가 부풀지 않는다**
- 기존 전체 데이터 ZIP 백업에 자동 포함
- 기존 첨부파일 무결성 검사 대상에 자동 포함
- 파일명이 FTS 색인에 들어가 검색됨

`ConversationImport.raw_attachment_id`가 이 파일을 가리킨다.

> **필요한 변경**: `ALLOWED_EXTENSIONS`에 `.md`, `.txt` 추가.
> 현재는 png/jpg/jpeg/pdf/wav/mp3/m4a/ogg/webm/mp4/mov만 허용되어
> 텍스트 파일이 막힌다.

### 6.3 재분석 가능성

원문이 그대로 있으므로 나중에 더 좋은 모델로 **재분석**할 수 있다.
재분석은 기존 `ConversationImport`를 수정하지 않고 새 레코드를 만든다
(`reanalysis_of`로 원본을 가리킴). 원문 첨부파일은 공유한다.

---

## 7. 대화 비교 및 병합 규칙

### 7.1 변화 6분류

| 분류 | 정의 | 예 | 기본 선택 |
|---|---|---|---|
| `added` 신규 | 이전에 없던 개념 | 그래핀 섬유 전도성 비아 | ☑ |
| `modified` 수정 | 기존 개념이 바뀜 | 금속핀 → 그래핀 섬유 장력 | ☑ |
| `strengthened` 강화 | 기존이 구체화됨 | 레이저 → 펨토초 + 선택적 식각 | ☑ |
| `deprecated` 폐기 | 제외하기로 함 | 방사선 직접 천공 (현실성 부족) | ☐ |
| `conflict` 충돌 | 기존과 모순 | 고온 성형 중 삽입 ↔ 상온 후가공 | ☐ (선택 강제) |
| `undecided` 미결정 | 후보로 남음 | 방법 A/B/C 병존 | ☐ (후보 목록으로) |

**기본 선택 정책**: 안전한 것(추가·수정·강화)만 기본 체크한다.
기존 내용을 지우는 것(폐기)과 사람 판단이 필요한 것(충돌·미결정)은
반드시 사용자가 명시적으로 켜야 한다.

### 7.2 ChangeProposal

```python
@dataclass
class ChangeProposal:
    change_type: str            # added | modified | strengthened |
                                # deprecated | conflict | undecided
    target_field: str           # Invention 필드명 (PARTIAL_APPLY_FIELDS 기준)
    proposed_text: str
    current_excerpt: str = ""   # 바뀌는 기존 내용 (modified/conflict)
    rationale: str = ""         # 왜 이렇게 판단했는지
    confidence: int = 0         # 0~100
    sources: list[SourceRef] = field(default_factory=list)
    conflict_options: list[str] = field(default_factory=list)
```

### 7.3 반영 방식 — 교체가 아니라 이어붙임

`modified` / `strengthened`도 기존 텍스트를 **교체하지 않고 이어붙인다.**
원칙 1(원문 불변)과 기존 `AIResultService.apply()` 동작에 맞춘다.

```
[기존]
금속핀을 유리 성형 전에 배열한다.

[반영 후]
금속핀을 유리 성형 전에 배열한다.

(대화 #3에서 변경) 금속핀 대신 그래핀 섬유를 장력을 유지한 채
관통 배치하는 방식으로 전환.
```

교체가 정말 필요하면 사용자가 상세 화면에서 직접 편집한다 — 그때도
Revision이 남는다.

---

## 8. 중복·충돌 처리

### 8.1 중복 판정 3단계

대화가 쌓이면 같은 말이 다르게 반복된다.

```
"그래핀은 전도성이 있다"
"그래핀 섬유가 전도체 역할을 한다"
"그래핀 실을 비아로 사용할 수 있다"
```

```
1단계  정확 포함 검사    proposed_text가 기존 필드에 그대로 있는가
       → duplicate                      (AI 불필요, 기존 apply() 로직)

2단계  TF-IDF 유사도     기존 필드를 문장 단위로 쪼개 최고 유사도
       ≥ 0.80    → duplicate
       0.55~0.80 → strengthened 후보 (기존 항목 확장 제안)
       < 0.55    → 3단계로              (AI 불필요)

3단계  AI 판정          위에서 애매한 것만
       → added / modified / conflict
```

**1·2단계가 AI 없이 동작하는 것이 중요하다.** 중복 방어의 대부분을
결정론적으로 처리하므로 Mock에서도 본문 오염이 막히고 AI 호출도 줄어든다.

### 8.2 처리 규칙

| 상황 | 원문 | 본문 | 사용자 안내 |
|---|---|---|---|
| 신규 정보 | 보존 | 추가 제안 | ☑ |
| 다른 표현 (중복) | 보존 | **추가 안 함** | "중복 5건" 접어서 표시 |
| 기존의 구체화 | 보존 | 기존 항목 확장 제안 | ☑ |
| 기존과 충돌 | 보존 | 선택 강제 | ⚠ 양쪽 원문 나란히 |
| 과거 폐기 내용 재등장 | 보존 | 재검토 알림 | 🔄 "대화 #4에서 제외했던 내용입니다" |

마지막 항목이 중요하다. **폐기 이력을 기억하지 못하면 사용자가 같은
막다른 길을 반복한다.** `deprecated` 상태 요소가 새 대화에 다시 나오면
폐기 사유와 함께 알린다.

### 8.3 충돌 UI

```
⚠ 충돌 1건 — 어느 쪽을 유지할지 선택하세요

  ○ 기존 유지   고온 성형 중 그래핀 섬유 삽입
                출처 대화#2 사용자 발언 14  [원문]

  ○ 신규 채택   상온에서 후가공으로 섬유 삽입
                출처 대화#5 사용자 발언 3   [원문]

  ● 둘 다 후보로 보존    ← 기본값
                → 후보 방법 목록에 2개 등록, 본문은 변경 없음
```

기본값이 "둘 다 보존"인 이유는 원칙 7이다. **InventOS가 임의로 하나를
고르지 않는다.**

---

## 9. Idea Element 개념

### 9.1 왜 키워드로는 부족한가

빈도만 세면 `방법`, `가능`, `문제`, `유리` 같은 단어가 상위에 온다.
발명의 핵심이 아니다. 필요한 건 **의미 역할이 붙은 요소**다.

### 9.2 6종 분류

| 종류 | 코드 | 예 |
|---|---|---|
| 기술 요소 | `tech` | 레이저, 그래핀 섬유, 유리 기판, 금속핀, 진공 챔버 |
| 문제 요소 | `problem` | 홀 붕괴, 열 손상, 정렬 불량, 도전성 저하 |
| 해결 원리 | `principle` | 장력 유지, 선택적 식각, 열팽창 차이, 기계적 고정 |
| 사건·계기 | `trigger` | 실험 실패, 특허 발견, 사진 관찰, 타 산업 참고 |
| 판단·결정 | `decision` | 채택, 보류, 폐기, 실험 필요, 특허 검색 필요 |
| 증거 | `evidence` | 실험 결과, 측정값, 이미지, 논문, 특허 |

### 9.3 데이터 표현 (MVP는 테이블 없음)

```python
@dataclass
class IdeaElement:
    name: str                  # 대표 이름 (정규화 후)
    kind: str                  # tech | problem | principle | trigger | decision | evidence
    synonyms: list[str]
    status: str = "active"     # active | deprecated | candidate
    first_seen: SourceRef | None = None
    mentions: list[SourceRef] = field(default_factory=list)
    importance: int = 0        # 0~100 (§11)

@dataclass
class IdeaRelation:
    subject: str               # "그래핀 섬유"
    predicate: str             # "제공한다"
    object: str                # "전도성"
    sources: list[SourceRef] = field(default_factory=list)
```

발명 단위 집계 결과는 `InventionAIResult(kind="idea_elements")` 1건에
`structured_content`로 보관하고, 새 대화가 들어올 때마다 갱신한다.

> **왜 테이블이 아닌가**: 단일 사용자 로컬 앱에서 발명당 대화 10~20개,
> 요소 50~200개 규모다. Python 집계로 충분히 빠르고, 테이블 3개를
> 도입하면 마이그레이션·정합성·삭제 전파를 전부 관리해야 한다.
> **교차 발명 질의가 필요해지는 시점**("그래핀이 나오는 모든 발명")에
> 테이블로 승격한다 (§17).

---

## 10. 키워드 정규화

### 10.1 문제

```
TGV / Through Glass Via / 유리 관통 비아 / 글라스 비아 / 유리 비아
그래핀 실 / 그래핀 섬유 / Graphene fiber / 전도성 섬유
```

전부 따로 세면 중요도가 분산되어 실제 핵심이 하위로 밀린다.

### 10.2 3단계 정규화

```
1단계  결정론적 정규화 (AI 불필요)
       대소문자·공백·하이픈 통일, 전각/반각 통일,
       내장 약어 사전 (TGV ↔ Through Glass Via)

2단계  AI 병합 후보 제안
       표기가 다르지만 같은 개념으로 보이는 쌍 + 신뢰도 + 근거 원문

3단계  사용자 승인   ← 자동 병합하지 않음
       ☑ 그래핀 실 + Graphene fiber → "그래핀 섬유"
       ☐ 전도성 섬유                 → 별개 유지
```

**자동 병합하지 않는 이유**: "전도성 섬유"는 그래핀 섬유의 상위 개념일
수도, 동의어일 수도 있다. 잘못 병합하면 되돌리기 어렵고, **특허 문서
작성 시 용어 구분이 결정적으로 중요하다.**

### 10.3 저장

- 승인된 대표 개념만 `Tag`로 생성 (기존 `TagService.add_tags()`)
- 동의어 매핑은 `idea_elements` JSON의 `synonyms`
- 미승인 병합 후보는 다음 대화 때 다시 제안

---

## 11. 중요도 계산 방식

### 11.1 8개 요소

| 요소 | 기호 | 계산 | AI 필요 |
|---|---|---|---|
| 등장 빈도 | `f` | `log(1+언급수) / log(1+최대언급수)` | ✗ |
| 대화 확산도 | `s` | `등장 대화 수 / 전체 대화 수` | ✗ |
| 지속성 | `p` | `(최근회차 - 최초회차 + 1) / 전체회차` | ✗ |
| 최근성 | `r` | `0.5 ^ (최근등장 이후 경과회차 / 3)` | ✗ |
| 사용자 강조 | `u` | `사용자 발언 언급 / 전체 언급` | ✗ |
| 결정 영향도 | `d` | `modified`/`decision` 변화 연루 횟수 (정규화) | ✗ |
| 연결도 | `c` | `IdeaRelation` 차수 (정규화) | △ |
| 증거 보유 | `e` | 연결된 실험·이미지·특허 수 (상한 3, 정규화) | ✗ |

**8개 중 7개가 AI 없이 계산된다.** `c`만 AI가 만든 관계에 의존하며,
없으면 0으로 둔다. 즉 **Mock에서도 중요도가 의미 있게 동작한다.**

### 11.2 가중치

```
importance = 100 × (
    0.15·f + 0.15·s + 0.10·p + 0.15·r +
    0.20·u + 0.10·d + 0.05·c + 0.10·e
)
```

`u`(사용자 강조)에 가장 큰 가중치를 준다. **AI가 길게 설명한 것보다
사용자가 반복해서 말한 것이 실제 발명의 핵심일 가능성이 높다**는
가정이다. 이 가정은 UAT에서 검증하고 조정해야 한다.

가중치는 `src/conversations/scoring.py` 상수 한 곳에 두어 쉽게 튜닝한다.

### 11.3 표시 — 점수만 보여주지 않는다

```
그래핀 섬유                            중요도 92
  언급 18회 · 대화 6개 · 최근 3일 전
  사용자 강조 높음 · 실험 2 · 이미지 3
  [근거 보기]
```

점수만 보여주면 신뢰하기 어렵다. **왜 92인지 분해해서 보여준다.**

---

## 12. Source Traceability

### 12.1 SourceRef

```python
@dataclass
class SourceRef:
    kind: str                    # conversation | experiment | attachment | patent | manual
    conversation_id: str = ""    # ConversationImport.id
    sequence_no: int = 0         # 대화 #3
    turn_index: int = -1         # 대화 내 몇 번째 발언
    speaker: str = ""            # user | assistant
    excerpt: str = ""            # 원문 발췌 (최대 200자)
    ref_id: str = ""             # experiment_id / attachment_id / patent_id
```

### 12.2 어디에 붙는가

| 대상 | 저장 위치 |
|---|---|
| `ChangeProposal` | 제안 JSON |
| `IdeaElement.mentions` | `idea_elements` JSON |
| 반영된 본문 항목 | 반영 시 Timeline event `meta_json` |
| Timeline 이벤트 | `meta_json.sources` |

### 12.3 본문 항목의 출처 역조회

본문 텍스트 자체에는 출처 표시를 넣지 않는다(가독성 훼손). 대신 반영
시점의 Timeline 이벤트가 `{target_field, proposed_text_hash, sources}`를
보관하고, UI가 필드별로 역조회한다.

```
핵심 아이디어                                    [출처 4]
그래핀 섬유를 장력 상태로 유리 성형체에 관통 배치한다.

  ▸ 대화 #2 사용자 발언 14  "실처럼 당겨서 유리에..."  [원문]
  ▸ 대화 #3 사용자 발언 6                             [원문]
  ▸ 스케치 IMG-00012                                  [열기]
  ▸ 실험 EXP-00004                                    [열기]
```

이 구조는 **특허 명세서 작성 시 착상 시점과 근거를 증명**하는 데 직접
쓰인다 — 이 기능의 장기 가치 중 가장 큰 부분이다.

---

## 13. Evolution Timeline

### 13.1 기존 Timeline과의 관계 — 같은 테이블, 다른 레이어

> **요청하신 검토 항목에 대한 답: 새 테이블을 만들지 않고
> `InventionEvent`를 재사용한다.**

`InventionEvent`는 이미 `event_type`(자유 문자열), `title`,
`description`, `meta_json`, `occurred_at`을 갖고 있다. 필요한 건
**레이어 구분**뿐이다.

```python
meta_json = {"layer": "idea", "turn_index": 41, "sources": [...]}
                      ^^^^^^
```

| 레이어 | `layer` | 내용 | 화면 |
|---|---|---|---|
| 시스템 | `system` (기본/없음) | 생성·수정·상태변경·첨부·삭제 | Timeline 탭 |
| 아이디어 | `idea` | 아이디어 등장·변경·폐기·실험 제안 | 아이디어 지도 탭 |

기존 이벤트는 `layer`가 없으므로 `system`으로 간주된다 —
**기존 데이터가 그대로 유효하고 마이그레이션이 불필요하다.**

### 13.2 새 event_type

`EVENT_LABELS`에 항목만 추가한다 (스키마 변경 아님).

```python
"conversation_imported":  "AI 대화 가져옴"
"idea_introduced":        "아이디어 최초 등장"
"idea_changed":           "아이디어 방식 변경"
"idea_strengthened":      "아이디어 구체화"
"idea_deprecated":        "접근법 폐기"
"idea_conflicted":        "상충하는 방향 발견"
"component_added":        "구성 요소 추가"
"problem_raised":         "문제점 발견"
"question_raised":        "질문 제기"
"question_resolved":      "질문 해결"
"experiment_planned":     "실험 제안"
"constraint_found":       "제약 조건 발견"
"trigger_recorded":       "아이디어 발생 계기 기록"
```

### 13.3 표시

```
2026-07-25  레이저로 유리 기판에 직접 홀을 만드는 초기 아이디어
            대화 #1 · 사용자 발언 3

2026-07-25  방사선 침투 원리를 이용한 비접촉 가공 가능성 검토
            대화 #1 · 사용자 발언 27              ⊘ 이후 폐기

2026-07-26  그래핀 섬유를 유리 성형 중 관통시키는 방식 제안
            대화 #2 · 사용자 발언 14              ★ 채택

2026-08-03  냉각 수축 차이를 이용한 고정 방식 추가
            대화 #3 · 실험 EXP-00004에서 파생
```

---

## 14. 질문·사건·이미지 연결

### 14.1 질문 (Question)

사용자가 던진 질문 자체가 발명의 출발점이다.

> "방사선처럼 투과하는 원리를 이용해 유리에 기공을 만들 수 없는가?"

map 단계에서 `question_raised` 신호로 추출한다. **화자가 `user`인
의문문만** 대상으로 한다 (AI가 되묻는 것은 제외).

```python
@dataclass
class Question:
    text: str
    status: str        # unresolved | partially_resolved | resolved |
                       # needs_experiment | needs_patent_search | deferred
    source: SourceRef
    resolved_by: SourceRef | None = None
```

상태 판정은 reduce 단계에서 AI가 한다 — "이 질문이 이후 대화에서
답변되었는가". 발명 상세에 집계 표시:

```
미해결 질문 7개   실험 필요 3 · 특허 검색 필요 2 · 보류 2
```

### 14.2 사건 (발생 계기)

> 실험 중 분리막 접합면이 분리됨 → 기계적 얽힘 구조 검토 필요

> **요청하신 검토 항목에 대한 답: 별도 의미 계층은 필요 없다.**
> `InventionEvent` + `meta_json`이 이미 인과 정보를 담을 수 있고,
> 새 테이블은 삭제 전파·백업·마이그레이션 부담만 늘린다.

```python
meta_json = {
    "layer": "idea",
    "trigger_kind": "experiment_failure",
    "affected_elements": ["세라믹 직접 접합"],
    "created_elements": ["기계적 얽힘 구조"],
    "deprecated_elements": ["세라믹 표면 직접 접합"],
    "next_actions": ["얽힘 구조 시험편 제작"],
    "sources": [{"kind": "experiment", "ref_id": "EXP-00004"}],
}
```

발생 계기 선택 항목:
`AI 대화 / 실험 결과 / 실패 / 현장 문제 / 사진 / 영상 / 논문 / 특허 /
제품 / 자연 현상 / 다른 산업 / 고객 요구 / 개인 경험 / 갑작스러운 생각 / 기타`

### 14.3 이미지 → 아이디어

이미지는 첨부파일이 아니라 **아이디어의 근거**다.

| 항목 | 저장 |
|---|---|
| 이 이미지에서 무엇을 봤는가 | `Attachment.notes` (신규 컬럼, §16.3) |
| 어떤 생각이 떠올랐는가 | 〃 |
| 어떤 발명 요소와 연결되는가 | `idea_elements` JSON의 `SourceRef(kind="attachment")` |
| 관련 대화 / 실험 / 키워드 | 〃 |

OCR·비전 분석은 범위 밖이다. **이미지와 아이디어 요소의 관계만**
설계하고 사람이 직접 메모한다.

---

## 15. 인포그래픽 화면 구조

복잡한 그래프를 처음부터 만들지 않는다. 4단계로 나누고 **1~3단계만
0.5.0에서** 구현한다.

### 1단계 — 핵심 카드 (MVP 필수)

```
┌─────────────────┬─────────────────┬─────────────────┐
│ 핵심 기술 요소   │ 핵심 문제        │ 핵심 해결 원리   │
│ 그래핀 섬유 92  │ 홀 붕괴    78   │ 장력 유지   88  │
│ 유리 기판   85  │ 열 손상    71   │ 열팽창 차이 64  │
│ 펨토초레이저 79 │ 정렬 불량  52   │ 선택적 식각 61  │
├─────────────────┴─────────────────┴─────────────────┤
│ 최근 등장한 새 개념   냉각 수축 고정 (대화 #11)       │
│ 미해결 질문           7개  [보기]                    │
└──────────────────────────────────────────────────────┘
```

### 2단계 — 키워드 (가능하면)

`st.bar_chart` 하나로 충분하다. 상위 키워드 / 사용자 발언 기준 핵심어 /
최근 증가 / 더 이상 안 쓰이는 키워드 4개 목록.

### 3단계 — 시간 흐름 (가능하면)

```
대화 #1  레이저 · 유리 · TGV
   ↓
대화 #2  그래핀 · 섬유 · 장력
   ↓
대화 #3  금형 · 관통 · 냉각
```

### 4단계 — 관계도 (후속 버전)

```
그래핀 섬유
├─ 제공한다   → 전도성
├─ 필요로 한다 → 장력 유지
├─ 형성한다   → 관통 구조
└─ 관련       → 냉각 후 비아
```

자유 그래프(node-link)가 아니라 **들여쓰기 목록**으로 시작한다.
그래프 라이브러리를 추가하면 의존성이 늘고 모바일에서 읽기 어렵다.
목록은 둘 다 해결한다.

---

## 16. DB 변경 최소안

### 16.1 원칙

- 새 테이블은 **1개만**
- 새 컬럼은 **전부 nullable 추가**
- 기존 컬럼 삭제·타입 변경 **없음**
- 기존 DB를 열었을 때 **아무 동작 없이 그대로 열려야 함**

### 16.2 새 테이블 1개

```python
class ConversationImport(Base):
    """붙여넣은 대화 한 건과 그 분석 결과.

    원문 자체는 여기 없다 — Attachment(.md)에 있고 raw_attachment_id로
    가리킨다. 이 테이블은 '어떤 대화가 언제 어느 발명에 들어왔고
    무엇을 바꿨는가'의 인덱스 역할만 한다.
    """
    __tablename__ = "conversation_imports"

    id: str                        # uuid
    invention_id: str              # FK → inventions.id, ondelete="CASCADE"
    sequence_no: int               # 발명별 1,2,3...
    source: str                    # chatgpt | claude | other
    title: str
    char_count: int
    turn_count: int
    conversation_date: date | None # 실제 대화일 (사용자 입력)
    imported_at: datetime
    raw_attachment_id: str | None  # FK → attachments.id (원문 .md)
    analysis_json: dict | None     # 신호·요소·질문·변화 제안 전부
    status: str                    # 분석됨 | 일부반영 | 반영완료 | 보관됨
    revision_id: str | None        # FK → invention_revisions.id
    reanalysis_of: str | None      # 재분석이면 원본 import id
    provider: str
    model: str | None
```

**이 테이블 하나가 필요한 이유**: 대화 목록·회차 정렬·반영 상태 조회가
기본 기능인데, 이걸 `InventionAIResult`의 JSON 안에 넣으면 **목록
화면조차 JSON 파싱으로** 만들어야 한다. 반면 요소·질문·변화 같은
**분석 결과는 조회 축이 아니므로** JSON으로 충분하다.

### 16.3 새 컬럼 2개 (권장, 없어도 동작)

| 테이블 | 컬럼 | 타입 | 용도 |
|---|---|---|---|
| `attachments` | `notes` | TEXT NULL | 이미지 메모 (§14.3) |
| `inventions` | `idea_candidates` | JSON NULL | 후보 방법 + 상태 (§17 요구) |

둘 다 없어도 MVP는 동작한다(각각 §14.3 기능 제외, 후보 목록을
`InventionAIResult`로 대체). 하지만 비용이 거의 없고 표현이 훨씬 깔끔하다.

### 16.4 기존 구조 재사용 요약

| 요구사항 | 재사용 대상 | 신규 |
|---|---|---|
| 원문 보존 | `Attachment` (.md) | — |
| AI 분석 결과 | `ConversationImport.analysis_json` | 테이블 1 |
| 변경 전 스냅샷 | `InventionRevision` | — |
| 변경 사건 | `InventionEvent` + `meta.layer` | — |
| Evolution Timeline | 〃 (layer=idea 필터) | — |
| Idea Element | `InventionAIResult(kind="idea_elements")` | — |
| 누적 요약 | `InventionAIResult(kind="rolling_summary")` | — |
| 키워드 | `Tag` / `InventionTag` | — |
| 실험 | `Experiment` | — |
| 파생 관계 | `Invention.parent_invention_id` | — |
| 후보 방법 | `Invention.idea_candidates` | 컬럼 1 |
| 이미지 메모 | `Attachment.notes` | 컬럼 1 |

---

## 17. 향후 확장 DB안

아래는 **0.5.0에서 만들지 않는다.** 필요가 실제로 확인되면 승격한다.

| 승격 대상 | 승격 조건 (트리거) |
|---|---|
| `IdeaElement` | 발명을 가로지르는 질의가 필요할 때 ("그래핀이 나오는 모든 발명") |
| `IdeaElementMention` | 요소별 언급을 SQL로 집계해야 할 만큼 커질 때 (발명당 요소 500+) |
| `IdeaRelation` | 관계도를 그래프로 그리고 경로 탐색이 필요할 때 |
| `IdeaChange` | 변화 이력을 Timeline과 별도로 필터·검색해야 할 때 |
| `SourceReference` | 출처 역인덱스가 필요할 때 (특정 발언이 어느 항목들에 쓰였는지) |
| `ConversationMessage` | 턴 단위 검색·인용이 필요할 때 (지금은 .md 원문으로 충분) |
| `Tag.canonical_tag_id` | 전역 동의어 사전이 필요할 때 (지금은 발명 단위 매핑) |

**승격 방식**: 전부 additive다. JSON에 있던 데이터를 테이블로 옮기는
백필을 한 번 돌리면 되고, 그 시점까지 JSON이 정본이므로 손실이 없다.

> 이 "JSON 먼저, 테이블은 나중에" 전략의 근거는
> **분석 결과가 조회 축이 아니라 표시 대상**이라는 점이다.
> 조회 축(발명·대화 회차·태그)만 테이블로 두면 나머지는 지연시켜도 된다.

---

## 18. 서비스 계층 구조

### 18.1 새 파일

```
src/conversations/
├─ schemas.py     Conversation, Turn, Signal, SourceRef,
│                 ChangeProposal, IdeaElement, Question, ImportPlan
├─ adapters.py    입력 형식별 → Conversation (§18.3)
├─ chunking.py    턴 단위 청크 분할
├─ parser.py      map/reduce 오케스트레이션 → ImportPlan
├─ diff.py        기존 발명 vs 새 대화 → ChangeProposal[]
├─ dedup.py       중복 3단계 판정 (§8.1) — AI 불필요 부분
├─ elements.py    Idea Element 추출·정규화·병합
├─ scoring.py     중요도 8요소 + 가중치 상수
├─ prompts.py     프롬프트 + JSON 스키마
└─ service.py     ConversationService — 저장 오케스트레이션

src/ui/pages/conversation_import.py
```

### 18.2 계층 규칙 (기존 원칙 유지)

```
UI (streamlit)
   ↓ 호출만
ConversationService              ← 트랜잭션 경계
   ↓ 기존 서비스만 호출
InventionService / TimelineService / TagService /
ExperimentService / AttachmentService / AIResultService
   ↓
Repository → DB
```

- **Parser는 DB를 모른다.** 순수 함수에 가깝다(입력 `Conversation`,
  출력 `ImportPlan`) — 테스트가 쉽다.
- **ConversationService만 DB를 만진다.** 기존 서비스를 우회하지 않는다.
- 저장은 `run_and_rerun`으로 감싼 **단일 트랜잭션**이다.

**기존 코드 수정 (최소)**

| 파일 | 변경 |
|---|---|
| `src/ai/base.py` | `AIProvider` Protocol에 메서드 3개 추가 |
| `src/ai/mock_provider.py` | 규칙 기반 구현 (§19.5) |
| `src/ai/providers/anthropic_provider.py` | 실제 구현 |
| `src/timeline/service.py` | `EVENT_LABELS` 항목 추가 |
| `src/similarity/tfidf.py` | 범용 `calculate_text_similarity(a, b)` 추가 |
| `src/attachments/service.py` | `ALLOWED_EXTENSIONS`에 `.md`, `.txt` |
| `app.py` | 라우트 1개 |

### 18.3 어댑터 — 입력은 여러 개, Parser는 하나

```python
class ConversationAdapter(Protocol):
    name: str
    def can_handle(self, raw: str | bytes, filename: str | None) -> bool: ...
    def to_conversation(self, raw: str | bytes, filename: str | None) -> Conversation: ...
```

| 어댑터 | 입력 | 버전 |
|---|---|---|
| `PasteAdapter` | 브라우저 전체 복사 평문 | **0.5.0** |
| `MarkdownFileAdapter` | `.md` | 0.5.1 |
| `PlainTextFileAdapter` | `.txt` | 0.5.1 |
| `HtmlExportAdapter` | `.html` 내보내기 | 0.6.0 |
| `ChatGptExportAdapter` | `conversations.json` | 0.6.0 |
| `UrlAdapter` | 공유 링크 | 0.7.0 (§24.1) |

### 18.4 화자 분리 폴백

붙여넣기는 화자 표시가 일정하지 않다(`You said:` / `ChatGPT said:` /
`나` / `Claude` / 표시 없음).

```
1) 알려진 화자 마커 정규식
2) 실패 → 빈 줄 2개 이상 블록 분리 + 길이·문체 휴리스틱
          (사용자 턴은 대체로 짧고 의문문)
3) 실패 → 화자 분리 포기, 전체를 하나의 흐름으로 처리
```

3단계로 떨어져도 **순서(turn_index)는 알 수 있으므로 Timeline은 여전히
만들어진다.** 다만 `사용자 강조도`(§11) 계산이 불가능하므로 해당
가중치를 0으로 두고 나머지를 재정규화한다. 사용자에게는 "화자를
구분하지 못했습니다 — 정확도가 낮을 수 있습니다"라고 안내한다.

---

## 19. AI Prompt 및 JSON 스키마

### 19.1 AIProvider 인터페이스 확장

```python
def extract_signals(self, chunk_text: str, turn_range: tuple[int, int]) -> list[dict]: ...
def cluster_and_structure(self, signals: list[dict], context: str) -> dict: ...
def analyze_diff(self, current: dict, rolling_summary: str, signals: list[dict]) -> dict: ...
```

Mock / Anthropic 양쪽 모두 구현한다.

### 19.2 신호 추출 (map)

```
아래는 발명 관련 대화의 일부다 (턴 {start}~{end}).
이 구간에서 "발명적으로 의미 있는 사건"만 뽑아라.

대상: 새 아이디어 등장 / 방식 변경 / 요소 추가 / 문제 제기 /
      실험 제안 / 제약 발견 / 사용자의 질문 / 판단·결정
제외: 인사, 잡담, 코드 문법 설명, 일반 상식 설명

각 사건마다 반드시 채워라:
- turn_index: 몇 번째 발언에서 나왔는지 (필수)
- speaker: user 또는 assistant
- excerpt: 근거가 되는 원문 문장 (최대 200자, 그대로 인용)

없으면 빈 배열을 반환하라. 추측해서 만들어내지 마라.
```

```json
{
  "type": "object",
  "properties": {
    "signals": {"type": "array", "items": {
      "type": "object",
      "properties": {
        "turn_index": {"type": "integer"},
        "speaker": {"type": "string"},
        "signal_type": {"type": "string",
          "enum": ["idea_introduced","idea_changed","component_added",
                   "problem_raised","experiment_planned","constraint_found",
                   "question_raised","decision_made"]},
        "topic": {"type": "string"},
        "summary": {"type": "string"},
        "excerpt": {"type": "string"},
        "elements": {"type": "array", "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "kind": {"type": "string",
              "enum": ["tech","problem","principle","trigger","decision","evidence"]}
          },
          "required": ["name","kind"]
        }},
        "confidence": {"type": "integer"}
      },
      "required": ["turn_index","signal_type","topic","summary","excerpt","confidence"]
    }}
  },
  "required": ["signals"]
}
```

### 19.3 클러스터링 + 구조화 (reduce)

기존 `STRUCTURED_RESULT_SCHEMA`를 **그대로 재사용**하고 부가 정보만 감싼다.

```json
{
  "type": "object",
  "properties": {
    "candidates": {"type": "array", "items": {
      "type": "object",
      "properties": {
        "title": {"type": "string"},
        "signal_indices": {"type": "array", "items": {"type": "integer"}},
        "structured": {"$ref": "#/definitions/InventionReviewResult"},
        "maturity": {
          "type": "object",
          "properties": {
            "idea": {"type": "integer"},
            "experiment": {"type": "integer"},
            "patent_ready": {"type": "integer"},
            "reason": {"type": "string"}
          },
          "required": ["idea","experiment","patent_ready"]
        },
        "questions": {"type": "array", "items": {
          "type": "object",
          "properties": {
            "text": {"type": "string"},
            "status": {"type": "string",
              "enum": ["unresolved","partially_resolved","resolved",
                       "needs_experiment","needs_patent_search","deferred"]},
            "turn_index": {"type": "integer"}
          },
          "required": ["text","status","turn_index"]
        }},
        "missing_info": {"type": "array", "items": {"type": "string"}},
        "idea_candidates": {"type": "array", "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "status": {"type": "string",
              "enum": ["제안됨","검토 중","실험 필요","유망","보류","제외","채택"]},
            "note": {"type": "string"}
          },
          "required": ["name","status"]
        }}
      },
      "required": ["title","signal_indices","structured"]
    }}
  },
  "required": ["candidates"]
}
```

### 19.4 차이 분석 (기존 발명 업데이트)

```
[현재 발명 내용]         (구조화 필드 10개)
[지금까지의 대화 요약]    (누적 요약 — 원문 아님)
[새 대화에서 추출한 신호]

새 대화가 현재 발명 내용에 대해 무엇을 바꾸는지 분류하라.

added        이전에 전혀 없던 개념
modified     기존 개념이 다른 것으로 바뀜
strengthened 기존 개념이 더 구체화됨
deprecated   이전에 제안됐지만 이제 제외하기로 함
conflict     기존 내용과 모순되어 사람이 골라야 함
undecided    여러 방법이 후보로 남아 결론이 안 남

규칙:
- 이미 본문에 있는 내용을 다시 제안하지 마라 (표현만 다른 경우 포함)
- 각 항목에 반드시 근거 원문(excerpt)과 신뢰도를 붙여라
- 확신이 없으면 confidence를 낮게 주고 conflict/undecided로 분류하라
- 본문을 지우는 제안(deprecated)은 명확한 근거가 있을 때만 하라
```

```json
{
  "type": "object",
  "properties": {
    "changes": {"type": "array", "items": {
      "type": "object",
      "properties": {
        "change_type": {"type": "string",
          "enum": ["added","modified","strengthened",
                   "deprecated","conflict","undecided"]},
        "target_field": {"type": "string"},
        "proposed_text": {"type": "string"},
        "current_excerpt": {"type": "string"},
        "rationale": {"type": "string"},
        "confidence": {"type": "integer"},
        "sources": {"type": "array", "items": {
          "type": "object",
          "properties": {
            "turn_index": {"type": "integer"},
            "speaker": {"type": "string"},
            "excerpt": {"type": "string"}
          },
          "required": ["turn_index","excerpt"]
        }},
        "conflict_options": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["change_type","target_field","proposed_text","confidence","sources"]
    }},
    "merge_candidates": {"type": "array", "items": {
      "type": "object",
      "properties": {
        "canonical": {"type": "string"},
        "synonyms": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer"}
      },
      "required": ["canonical","synonyms","confidence"]
    }},
    "rolling_summary": {"type": "string"}
  },
  "required": ["changes","rolling_summary"]
}
```

### 19.5 Mock Provider 정책

API 키 없이도 전체 흐름이 돌아야 한다 (E2E 포함).

| 단계 | Mock 동작 |
|---|---|
| 신호 추출 | 턴 앞 문장 발췌, N턴당 1개 `idea_introduced`. 의문문은 `question_raised` |
| 요소 추출 | 빈도 상위 명사형 토큰을 `tech`로 |
| 클러스터링 | 전부 1개 후보 (여러 발명 분리 안 함) |
| 구조화 | 첫 사용자 턴 → `core_idea`, 의문문 → `problem` 등 단순 규칙 |
| 차이 분석 | TF-IDF 기반 `added`/`duplicate`만 (`conflict` 판정 안 함) |
| 중요도 | 8요소 중 7개 정상 계산, 연결도만 0 |

UI에 명시한다:

> ⚠️ Mock AI로 동작 중입니다. 대화 분석 품질이 크게 떨어집니다.
> 실제 결과를 보려면 `.env`에 `ANTHROPIC_API_KEY`를 설정하세요.

---

## 20. UI Wireframe

### 20.1 발명 상세 화면 재구성

현재는 expander 나열이다. 대화가 쌓이면 화면이 너무 길어지므로
`st.tabs`로 나눈다.

```
INV-2026-00012  유리 기판 TGV 홀 형성 방법          [아이디어 ▾] ★
────────────────────────────────────────────────────────────────
 개요 │ 발명 내용 │ 대화 기록 │ 아이디어 지도 │ 실험 │ 선행기술 │ Timeline │ 변경 이력 │ 첨부
────────────────────────────────────────────────────────────────
```

> **모바일 주의**: 탭 9개는 390px에서 가로 스크롤을 만든다 — 현재
> E2E가 금지하는 조건이다. 모바일에서는 `st.selectbox`로 섹션을 고르는
> 방식으로 대체한다 (기존 `layout.py` 모바일 CSS 패턴 확장).

### 20.2 대화 기록 탭

```
┌──────────────────────────────────────────────────────┐
│  + 새 대화 추가                                       │
├──────────────────────────────────────────────────────┤
│  대화 #4            2026-08-10          ✅ 반영 완료  │
│  새로운 그래핀 고정 방식 검토                          │
│  새 개념 3 · 수정 2 · 중복 5                          │
│  [분석 결과]  [원문]  [재분석]                        │
├──────────────────────────────────────────────────────┤
│  대화 #3            2026-07-30          ⚠️ 일부 반영  │
│  금형 및 장력 구조                                    │
│  새 개념 5 · 충돌 1 (미해결)                          │
│  [분석 결과]  [원문]  [남은 항목 반영]                 │
└──────────────────────────────────────────────────────┘
```

### 20.3 새 대화 추가 — 3단계

**1단계 붙여넣기**

```
ChatGPT나 Claude에서 대화 전체를 복사(CTRL+A → CTRL+C)해 붙여넣으세요.

┌────────────────────────────┐
│                            │
└────────────────────────────┘

분량 124,000자 · 턴 87개
예상 AI 호출 14회 · 예상 1~2분
Provider: anthropic / claude-sonnet-5

이 대화를 어떻게 처리할까요?
  ● 현재 발명에 후속 대화로 추가       ← 기본
  ○ 현재 발명의 파생 아이디어로 생성
  ○ 새로운 발명으로 생성
  ○ 다른 기존 발명에 연결

실제 대화일 (선택) [2026-08-10]

              [ 분석 시작 ]
```

분량과 예상 호출 수를 **먼저** 보여준다. 사용자가 비용을 모른 채 큰
작업을 시작하지 않게 한다.

**2단계 변경 검토** (아직 DB에 아무것도 안 씀)

```
대화 #4 분석 결과                신뢰도 낮은 항목 2개는 기본 해제됨

▼ 새로 추가 3
  ☑ 핵심 아이디어 ← 그래핀 섬유를 이용한 전도성 비아 형성    신뢰 94
     출처 대화#4 사용자 발언 12  "그래핀 실을 그대로..."  [원문]
  ☑ 실험 계획 ← 섬유 직경별 장력 시험                      신뢰 88
  ☐ 예상 효과 ← 공정 단계 30% 감소 예상                    신뢰 51 ⚠

▼ 수정 1
  ☑ 작동 원리   금속핀 삽입 → 그래핀 섬유 장력 유지          신뢰 91
     기존: "금속핀을 유리 성형 전에 배열한다"
     추가: "(대화 #4에서 변경) 금속핀 대신 그래핀 섬유를..."

▼ 강화 2   ☑ ☑

▼ 폐기 1
  ☐ 기존 방식에서 "방사선 직접 천공" 제외                   신뢰 76
     ⚠ 본문 내용을 지웁니다. 확인 후 체크하세요.

▼ 충돌 1  ⚠ 선택 필요
  기존: 고온 성형 중 섬유 삽입   [원문]
  신규: 상온 후가공 방식         [원문]
    ○ 기존 유지   ○ 신규 채택   ● 둘 다 후보로 보존

▼ 중복 5  (본문에 이미 있어 반영하지 않음)  [펼치기]

▼ 키워드 병합 제안 1
  ☑ 그래핀 실 + Graphene fiber → "그래핀 섬유"

              [ 선택한 8개 항목 반영 ]
```

**3단계 결과**

```
✅ 대화 #4를 반영했습니다.
   본문 6개 항목 변경 · Revision #7 생성 · Timeline 9건 추가
   원문은 conversation_004.md 로 보존되었습니다.

   [발명 내용 보기]  [아이디어 지도 보기]
```

### 20.4 아이디어 지도 탭

```
핵심 개념
┌────────────┬────────────┬────────────┐
│ 기술 요소   │ 문제        │ 해결 원리   │
│ 그래핀섬유92│ 홀 붕괴  78│ 장력유지 88│
│ 유리기판 85│ 열 손상  71│ 열팽창차 64│
└────────────┴────────────┴────────────┘

최근 새 개념   냉각 수축 고정 (대화 #11, 3일 전)

미해결 질문 7                                    [전체 보기]
  · 상온에서 장력을 유지할 방법이 있는가?     실험 필요
  · 그래핀 섬유의 접촉 저항은?                실험 필요
  · 유사 특허가 있는가?                       특허 검색 필요

후보 방법 5
  ★ 유망    D. 그래핀 섬유 관통 성형
  ★ 유망    B. 레이저 개질 + 식각
    검토중  C. 금속핀 삽입 성형
    보류    A. 레이저 직접 가공
    제외    E. 방사선 기반 구조 변경  (대화 #4에서 현실성 부족)

키워드 추이                                   [막대그래프]
발전 타임라인                                 [Evolution Timeline]
```

---

## 21. Migration 영향

### 21.1 변경 요약

| 항목 | 종류 | 위험 |
|---|---|---|
| `conversation_imports` 테이블 | 신규 테이블 | **없음** — `create_all()`이 자동 생성 |
| `attachments.notes` | nullable 컬럼 | 없음 — 기존 `_ADDED_COLUMNS` 메커니즘 |
| `inventions.idea_candidates` | nullable JSON | 없음 — 〃 |
| `EVENT_LABELS` 항목 | 표시용 dict | 없음 — 스키마 아님 |
| `ALLOWED_EXTENSIONS` 확장 | 상수 | 없음 |
| `calculate_text_similarity()` | 함수 추가 | 낮음 — 기존 함수가 이걸 호출하도록 정리 |

### 21.2 이 프로젝트에서 테이블 추가가 안전한 이유

`init_engine()`이 `Base.metadata.create_all()`을 먼저 호출하므로
**새 테이블은 마이그레이션 코드 없이 자동 생성된다.**
`run_migrations()`는 기존 테이블의 누락 컬럼만 채운다.

### 21.3 기존 DB 호환성

- 새 테이블 = 빈 테이블 → 기존 기능에 영향 없음
- 새 컬럼 = 전부 NULL → 기존 데이터 그대로
- 기존 `InventionEvent`는 `meta.layer`가 없음 → `system`으로 간주 (§13.1)
- **0.4.x DB를 0.5.0에서 열면 스키마만 확장되고 데이터는 그대로다.**
- 0.5.0 DB를 0.4.x에서 열면 새 테이블·컬럼을 무시하므로 열리기는 하지만
  대화 기록이 보이지 않는다. **다운그레이드는 지원하지 않는다**고 문서화한다.

### 21.4 마이그레이션 전 백업

기존 정책이 그대로 적용된다 — 스키마가 실제로 바뀌므로 SQLite 온라인
백업 API로 백업 + `PRAGMA integrity_check`를 거친 뒤에만 진행하고,
실패하면 중단한다.

---

## 22. 테스트 전략

### 22.1 계층별 비중

```
순수 함수 (AI·DB 불필요)         ← 가장 두껍게
  adapters / chunking / dedup / scoring / elements

서비스 (DB 필요, AI는 스텁)
  parser / diff / ConversationService

E2E (브라우저, Mock AI)
  붙여넣기 → 분석 → 승인 → 반영
```

### 22.2 단위 테스트

```
test_conversation_adapters.py
  ChatGPT / Claude / 한국어 화자 마커 분리
  마커 없는 평문 → speaker_detection_failed=True, 턴은 생성됨
  빈 입력 / 공백 / 200자 미만 → 거부
  코드 블록 안의 "You said:" 오탐 방지

test_conversation_chunking.py
  턴 경계에서만 분할
  긴 단일 턴은 강제 분할하지 않음
  overlap이 실제로 겹침
  턴 1개짜리 대화

test_conversation_dedup.py            ← AI 불필요, 가장 중요
  정확 포함 → duplicate
  유사도 0.85 → duplicate
  유사도 0.65 → strengthened 후보
  유사도 0.20 → AI 판정 대상
  폐기됐던 내용 재등장 → 재검토 플래그

test_conversation_scoring.py          ← AI 불필요
  8요소 각각의 경계값
  화자 미상일 때 user_emphasis 가중치 재정규화
  언급 0회 → 0점
  최근성 감쇠 곡선

test_conversation_elements.py
  대소문자·공백·전각 정규화
  내장 약어 사전 (TGV ↔ Through Glass Via)
  병합 후보 제안은 하되 자동 병합하지 않음

test_conversation_parser.py           ← 스텁 Provider
  신호가 turn_index 순으로 정렬됨
  map 일부 실패 → 나머지로 계속 + warning
  map 전부 실패 → 예외, DB 미변경
  reduce 실패 → 단일 후보 폴백
  여러 주제 → 여러 후보 분리

test_conversation_service.py          ← DB
  신규 발명: Invention/Tag/Experiment/Timeline 전부 생성
  Timeline이 신호 순서대로 저장됨 (layer=idea)
  기존 발명 업데이트: 승인한 항목만 반영
  미승인 항목은 본문에 안 들어감
  Revision은 1건만 (항목 6개 반영해도)
  중복 항목은 본문에 추가되지 않음
  충돌 "둘 다 보존" → 본문 불변 + 후보 목록 2건
  저장 중 실패 → 전체 롤백
  원문이 .md 첨부파일로 저장됨
  sequence_no가 발명별로 1,2,3 증가
  rolling_summary 갱신
  ConversationImport.status가 반영 결과에 맞게 변함
  발명 purge 시 대화 레코드도 삭제 (§25 R9)

test_conversation_traceability.py
  ChangeProposal의 sources가 반영 후 Timeline meta에 보존
  필드별 출처 역조회 정확성
```

### 22.3 E2E

```
tests/e2e/test_conversation_engine_flow.py
  1) 홈 → 붙여넣기 → 분석 → 후보 선택 → 발명 생성
  2) 상세 → 대화 기록 탭 → 새 대화 추가 → 항목 승인 → 반영 확인
  3) 승인 안 한 항목이 본문에 없는지
  4) 대화 기록 탭 회차 표시 (#1, #2)
  5) 아이디어 지도 탭 렌더링
  6) 모바일 390px 탭 대체 UI — 가로 스크롤 없음
```

### 22.4 회귀 (필수)

**기존 267개 단위 + 9개 E2E가 전부 그대로 통과해야 한다.**
특히 다음이 기존 동작을 깨지 않는지 확인:

- `calculate_similarity()` 리팩터링
- `ALLOWED_EXTENSIONS` 확장 (기존 확장자 거부 로직 유지)
- `st.tabs` 도입 후 기존 상세 화면 E2E 셀렉터
- 새 테이블 추가 후 기존 마이그레이션 테스트

### 22.5 AI 응답 픽스처

실제 API 없이 다양한 응답을 재현한다.

```
tests/fixtures/conversations/
├─ chatgpt_tgv_sample.txt      실제와 유사한 대화 샘플
├─ claude_format_sample.txt
├─ no_speaker_marker.txt
├─ signals_response.json       정상 map 응답
├─ signals_malformed.json      JSON 깨진 응답
└─ diff_with_conflict.json     충돌 포함 차이 분석
```

---

## 23. 0.5.0 MVP 범위

### 23.1 반드시 구현

| # | 항목 | 근거 |
|---|---|---|
| 1 | 새 대화 붙여넣기 (`PasteAdapter`) | 진입점 |
| 2 | 새 발명 / 기존 / 파생 / 다른 발명 선택 | §4.1 |
| 3 | 원문 독립 저장 (.md 첨부) | 원칙 1 |
| 4 | 기존 발명과 차이 분석 | §7 |
| 5 | 신규·수정·강화·폐기·충돌·중복 6분류 | §7.1 |
| 6 | 항목별 승인 반영 | 원칙 4 |
| 7 | Revision 생성 | 원칙 5 |
| 8 | Timeline 기록 (layer=idea) | 원칙 5 |
| 9 | 대화 회차 표시 | §5.1 |
| 10 | 핵심 키워드 및 Idea Element 추출 | §9 |
| 11 | 원문 출처 추적 (SourceRef) | 원칙 9 |
| 12 | 여러 대화 통합 요약 | §5.3 |
| 13 | 미해결 질문 추출 | §14.1 |

### 23.2 가능하면 구현

| 항목 | 비고 |
|---|---|
| 상위 키워드 카드 (§15 1단계) | 구현 쉽고 가치 높음 — 사실상 필수에 가깝다 |
| 대화별 새로 등장한 개념 | 차이 분석 부산물 |
| 키워드 막대그래프 (§15 2단계) | `st.bar_chart` 한 줄 |
| 아이디어 발전 타임라인 (§15 3단계) | Timeline 필터링만 |
| 후보 방법 목록 + 상태 | `inventions.idea_candidates` 필요 |
| 키워드 병합 승인 UI | 없으면 중복 키워드 누적 |
| 이미지 메모 (`attachments.notes`) | 컬럼 1개 |

### 23.3 제외

- 복잡한 관계 그래프 (node-link)
- 이미지 비전 분석 / OCR
- 대화 URL 자동 가져오기
- ChatGPT 계정 직접 연동
- 의미 기반 클러스터 시각화
- 고급 성숙도 점수 (단순 3축 별점만)
- 자동 특허성 판단
- `IdeaElement` 등 테이블 승격 (§17)

### 23.4 구현 순서

각 단계가 끝날 때마다 전체 테스트가 통과해야 한다.

| 단계 | 내용 | 이 단계에서 되는 것 |
|---|---|---|
| 1 | schemas + PasteAdapter + chunking | 대화를 턴·청크로 쪼갠다 (AI 없음) |
| 2 | dedup + scoring + elements 정규화 | 중복·중요도가 AI 없이 계산된다 |
| 3 | Mock Provider 3개 메서드 | 키 없이 파이프라인이 끝까지 돈다 |
| 4 | parser → ImportPlan | 신규 발명 후보가 나온다 |
| 5 | ConversationService 저장 | DB에 실제로 들어간다 |
| 6 | UI 새 대화 추가 3단계 | 사람이 쓸 수 있다 |
| 7 | diff.py + 기존 발명 업데이트 | N차 누적이 된다 |
| 8 | Anthropic Provider | 실제 품질이 나온다 |
| 9 | 대화 기록 탭 + 아이디어 지도 탭 | 축적이 보인다 |
| 10 | E2E + 문서 + 회귀 | 릴리스 가능 |

1~6단계까지만으로도 Mock 기반의 완결된 흐름이 된다.
**8단계 전까지 실제 AI 없이 개발·테스트가 가능하다.**

---

## 24. 후속 버전 범위

| 버전 | 내용 |
|---|---|
| 0.5.1 | `MarkdownFileAdapter` / `PlainTextFileAdapter` |
| 0.6.0 | `HtmlExportAdapter`(이미지 첨부 가능) · `ChatGptExportAdapter` · 관계도 · `IdeaElement` 테이블 승격 |
| 0.7.0 | 대화 URL 가져오기 (§24.1) · 의미 기반 클러스터 · 고급 성숙도 |
| 미정 | 이미지 비전 분석 · OCR · 자동 특허성 판단 · ChatGPT 계정 연동 |

### 24.1 URL 입력 사전 검토

구조는 대비하되(§18.3) 실제로 막히는 지점을 미리 적어 둔다.

- ChatGPT/Claude 공유 링크는 **로그인 세션이 필요한 경우가 많다.**
  공개 링크만 가능하고, 서비스가 HTML 구조를 바꾸면 즉시 깨진다.
- 서버가 외부 네트워크로 나가야 한다. 지금 InventOS는 특허 API를 빼면
  외부 호출이 없고 발명 데이터는 전부 로컬에 있다.
  **이 성질을 깨는 결정이므로 별도 판단이 필요하다.**
- 따라서 `UrlAdapter`는 "HTML을 받아 `HtmlExportAdapter`에 넘기는 얇은
  껍데기"로만 설계한다. 파싱은 재사용하고 네트워크만 추가된다.

### 24.2 첨부파일 자동 연결의 한계 (명세 수정)

붙여넣기(CTRL+V)로는 **이미지·PDF를 가져올 수 없다.** 클립보드에
텍스트만 담기기 때문이다.

| 항목 | 0.5.0 (붙여넣기) | 0.6.0 (HTML 가져오기) |
|---|---|---|
| 마크다운 표 | ✅ 텍스트로 보존 | ✅ |
| 이미지 | ❌ 불가능 | ✅ |
| PDF | ❌ 불가능 | ✅ |
| "이미지가 있었다"는 사실 | ⚠️ 자리표시자 감지 시 안내 | ✅ |

0.5.0에서는 감지 시 안내만 한다:

> 대화에 이미지 3개가 있었던 것으로 보입니다. 붙여넣기로는 이미지를
> 가져올 수 없습니다 — 발명 상세 화면에서 직접 첨부해 주세요.

---

## 25. 예상 위험 및 대응

### R1. 기능 비대화로 "빠른 기록" 철학이 훼손됨 — **가장 큰 위험**

InventOS의 정체성은 "가장 빠르게 아이디어를 기록하는 프로그램"이다.
이 기능은 그 자체로 크고, 탭 9개·인포그래픽·승인 UI가 붙으면 앱이
무거워 보인다. **처음 열었을 때 복잡하면 원래 강점을 잃는다.**

**대응**
- 이 기능 전체를 새 탭 안에 격리. 홈 → 빠른 기록 → 저장 경로는
  **지금과 100% 동일하게 유지**하고 E2E로 고정한다.
- 대화가 0건인 발명에서는 `대화 기록` / `아이디어 지도` 탭을
  **숨기거나 비활성**으로 둔다. 쓰지 않는 사용자에게는 존재하지 않는다.
- 붙여넣기 → 반영까지 클릭 3번을 넘지 않는다.

### R2. AI 비용·시간이 누적으로 폭발

12차 대화에서 매번 전체를 재분석하면 비용이 회차의 제곱으로 는다.

**대응**
- 누적 요약으로 컨텍스트를 **회차와 무관하게 일정**하게 유지 (§5.2)
- 과거 원문을 다시 보내지 않는다
- 분석 전 예상 호출 수·시간 표시
- 중복·중요도 계산의 대부분을 AI 없이 처리 (§8.1, §11)

### R3. 잘못된 자동 분류를 사용자가 그대로 승인

AI가 `deprecated`로 잘못 판정한 것을 승인하면 본문이 지워진다.

**대응**
- 본문을 지우거나 바꾸는 제안은 **기본 체크 해제** (§7.1)
- 신뢰도 표시 + 70 미만이면 기본 해제
- 모든 제안에 **원문 근거를 항상 함께** 표시 (§12)
- Revision이 남으므로 되돌릴 수 있음을 UI에 안내

### R4. 중복 판정 실패로 본문이 같은 말로 오염

대화 12개면 같은 말이 수십 번 반복된다.

**대응**
- 3단계 중복 방어 (§8.1) — 1·2단계는 결정론적
- 사용자 승인이 최종 방어선
- 본문이 길어지면 "정리하기" 안내

### R5. `analysis_json` 비대화

대화 20개 × 요소 200개면 JSON이 커진다.

**대응**
- 원문은 디스크, JSON은 **요약·참조만** (excerpt 200자 제한)
- 대화당 JSON 상한 목표 100KB
- 초과하면 §17 테이블 승격 신호로 본다

### R6. Streamlit 동기 실행으로 UI가 멈춤

14회 AI 호출은 1~2분이다. 그동안 화면이 멈춘다.

**대응**
- `st.progress`로 청크 진행률 표시
- 시작 전 예상 시간 명시
- 백그라운드 스레드는 0.5.0 범위 밖 (세션 상태 관리 복잡)
- 분석 결과를 `DraftStore`에 임시 저장해 새로고침에도 살아남게 검토

### R7. 화자 분리 실패로 핵심 가정이 깨짐

중요도의 최대 가중치가 `사용자 강조도`(0.20)인데 화자를 모르면 못 쓴다.

**대응**
- 3단계 폴백 (§18.4)
- 실패 시 해당 가중치를 0으로 두고 재정규화
- 사용자에게 명확히 안내 (품질 저하를 숨기지 않는다)

### R8. 탭 9개가 모바일에서 깨짐

390px에서 탭 9개는 가로 스크롤을 만든다 — 현재 E2E가 금지하는 조건이다.

**대응**
- 모바일은 `st.selectbox` 섹션 선택으로 대체
- 기존 모바일 E2E(가로 스크롤 없음)를 새 화면에도 적용

### R9. 새 테이블로 기존 백업·삭제 흐름이 어긋남

**대응**
- `conversation_imports.invention_id`에 `ondelete="CASCADE"` + ORM cascade
- 발명 영구 삭제(purge) 시 대화 레코드도 삭제되는지 테스트
- 휴지통(soft delete) 시 대화도 함께 숨겨지는지 확인
- 전체 데이터 ZIP에 새 테이블이 포함되는지 확인 (DB 스냅샷이므로 자동)

### R10. 설계가 커서 0.5.0이 끝나지 않음

이 문서의 범위는 크다. 한 번에 다 만들려 하면 릴리스가 무한정 밀린다.

**대응**
- §23.4의 10단계를 각각 독립 릴리스 가능 단위로 유지
- 1~6단계(Mock 기반 완결 흐름)를 **먼저 0.5.0-alpha로 내보내** 실사용
  피드백을 받고, 7~10단계를 그 뒤에 붙인다
- 각 단계마다 전체 테스트 통과를 강제한다

---

## 부록: 파싱 파이프라인 (map/reduce)

### A.1 왜 한 번에 요약하지 않는가

이유가 둘인데 **두 번째가 더 중요하다.**

1. **컨텍스트·비용**: 수십만 토큰을 한 번에 보내면 실패하거나 비싸다.
2. **발전 과정이 사라진다**: LLM은 긴 입력을 요약할 때 최종 상태로
   수렴시킨다. "레이저 → 그래핀 추가 → 금속핀으로 변경"이 그냥
   "금속핀 방식"으로 납작해진다. **이 기능의 존재 이유가 그 과정인데
   말이다.**

청크별로 처리하면 각 신호가 자기 `turn_index`를 달고 나오므로
**순서가 구조적으로 보존된다.** Timeline이 사후 추론이 아니라 파싱의
부산물로 얻어진다.

### A.2 청크 분할

```python
def split_into_chunks(
    conversation: Conversation,
    target_chars: int = 12_000,   # 약 4~6K 토큰
    overlap_turns: int = 1,
) -> list[ConversationChunk]
```

- **턴 경계에서만 자른다** — 문장 중간에서 자르면 맥락이 깨진다
- 한 턴이 `target_chars`보다 길면 단독 청크 (강제 분할 안 함)
- 인접 청크는 턴 1개를 겹쳐 경계 신호를 놓치지 않는다

### A.3 Timeline 조립 (AI 호출 0회)

후보에 속한 신호를 `turn_index` 오름차순 정렬하면 그게 곧 Timeline이다.

```
turn  3  idea_introduced     레이저로 유리에 홀 가공
turn 27  problem_raised      열 손상으로 크랙 발생
turn 41  component_added     그래핀 열확산층 추가
turn 88  idea_changed        금속핀 선배열 방식으로 전환
turn 95  experiment_planned  핀 직경별 성형 테스트
      ↓
InventionEvent 5건 (meta.layer="idea")
```

### A.4 호출 횟수

| 단계 | 호출 수 |
|---|---|
| map (신호 추출) | 청크 수 N |
| reduce (클러스터링 + 구조화) | 1~3 |
| 차이 분석 (기존 발명 누적 시) | 1~2 |
| Timeline 조립 | 0 |
| 중복 판정 1·2단계 | 0 |
| 중요도 계산 | 0 |

- 신규 발명 (12만 자): 청크 10 + reduce 2 ≈ **12회**
- 기존 발명 누적 (3만 자): 청크 3 + diff 1 ≈ **4회**

### A.5 부분 실패 허용

청크 13개 중 7번이 실패해도 나머지 12개로 계속 진행하고
`parse_warnings`에 기록한다. 기존 "AI 실패가 발명 데이터에 영향을 주지
않는다" 원칙과 같은 태도다.

| 실패 지점 | 동작 |
|---|---|
| map 일부 | 성공분으로 계속 + 경고 |
| map 전부 | 오류 표시, **DB 미변경** |
| reduce | 후보 1개(전체를 한 발명으로)로 폴백 |
| 구조화 | 원문 보존 + `parse_error` (기존 `coerce_review_result` 방식) |
| 차이 분석 | 오류 표시, 본문 미변경, 원문은 이미 저장됨 |
| 저장 | 트랜잭션 전체 롤백 |
