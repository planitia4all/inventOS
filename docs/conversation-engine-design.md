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
| 13 | [Evolution Timeline](#13-evolution-timeline) | 26 | [analysis_json 스키마 계약](#26-analysis_json-스키마-계약) |
| — | — | 27 | [AI 분석과 사용자 판단 분리](#27-ai-분석과-사용자-판단-분리) |
| — | — | 28 | [ConversationImport 삭제 정책](#28-conversationimport-삭제-정책) |
| — | — | 29 | [구현 0단계 완료 조건](#29-구현-0단계-완료-조건) |
| — | — | — | [부록: 파싱 파이프라인](#부록-파싱-파이프라인-mapreduce) |

> **§26~§29는 데이터 계약이다.** 구현 순서상 가장 먼저 고정해야 하는
> 부분이므로, 코드를 쓰기 전에 이 네 절을 확정한다.
> **§29가 0단계 완료 조건 체크리스트**다 — 여기 10개 항목이 전부
> 체크되기 전에는 `0.5.0-dev` 구현을 시작하지 않는다.

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
# + ConversationImport 레코드 1건 (raw_content 포함, §16.2)
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

### 5.2.1 누적 요약은 원문을 대체하지 않는다

누적 요약은 **AI 호출 비용을 줄이기 위한 파생물일 뿐**이다.
각 대화 원문은 언제나 독립적으로 보존되며(§6), 요약이 잘못되었더라도
원문에서 다시 만들 수 있어야 한다.

### 5.2.2 요약 이력 보존 — 별도 테이블 없이 체인으로

> **확정: `RollingSummary` 테이블을 만들지 않는다.**
> 신규 테이블은 `ConversationImport` 하나뿐이다.

**대화 #N 레코드의 `rolling_summary_after`가 곧 Summary Version N이다.**
요약은 대화마다 하나씩 생기므로, 대화 레코드가 그 요약을 들고 있으면
이력이 자연히 보존된다. 덮어쓰지 않고 각 대화가 자기 시점의 요약을
갖는다.

```
대화 #1 ─ rolling_summary_after = S1   (before_hash = null, 최초)
   │            previous_conversation_import_id = null
   ▼
대화 #2 ─ rolling_summary_before_hash = hash(S1)
   │      rolling_summary_after       = S2
   │      previous_conversation_import_id = 대화#1.id
   ▼
대화 #3 ─ rolling_summary_before_hash = hash(S2)
          rolling_summary_after       = S3
          previous_conversation_import_id = 대화#2.id
```

각 레코드가 보존하는 재현 정보 (전부 정규 컬럼, §16.2):

| 컬럼 | 의미 |
|---|---|
| `rolling_summary_before_hash` | 어느 요약 위에 얹었는가 |
| `rolling_summary_after` | 이 대화까지 반영한 요약 본문 (= Summary vN) |
| `rolling_summary_after_hash` | 다음 대화가 검증할 값 |
| `previous_conversation_import_id` | 체인의 이전 고리 |
| `raw_content_hash` | 어느 대화를 얹었는가 |
| `provider` / `model` / `prompt_version` | 무엇으로 만들었는가 |
| `analysis_schema_version` | 어떤 구조로 저장했는가 |

**해시를 남기는 이유**: 요약이 이상하다고 판단됐을 때 "어느 요약 위에
어느 대화를 얹어 만든 것인지"를 정확히 재현할 수 있어야 한다.
`before_hash`가 이전 레코드의 `after_hash`와 다르면 **체인이 끊어진
것**이므로(중간 대화가 삭제·수정됨) 재생성이 필요하다고 표시한다 (§28.3).

**체인 검증**

```python
def verify_summary_chain(imports: list[ConversationImport]) -> list[str]:
    """끊어진 지점의 import id를 돌려준다. 빈 리스트면 정상."""
    broken = []
    for prev, cur in zip(imports, imports[1:]):   # sequence_no 오름차순
        if cur.rolling_summary_before_hash != prev.rolling_summary_after_hash:
            broken.append(cur.id)
    return broken
```

이 검증은 **AI 호출 없이** 즉시 수행되므로 화면 진입 시마다 돌려도 된다.

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
① 원본 대화        ConversationImport.raw_content       절대 불변
② AI 분석 결과     analysis_json.ai_analysis            재분석 시 교체
③ 사용자 판단      analysis_json.user_review            재분석해도 보존 (§27)
④ 변경 전 스냅샷    InventionRevision                    불변
⑤ 변경 사건        InventionEvent                       불변
```

### 6.2 원문 저장 위치: DB 컬럼

원문은 `ConversationImport.raw_content` **컬럼에 직접 저장한다.**

> **초기 설계에서 바뀐 결정이다.** 처음에는 `.md` 첨부파일(디스크)을
> 제안했으나, 다음 이유로 DB 컬럼이 낫다고 판단했다.

| 항목 | DB 컬럼 | 디스크 첨부 |
|---|---|---|
| 저장 원자성 | ✅ 트랜잭션 하나 | ❌ 파일 성공 + DB 실패 시 고아 파일 |
| 해시 기반 중복 검사 (§6.4) | ✅ `WHERE raw_content_hash = ?` | ⚠️ 파일을 다 읽어야 함 |
| 백업 일관성 | ✅ DB 스냅샷에 포함 | ⚠️ DB와 파일이 따로 |
| 무결성 관리 | ✅ 불필요 | ❌ 파일 없는 레코드 발생 가능 |
| DB 크기 | ⚠️ 증가 | ✅ 영향 없음 |

파일-DB 불일치라는 **버그 종류 자체가 사라지는 것**이 크기 증가보다
중요하다. 이미 첨부파일에서 그 문제를 겪어 무결성 검사 도구를 만들어야
했다(§0.4.0).

**크기 계산**: 대화 평균 50KB × 발명당 20건 × 발명 100건 = 약 100MB.
SQLite가 다루기에 전혀 문제없는 크기다. 다만 설정 화면의 DB 백업
다운로드가 그만큼 커진다.

> **재검토 기준**: DB가 500MB를 넘으면 `raw_content`를 zlib 압축해
> `BLOB`으로 저장하는 것을 검토한다(텍스트라 보통 1/4로 줄어든다).
> 0.5.0에서는 하지 않는다.

`.md` 첨부파일로 저장하지 않으므로 **`ALLOWED_EXTENSIONS` 변경도
불필요하다** — 앞선 설계에서 필요하다고 적었던 항목이 사라졌다.

### 6.3 재분석 가능성

원문이 그대로 있으므로 나중에 더 좋은 모델로 **재분석**할 수 있다.
재분석은 기존 레코드를 수정하지 않고 새 `ConversationImport`를 만들며
(`reanalysis_of`로 원본을 가리킴), `raw_content`와 해시는 복사한다.

**재분석해도 사용자의 승인·수정·거절 기록은 이어받는다** — 방법은
§27.3에 있다.

### 6.4 중복 검사 1단계 — 전체 원문 Exact Hash

같은 대화를 실수로 두 번 붙여넣는 일은 흔하다. 그대로 두면 본문이
같은 내용으로 두 번 오염된다.

**정규화 후 SHA-256을 계산한다.**

```python
def normalize_for_hash(raw: str) -> str:
    """해시 계산용 정규화. 표시용 원문(raw_content)은 건드리지 않는다."""
    text = unicodedata.normalize("NFKC", raw)
    text = _UI_NOISE.sub("", text)      # "Copy code", "복사", "ChatGPT said:" 등
    text = re.sub(r"[ \t]+", " ", text)  # 공백 정규화
    text = re.sub(r"\n{3,}", "\n\n", text)  # 줄바꿈 정규화
    return text.strip()

raw_content_hash = hashlib.sha256(
    normalize_for_hash(raw).encode("utf-8")
).hexdigest()
```

정규화는 **해시 계산에만** 쓴다. `raw_content`에는 사용자가 붙여넣은
그대로를 저장한다 (원칙 1).

**판정과 안내**

| 상황 | 동작 |
|---|---|
| 같은 발명에 같은 해시 | ⚠️ 경고 + 기본 차단 (사용자가 명시적으로 강행 가능) |
| 다른 발명에 같은 해시 | ⚠️ 안내 ("이 대화는 INV-2026-00007에 이미 등록됨") |
| 해시는 다르지만 TF-IDF 유사도 ≥ 0.95 | ⚠️ 경고 (일부만 다시 복사한 경우) |

```
⚠️ 동일하거나 매우 유사한 대화가 이미 등록되어 있습니다.
   대화 #3 — 2026-07-27 · 유사도 100%

   [취소]   [그래도 새 대화로 추가]
```

**기본은 경고이고 차단이 아니다.** 사용자가 의도적으로 같은 대화를
다시 넣는 경우(예: 다른 발명 관점에서 재분석)를 막지 않는다.

### 6.5 중복 검사 2단계 — 메시지 단위 (전체 재복사 대응)

**실제로 가장 흔한 패턴이다.** 사용자는 같은 대화창에서 대화를
이어가므로, 후속 대화를 복사할 때 과거 대화가 통째로 딸려온다.

```
1차 Import:  메시지  1~20
2차 Import:  메시지  1~35   ← 1~20이 그대로 포함됨
```

1단계(전체 해시)로는 이걸 못 잡는다 — 원문이 다르므로 해시도 다르다.
그대로 두면 **메시지 1~20을 두 번 분석하고 본문에 두 번 반영한다.**

#### 6.5.1 메시지 해시 비교

각 메시지마다 `content_hash`를 만들어 `analysis_json.messages`에
보존한다 (§26.2, §5). 새 Import가 들어오면 **같은 발명의 기존 Import
전부**의 메시지 해시와 대조한다.

```python
def classify_messages(
    new_messages: list[Turn],
    known_hashes: dict[str, tuple[str, int]],   # hash -> (import_id, message_index)
    known_texts: list[str],
) -> MessageOverlapReport:
    """새 대화의 각 메시지를 기존/신규/수정으로 분류한다."""
    already, newly, modified = [], [], []
    for msg in new_messages:
        h = message_hash(msg.text)
        if h in known_hashes:
            already.append(msg.index)
            continue
        best = max_similarity(msg.text, known_texts)      # TF-IDF
        if best.score >= 0.90:
            modified.append((msg.index, best.ref))         # 살짝 편집됨
        else:
            newly.append(msg.index)
    return MessageOverlapReport(already, newly, modified)
```

`message_hash`는 §6.4의 `normalize_for_hash`를 메시지 단위로 적용한
SHA-256이다 (공백·UI 문구 차이를 흡수).

#### 6.5.2 재복사 패턴 판정

단순히 "겹치는 메시지가 있다"가 아니라, **앞부분이 순서까지 일치하는가**를
본다. 이게 재복사의 특징이다.

```
새 대화의 [0..k] 구간이 기존 Import의 [0..k]와 순서까지 일치하고,
k+1 이후가 전부 신규이면  →  "재복사 확실" (superset)
```

| 판정 | 조건 | 기본 동작 |
|---|---|---|
| `identical` | 전체 해시 동일 | ⚠️ 경고 + 차단 (§6.4) |
| `superset` | 앞부분 순서 일치 + 뒤에 신규 | ✅ **신규 구간만 분석** |
| `partial_overlap` | 겹치지만 순서가 안 맞음 | ⚠️ 안내 후 사용자 선택 |
| `unrelated` | 겹침 없음 | 전체 분석 |

#### 6.5.3 신규 구간만 분석한다

`superset`으로 판정되면 **메시지 21~35만 map 단계에 넣는다.**

- 비용이 크게 준다 (35개 → 15개)
- **맥락 손실이 없다** — 1~20의 내용은 이미 누적 요약(§5.2)에 들어
  있고, 그 요약을 컨텍스트로 함께 넣기 때문이다. 재복사 대응과 누적
  요약 설계가 여기서 정확히 맞물린다.
- `raw_content`에는 **사용자가 붙여넣은 전체(1~35)를 그대로** 저장한다.
  분석 범위를 좁히는 것이지 원문을 자르는 것이 아니다 (원칙 1).

레코드에 남기는 값:

```json
"overlap": {
  "match_type": "superset",
  "overlap_with_import_id": "conv-uuid-1",
  "already_imported_indices": [0, 1, ..., 19],
  "newly_added_indices": [20, 21, ..., 34],
  "modified_indices": [],
  "analyzed_range": [20, 34]
}
```

#### 6.5.4 화면

```
ℹ️ 이 대화는 대화 #1의 이어진 내용으로 보입니다.

   메시지 35개 중
     기존 20개  (대화 #1에서 이미 분석됨)
     신규 15개  ← 이 부분만 분석합니다

   예상 AI 호출 4회 (전체 분석 시 9회)

   ● 신규 부분만 분석          ← 기본
   ○ 전체를 다시 분석          (이전 분석 결과와 별개로 처리)
   ○ 취소
```

#### 6.5.5 편집된 메시지

사용자가 과거 메시지를 수정한 뒤 다시 복사한 경우(`modified`),
자동으로 처리하지 않고 **알리기만 한다.**

```
⚠️ 기존 메시지 2개가 수정된 것으로 보입니다 (유사도 92%, 95%).
   원문은 새 대화 레코드에 그대로 보존되며,
   이전 분석 결과는 변경되지 않습니다.
```

이전 분석을 소급해서 고치지 않는 이유: 그 분석에 근거해 사용자가 이미
승인/반영한 내용이 있을 수 있고, 소급 수정은 §27의 판단 보존 원칙과
충돌한다. 필요하면 사용자가 해당 대화를 **재분석**하면 된다 (§6.3).

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

    # 상태는 두 종류로 나눈다 (§9.4)
    declared_status: str = "proposed"   # 사용자가 정한 것 — 시스템이 못 바꿈
    derived_status: list[str] = field(default_factory=list)  # 시스템이 계산한 것

    # 누가 말했는가 (§9.5)
    origin_stance: str = "ai_proposed"
    stance_history: list[StanceRecord] = field(default_factory=list)

    first_seen: SourceRef | None = None
    last_seen: SourceRef | None = None
    mentions: list[SourceRef] = field(default_factory=list)
    importance: int = 0        # 0~100 (§11)
    importance_breakdown: ImportanceBreakdown | None = None

@dataclass
class IdeaRelation:
    subject: str               # "그래핀 섬유"
    predicate: str             # "제공한다"
    object: str                # "전도성"
    sources: list[SourceRef] = field(default_factory=list)
```

### 9.4 상태 — 사용자가 정한 것과 시스템이 계산한 것을 분리한다

> **이 분리가 핵심이다.** 둘을 한 필드에 섞으면
> "최근 대화에 안 나왔다"는 이유로 사용자가 **채택**한 아이디어가
> 폐기로 표시되는 사고가 난다.

**A. 사용자가 명시한 상태** (`declared_status`) — 하나만 가지며,
시스템은 **절대 자동으로 바꾸지 않는다.**

| 값 | 의미 |
|---|---|
| `proposed` | 새로 제안됨 (초기값) |
| `candidate` | 후보로 유지 |
| `deferred` | 보류 |
| `adopted` | 채택 |
| `rejected` | 명시적 폐기 |
| `disproved_by_experiment` | 실험으로 반증됨 |
| `superseded` | 다른 방법으로 대체됨 (`superseded_by` 함께 기록) |

**B. 시스템이 계산한 상태** (`derived_status`) — 여러 개 동시 가능,
매번 다시 계산되며 저장은 캐시일 뿐이다.

| 값 | 계산 근거 |
|---|---|
| `newly_proposed` | 최근 대화에서 처음 등장 |
| `strengthened` | 이번 대화에서 더 구체화됨 |
| `modified` | 이번 대화에서 내용이 바뀜 |
| `dormant` | **최근 N회차 동안 미언급** (기본 N=3) |

```python
def derive_status(el: IdeaElement, current_seq: int) -> list[str]:
    """파생 상태만 계산한다. declared_status는 건드리지 않는다."""
    out = []
    if el.first_seen and el.first_seen.sequence_no == current_seq:
        out.append("newly_proposed")
    if el.last_seen and current_seq - el.last_seen.sequence_no >= 3:
        out.append("dormant")          # ← 폐기가 아니다
    return out
```

**표시할 때도 두 배지를 따로 보여준다.**

```
그래핀 섬유          ★ 채택           💤 최근 미언급 (4회차 전)
방사선 직접 천공     ⊘ 명시적 폐기
금속핀 삽입          ○ 후보 유지       ✎ 이번에 수정됨
레이저 직접 가공     ○ 후보 유지       💤 최근 미언급
```

`💤 최근 미언급`은 **"확인해 보라"는 힌트일 뿐 판정이 아니다.**
아이디어 지도에서 `dormant` 항목을 모아 "한동안 다루지 않은 아이디어
5건 — 아직 유효한가요?"로 되짚어 주는 용도로만 쓴다.

### 9.5 발언 주체 — AI 제안은 자동 승격하지 않는다

> **원칙: AI만 제안하고 사용자가 아무 반응도 하지 않은 내용은
> 핵심 발명 내용으로 자동 승격하지 않는다.**

발명자가 실제로 생각한 것과 AI가 거들어 준 것을 구분하지 못하면,
나중에 특허 출원에서 **발명자의 착상을 증명할 수 없다.**

| `origin_stance` | 의미 | 핵심 필드 자동 제안 |
|---|---|---|
| `user_proposed` | 사용자가 직접 제안 | ✅ 기본 체크 |
| `user_adopted` | 사용자가 최종 채택 | ✅ 기본 체크 |
| `user_agreed` | 사용자가 AI 제안에 동의 | ✅ 기본 체크 |
| `user_asked` | 사용자가 질문한 것 | ⚠️ 질문으로만 등록 (§14.1) |
| `ai_proposed` | AI가 제안, **사용자 반응 없음** | ❌ **기본 체크 해제 + 표시** |
| `user_rejected` | 사용자가 AI 제안을 부정 | ❌ 제안하지 않음 |
| `user_deferred` | 사용자가 보류·폐기 | ❌ 제안하지 않음 |

```python
@dataclass
class StanceRecord:
    stance: str                 # 위 7종
    source: SourceRef           # 어느 발언에서 이 태도가 나타났는가
    turn_index: int
```

**태도는 대화가 진행되며 바뀐다.** `stance_history`에 순서대로 쌓고,
`origin_stance`는 그중 **가장 강한 사용자 태도**를 취한다
(`user_adopted` > `user_proposed` > `user_agreed` > `user_asked`
> `ai_proposed` > `user_deferred` > `user_rejected`).

```
turn 12  ai_proposed    AI가 "그래핀 섬유를 써보는 건 어떨까요?"
turn 14  user_agreed    사용자 "그거 좋네요, 장력만 유지되면"
turn 88  user_adopted   사용자 "그래핀 섬유 방식으로 가겠습니다"
         → origin_stance = user_adopted
```

**화면 표시**

```
▼ 새로 추가 3
  ☑ 핵심 아이디어 ← 그래핀 섬유 전도성 비아        👤 사용자 제안
  ☐ 예상 효과   ← 공정 단계 30% 감소             🤖 AI 제안 (사용자 반응 없음)
     ⓘ AI가 제안했지만 대화에서 확인되지 않았습니다. 검토 후 선택하세요.
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
1단계  결정론적 정규화 (AI 불필요)      ← §10.4 한국어 처리
2단계  AI 병합 후보 제안                 신뢰도 + 근거 원문 포함
3단계  사용자 승인                       ← 자동 병합하지 않음
       ☑ 그래핀 실 + Graphene fiber → "그래핀 섬유"
       ☐ 전도성 섬유                 → 별개 유지
```

### 10.4 한국어 정규화 — 형태소 분석기 없이

**0.5.0-alpha에 형태소 분석기(KoNLPy/Mecab 등)를 넣지 않는다.**
설치가 무겁고(Java/C 의존), Windows 설치 실패가 잦으며, "새 의존성
최소화" 원칙에 어긋난다. 대신 아래 최소 규칙으로 시작한다.

**1) 표기 통일**

```python
text = unicodedata.normalize("NFKC", text)   # 전각/반각
text = text.lower()                          # 영문 대소문자
text = re.sub(r"[-_·\s]+", "", text)         # 하이픈·중점·공백
```

**2) 조사 제거 (보수적)**

```python
_PARTICLES = ("으로써","으로서","에서는","에게서","으로","에서","까지",
              "부터","에게","한테","이나","라도","보다","처럼","마다",
              "은","는","이","가","을","를","의","에","와","과","도","만","로")

def strip_particle(token: str) -> str:
    """조사로 보이는 꼬리를 뗀다. 남는 어간이 2자 미만이면 원본 유지."""
    for p in sorted(_PARTICLES, key=len, reverse=True):
        if token.endswith(p) and len(token) - len(p) >= 2:
            return token[: -len(p)]
    return token
```

`len >= 2` 가드가 핵심이다. 이게 없으면 `정도` → `정`, `가능` → `가`
같은 오작동이 난다.

| 입력 | 결과 | 비고 |
|---|---|---|
| 그래핀은 | 그래핀 | ✅ |
| 유리기판에서 | 유리기판 | ✅ |
| 장력을 | 장력 | ✅ |
| 정도 | 정도 | ✅ 가드가 막음 (2-1=1 < 2) |
| 가능 | 가능 | ✅ 가드가 막음 |
| 자동화 | 자동화 | ✅ 해당 조사 없음 |
| 온도 | 온도 | ✅ 가드가 막음 |

**한계를 인정한다**: `모델링` → `모델`(ㄹ 아님, 해당 없음)처럼 대부분
안전하지만, `이론` → 앞에 `이`가 아니라 끝이 `론`이라 안전, `자료를`
→ `자료` 정상. 다만 `노트` 같은 단어가 `노` + `트`로 오인될 일은 없다
(조사 목록에 `트`가 없음). **오작동이 발견되면 조사 목록을 줄이는
방향으로 조정한다** — 과하게 떼는 것보다 덜 떼는 편이 안전하다.

**3) N-gram (보조 매칭)**

한글은 어절 경계가 불규칙하므로, 병합 후보를 찾을 때 **문자 bigram
자카드 유사도**를 보조로 쓴다.

```
"유리관통비아"  → {유리, 리관, 관통, 통비, 비아}
"유리비아"      → {유리, 리비, 비아}
자카드 = 2/6 = 0.33   → 병합 후보로 제안 (임계 0.3)
```

**4) 내장 약어 사전** (`src/conversations/abbreviations.py`)

```python
BUILTIN_ABBREVIATIONS = {
    "tgv": ["throughglassvia", "유리관통비아", "글라스비아", "유리비아"],
    "pcb": ["printedcircuitboard", "인쇄회로기판"],
    ...
}
```

프로젝트에 내장하고, 사용자가 추가할 수는 없다(오염 방지).

**5) 사용자 동의어 사전**

사용자가 승인한 병합은 **발명 단위**로 `idea_elements` JSON에 쌓인다.

```json
{"canonical": "그래핀 섬유",
 "synonyms": ["그래핀실", "graphenefiber", "전도성섬유"],
 "approved_at": "2026-08-10T...", "approved_by": "user"}
```

전역 사전(모든 발명 공유)은 `Tag.canonical_tag_id`가 생기는
0.6.0으로 미룬다 (§17).

**6) 사용자 직접 병합·분리**

아이디어 지도 화면에서 언제든 개념을 합치거나 되돌릴 수 있다.
**병합은 되돌릴 수 있어야 한다** — 원본 표기를 `synonyms`에 그대로
보존하므로 분리 시 복원된다.

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
| 사용자 강조 | `u` | 태도 가중 평균 (§11.1.1) | ✗ |
| 결정 영향도 | `d` | `modified`/`decision` 변화 연루 횟수 (정규화) | ✗ |
| 연결도 | `c` | `IdeaRelation` 차수 (정규화) | △ |
| 증거 보유 | `e` | 연결된 실험·이미지·특허 수 (상한 3, 정규화) | ✗ |

**8개 중 7개가 AI 없이 계산된다.** `c`만 AI가 만든 관계에 의존하며,
없으면 0으로 둔다. 즉 **Mock에서도 중요도가 의미 있게 동작한다.**

#### 11.1.1 사용자 강조는 단순 비율이 아니라 태도 가중이다

"사용자 발언에서 몇 번 나왔나"만 세면, 사용자가 **부정한** 내용도
언급 횟수로 잡혀 점수가 올라간다. §9.5의 태도(`stance`)로 가중한다.

```python
STANCE_WEIGHT = {
    "user_adopted":  1.0,   # 최종 채택
    "user_proposed": 1.0,   # 직접 제안
    "user_agreed":   0.8,   # AI 제안에 동의
    "user_asked":    0.6,   # 질문 (관심의 신호)
    "ai_proposed":   0.2,   # AI만 말함
    "user_deferred": 0.1,   # 보류
    "user_rejected": 0.0,   # 부정 — 언급돼도 점수 없음
}

def user_emphasis(mentions: list[SourceRef],
                  stances: list[StanceRecord]) -> float:
    if not mentions:
        return 0.0
    total = sum(STANCE_WEIGHT.get(s.stance, 0.2) for s in stances)
    return min(1.0, total / len(mentions))
```

`user_rejected`가 0.0인 것이 중요하다. **사용자가 "그건 아니다"라고
열 번 말한 개념이 중요도 상위에 오르면 안 된다.**

화자 분리에 실패했으면(§18.4) 모든 태도를 알 수 없으므로 `u`의
가중치를 0으로 두고 나머지 7개를 재정규화한다.

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

### 11.3 설명 가능성 — 점수는 항상 분해해서 저장한다

**종합 점수를 하나의 불투명한 숫자로 만들지 않는다.** 8개 원자값과
가중 기여도를 **함께 저장**해서, UI가 언제든 근거를 펼쳐 볼 수 있게 한다.

```python
@dataclass
class ImportanceBreakdown:
    """중요도의 원자값과 기여도. 점수와 항상 함께 저장한다."""
    # 사람이 바로 이해하는 원자값 (정규화 전)
    mention_count: int          # 언급 횟수
    conversation_count: int     # 서로 다른 대화 등장 수
    first_seq: int              # 최초 등장 회차
    last_seq: int               # 최근 등장 회차
    user_mention_count: int     # 사용자 발언에서의 언급 수
    decision_count: int         # 결정·변경에 연루된 횟수
    experiment_count: int       # 관련 실험 수
    attachment_count: int       # 관련 첨부 수

    # 정규화값(0~1)과 가중 기여도 — 합이 곧 최종 점수
    factors: dict[str, float]        # {"f": 0.82, "s": 0.50, ...}
    contributions: dict[str, float]  # {"f": 12.3, "s": 7.5, ...}
    total: int                       # 0~100
    weights_version: str             # 가중치를 바꿔도 과거 점수를 해석 가능
```

`weights_version`을 함께 저장하는 이유: 가중치를 튜닝하면 과거에
계산된 점수와 비교가 불가능해진다. 버전을 남기면 "이 점수는 v1
가중치로 계산됨"을 알 수 있고, 필요하면 일괄 재계산할 수 있다.

**화면**

```
그래핀 섬유                                        중요도 92
  언급 18회 · 대화 6개 · 최근 3일 전
  사용자 강조 높음 · 실험 2 · 이미지 3        [근거 보기 ▾]

  ▾ 근거
    언급 빈도        18회        0.82 × 0.15 = 12.3
    대화 확산도      6/12개      0.50 × 0.15 =  7.5
    지속성           #2~#11      0.83 × 0.10 =  8.3
    최근성           1회차 전    0.79 × 0.15 = 11.9
    사용자 강조      11/18       0.61 × 0.20 = 12.2
    결정 영향도      4회         0.80 × 0.10 =  8.0
    연결도           3           0.60 × 0.05 =  3.0
    증거 보유        실험2+이미지3 1.00 × 0.10 = 10.0
                                            ─────────
                                              합계  73  ← 예시
    (가중치 v1)
```

원자값을 저장해 두면 **가중치만 바꿔서 즉시 재계산**할 수 있다 —
원본 대화를 다시 분석할 필요가 없다.

---

## 12. Source Traceability

### 12.1 SourceRef

```python
@dataclass
class SourceRef:
    kind: str                          # conversation | experiment | attachment | patent | manual

    # --- 대화 출처 (kind == "conversation") ---
    conversation_import_id: str = ""   # ConversationImport.id
    sequence_no: int = 0               # 대화 #3
    message_index: int = -1            # 대화 내 몇 번째 메시지 (= turn_index)
    message_role: str = ""             # user | assistant | unknown
    source_excerpt: str = ""           # 원문 발췌 (최대 200자)
    source_start: int = -1             # raw_content 기준 시작 offset (-1 = 미상)
    source_end: int = -1               # 〃 끝 offset
    confidence: int = 0                # 0~100

    # --- 그 밖의 출처 ---
    ref_id: str = ""                   # experiment_id / attachment_id / patent_id
```

### 12.1.1 문자 Offset을 얻는 방법 — AI에게 세게 하지 않는다

LLM은 문자 위치를 세는 데 약하다. offset을 직접 물어보면 거의 틀린다.
대신 **AI에게는 원문을 그대로 인용하게 하고, offset은 우리가 계산한다.**

```python
def locate(raw_content: str, message_start: int, excerpt: str) -> tuple[int, int]:
    """excerpt를 원문에서 찾아 offset을 계산한다. 못 찾으면 (-1, -1)."""
    idx = raw_content.find(excerpt, message_start)
    if idx < 0:
        idx = raw_content.find(excerpt)      # 메시지 밖에서 재시도
    if idx < 0:
        return (-1, -1)                       # AI가 표현을 바꿈
    return (idx, idx + len(excerpt))
```

- 프롬프트에서 `excerpt`는 **원문 그대로 인용**하도록 강제한다(§19.2).
- 찾으면 정확한 offset이 생긴다 — AI가 숫자를 세지 않았으므로 신뢰할 수 있다.
- 못 찾으면 `(-1, -1)`로 두고 `excerpt`만 보존하며, 해당 항목의
  `confidence`를 낮춘다(AI가 원문을 바꿔 인용했다는 신호이므로).

### 12.1.2 MVP 최소 보장

offset이 `-1`이어도 다음 4가지는 **항상** 제공한다.

```
대화 번호        sequence_no
사용자 / AI      message_role
메시지 번호      message_index
원문 일부        source_excerpt
```

즉 offset은 **있으면 더 좋은 정보**이고, 없어도 출처 추적은 성립한다.

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

**0.5.0-alpha에서 새로 만드는 테이블은 이것 하나뿐이다.**
`ConversationMessage` · `IdeaElement` · `IdeaElementMention` ·
`IdeaRelation` · `IdeaChange` · `SourceReference` · `RollingSummary`는
**만들지 않는다.** 아이디어 요소·출처·사용자 판단·메시지 분석 결과는
계속 버전형 `analysis_json` 안에 둔다 (§26).

테이블 승격은 아래가 **실제로** 확인될 때만 검토한다 — 미리 만들지 않는다.

- 여러 발명을 가로지르는 Idea Element 검색이 필요해짐
- 특정 개념 기준 통계가 반복적으로 필요해짐
- JSON 집계 성능이 실제로 문제가 됨
- 개별 Element의 독립적인 수정·권한·수명 관리가 필요해짐
- 발명당 대화 수가 설계 예상(20건)보다 크게 늘어남

구현: `src/database/models.py::ConversationImport`

```python
class ConversationImport(Base):
    __tablename__ = "conversation_imports"

    # --- 식별 / 소속 ---
    id:                str            # uuid (기존 테이블과 같은 정책)
    invention_id:      str            # FK → inventions.id  (ON DELETE 절 없음)
    sequence_no:       int            # 발명별 1,2,3...

    # --- 출처 ---
    title:             str
    source_type:       str            # chatgpt | claude | other | file
    source_name:       str | None
    conversation_date: date | None    # 실제 대화일 (사용자 입력)
    imported_at:       datetime

    # --- 원문 (§6.2) ---
    raw_content:        str           # 붙여넣은 그대로. 자동으로 자르지 않는다.
    raw_content_hash:   str           # 정규화 후 SHA-256 (§6.4)
    raw_content_length: int           # Python 문자열 길이(코드포인트). 바이트 아님.

    # --- 분석 ---
    analysis_status:   str            # pending | analyzing | analyzed
                                      # | failed | needs_reanalysis
    analysis_json:     str | None     # §26 스키마를 결정론적으로 직렬화한 TEXT
    analysis_schema_version: str      # "1.0"
    analysis_version:  int            # 재분석할 때마다 +1. 0이면 분석 전.
    provider:          str            # mock | anthropic
    model:             str | None
    prompt_version:    str
    synonym_dict_version: int         # 해시 입력 아님 — remap 판단용 (§27.2.2)

    # --- 누적 요약 체인 (§5.2.2) — 별도 테이블 없이 여기에 보존 ---
    previous_conversation_import_id: str | None  # FK → 자기 테이블
    rolling_summary_before_hash: str | None      # 어느 요약 위에 얹었는가
    rolling_summary_after:       str | None      # 이 대화까지의 요약
    rolling_summary_after_hash:  str | None      # 다음 대화가 검증할 값
    summary_status: str              # not_generated | valid
                                     # | needs_regeneration | failed

    # --- 부분 중복 (§6.5). 판정은 Parser 단계에서 채운다 ---
    overlap_type:           str | None  # exact_duplicate | superset
                                        # | partial_overlap | new
    overlap_with_import_id: str | None  # FK → 자기 테이블
    new_message_start:      int | None  # 실제로 새로 분석한 구간
    new_message_count:      int | None

    # --- 반영 결과 ---
    applied_at:          datetime | None
    created_revision_id: str | None   # FK → invention_revisions.id (SET NULL)
    created_event_id:    str | None   # FK → invention_events.id    (SET NULL)

    # --- 삭제 (§28) ---
    is_deleted: bool                  # 기본 False
    deleted_at: datetime | None

    created_at: datetime
    updated_at: datetime
```

**필수 정규 컬럼** (이것만은 JSON에 넣지 않는다):
`invention_id` · `sequence_no` · `raw_content` · `raw_content_hash` ·
`analysis_status` · `analysis_json` · `analysis_schema_version` ·
`analysis_version` · `provider` · `model` · `prompt_version` ·
`synonym_dict_version` · `previous_conversation_import_id` ·
`rolling_summary_before_hash` / `rolling_summary_after` /
`rolling_summary_after_hash` · `is_deleted` · `created_at` · `updated_at`

**인덱스와 제약**

| 이름 | 종류 | 용도 |
|---|---|---|
| `uq_conversation_import_seq` | UNIQUE `(invention_id, sequence_no)` | 회차 중복 방지 |
| `ck_conversation_import_prev_not_self` | CHECK | 자기 자신을 이전 고리로 지정 금지 |
| `ix_conversation_import_invention_hash` | INDEX `(invention_id, raw_content_hash)` | 같은 발명 안 중복 검사 |
| `ix_conversation_import_hash` | INDEX `(raw_content_hash)` | 다른 발명에 같은 원문이 있는지 |
| `ix_conversation_import_invention_deleted` | INDEX `(invention_id, is_deleted)` | 삭제되지 않은 대화 목록 (§28) |
| `ix_conversation_import_previous` | INDEX `(previous_conversation_import_id)` | 요약 체인 역추적 (§5.2.2) |

**`raw_content_hash`에 UNIQUE를 걸지 않는 이유**: 사용자가 같은 대화를
일부러 다시 저장하고 싶을 수 있다. 중복은 **경고**지 금지가 아니다.
서비스가 `new` / `exact_duplicate_same_invention` /
`exact_duplicate_other_invention`을 돌려주고, 저장 여부는 사용자가 정한다.

**`invention_id` FK에 `ON DELETE` 절을 달지 않은 이유**: DB가 조용히
연쇄 삭제하면 "무엇이 함께 사라지는지 먼저 보여준다"는 영구 삭제 정책을
우회하게 된다. 대신 ORM 관계(`Invention.conversation_imports`)의 cascade가
영구 삭제 시 명시적으로 함께 지운다 — 삭제 경로가 서비스 한 곳으로 모인다.
발명을 **휴지통에 넣는 것**(Soft Delete)은 대화에 아무 영향이 없다.

**`sequence_no` 생성**: 잠금 없이 `max+1`로 계산하고, UNIQUE 제약에
부딪히면 다시 계산해서 재시도한다(최대 5회, SAVEPOINT로 감싸 바깥
트랜잭션을 깨뜨리지 않는다). 발명번호 생성과 같은 방식이다. **삭제된
회차까지 포함해서** 최대값을 구하므로 번호가 재사용되지 않는다.

**`analysis_json` 직렬화**는 다음으로 고정한다 (§26.4).

```python
json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

JSON 타입 컬럼이 아니라 TEXT인 이유는 키 순서까지 고정해야 변경 감지와
비교가 안정적이기 때문이다.

> 메시지 단위 해시(§6.5)는 `analysis_json.messages`에 있어 인덱스를
> 걸 수 없다. 발명당 대화 20개 × 메시지 100개 = 2,000건 규모라
> Python 집합 비교로 충분하다. 느려지면 §17의 테이블 승격 신호로 본다.

**이 테이블 하나가 필요한 이유**: 대화 목록·회차 정렬·반영 상태 조회·
중복 해시 검사가 전부 기본 기능인데, 이걸 `InventionAIResult`의 JSON
안에 넣으면 **목록 화면조차 JSON 파싱으로** 만들어야 하고 해시 검사에
전체 스캔이 필요하다. 반면 요소·질문·변화 같은 **분석 내용은 조회 축이
아니므로** JSON으로 충분하다.

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
| 원문 보존 | — | `ConversationImport.raw_content` (§6.2) |
| AI 분석 결과 | `ConversationImport.analysis_json` | 테이블 1 |
| 변경 전 스냅샷 | `InventionRevision` | — |
| 변경 사건 | `InventionEvent` + `meta.layer` | — |
| Evolution Timeline | 〃 (layer=idea 필터) | — |
| Idea Element | `InventionAIResult(kind="idea_elements")` | — |
| 누적 요약 | — | `ConversationImport` 컬럼 (§5.2.2) |
| 메시지 분리 결과 | — | `analysis_json.messages` (§26.2) |
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
├─ schemas.py          Conversation, Turn, Signal, SourceRef,
│                      ChangeProposal, IdeaElement, Question, ImportPlan
├─ analysis_schema.py  ★ analysis_json 스키마 계약 + 접근자 + 마이그레이션 (§26)
│                        — JSON 키 문자열이 존재하는 유일한 파일
├─ hashing.py          원문 정규화 + SHA-256 + item_id 생성 (§6.4, §27.2)
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
| `app.py` | 라우트 1개 |

> `ALLOWED_EXTENSIONS` 변경은 **불필요해졌다** — 원문을 첨부파일이
> 아니라 DB 컬럼에 저장하기로 했기 때문이다 (§6.2).

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
│  [분석 결과]  [원문]  [남은 항목 반영]  [삭제]         │
├──────────────────────────────────────────────────────┤
│  대화 #2            2026-07-28          ✅ 반영 완료  │
│  ↑ 대화 #1의 이어진 내용 (메시지 20개 재사용)          │
│  🔗 요약 체인 재생성 필요                              │
│  [분석 결과]  [원문]  [요약 재생성]                    │
├──────────────────────────────────────────────────────┤
│  ▸ 삭제된 대화 2건 보기                                │
└──────────────────────────────────────────────────────┘
```

목록에 함께 표시하는 상태 배지:

| 배지 | 의미 |
|---|---|
| ✅ 반영 완료 / ⚠️ 일부 반영 / ○ 미반영 | `analysis_status` |
| ↑ 이어진 내용 | `overlap_match_type = superset` (§6.5) |
| 🔗 요약 체인 재생성 필요 | `summary_chain_status = needs_regeneration` (§28.3) |
| 🗑 삭제됨 | `deleted_at` (접힘 영역 안, §28.5) |

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
   원문은 대화 #4 레코드에 그대로 보존되었습니다.  [원문 보기]

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
| `calculate_text_similarity()` | 함수 추가 | 낮음 — 기존 함수가 이걸 호출하도록 정리 |

> DB 크기가 늘어난다(원문을 컬럼에 저장, §6.2). 기존 데이터에는
> 영향이 없고 새 대화를 넣을 때만 증가한다.

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
  excerpt가 원문에 있으면 offset이 정확히 계산됨
  excerpt를 못 찾으면 offset -1 + confidence 하향 (예외 아님)
  offset이 -1이어도 대화번호/역할/메시지번호/원문일부는 항상 존재

test_analysis_schema.py               ← §26, 가장 먼저 작성
  빈 dict / None을 load해도 예외 없이 기본 구조가 나옴
  과거 버전(schema_version 없음) JSON도 현재 구조로 승격됨
  미래 버전 JSON은 예외 없이 _unmigrated_raw에 원본 보존
  필드가 없는 JSON을 읽어도 KeyError가 나지 않음
  to_json() → load() 왕복이 손실 없음
  마이그레이션 체인에 순환이 있으면 무한루프에 빠지지 않음
  JSON 키가 analysis_schema.py 밖에서 참조되지 않음 (grep 테스트, §26.6)

test_analysis_user_review.py          ← §27, 핵심
  approve/reject/edit가 user_review에만 기록됨 (ai_analysis 불변)
  재분석 시 ai_analysis만 교체되고 user_review는 보존
  같은 내용이면 item_id가 동일 → 이전 판단을 이어받음
  텍스트가 바뀌면 item_id가 달라짐 → 새 판단 대상
  재분석 결과에 없는 이전 판단은 orphaned로 이동 (삭제 아님)
  승인했지만 중복으로 반영되지 않은 항목이 구분됨
  application_result가 실제 반영된 것만 담음

test_conversation_hashing.py          ← §6.4
  공백/줄바꿈만 다른 대화는 같은 해시
  UI 문구("Copy code" 등)만 다른 대화는 같은 해시
  내용이 다르면 다른 해시
  정규화는 해시에만 적용되고 raw_content는 원본 그대로
  같은 발명에 같은 해시 → 경고 (차단 아님)
  강행 선택 시 정상 저장됨

test_korean_normalization.py          ← §10.4
  조사 제거: 그래핀은→그래핀, 유리기판에서→유리기판
  2자 가드: 정도→정도, 가능→가능, 온도→온도 (잘못 떼지 않음)
  전각/반각, 대소문자, 하이픈 통일
  내장 약어 사전 (TGV ↔ Through Glass Via ↔ 유리관통비아)
  bigram 자카드 유사도 임계값
  사용자 병합 승인 후 synonyms에 원본 표기가 보존됨 (분리 가능)

test_importance_scoring.py            ← §11.1.1, §11.3
  ImportanceBreakdown의 contributions 합 == total
  원자값만으로 가중치를 바꿔 재계산 가능
  weights_version이 함께 저장됨
  user_rejected만 있는 요소는 user_emphasis가 0
  화자 미상이면 u 가중치 0 + 나머지 재정규화

test_conversation_overlap.py          ← §6.5, 재복사 대응
  1~20 뒤에 1~35를 넣으면 superset으로 판정
  신규 구간 [20..34]만 분석 대상이 됨
  raw_content에는 전체 1~35가 그대로 저장됨
  순서가 안 맞게 겹치면 partial_overlap
  겹침이 없으면 unrelated → 전체 분석
  살짝 편집된 메시지는 modified로 분류 (자동 수정 안 함)
  이전 분석 결과는 재복사로 변경되지 않음

test_rolling_summary_chain.py         ← §5.2.2
  #1의 after_hash가 #2의 before_hash와 일치
  체인이 끊기면 verify_summary_chain이 해당 id를 반환
  중간 대화 Soft Delete 시 후속이 needs_regeneration이 됨
  재생성 후 체인이 다시 ok가 됨
  요약 재생성이 AI 호출 없이 검증만으로 판단됨

test_conversation_delete.py           ← §28
  기본 삭제는 deleted_at만 채우고 raw_content 보존
  삭제해도 본문/Revision/Timeline은 되돌아가지 않음
  삭제 전 영향 범위(Revision/Timeline/요소 수)가 정확히 계산됨
  체인 중간 삭제 시 후속 요약이 needs_regeneration
  발명 purge 시 대화가 CASCADE 삭제됨
  발명 휴지통 이동 시 대화도 함께 숨겨짐
  영구 삭제는 휴지통에 있는 대화만 대상
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
- `st.tabs` 도입 후 기존 상세 화면 E2E 셀렉터
- 새 테이블 추가 후 기존 마이그레이션 테스트
- 새 컬럼(`attachments.notes`, `inventions.idea_candidates`) 추가 후
  기존 백업/무결성 검사 테스트

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

### 23.0 0.5.0-alpha — 첫 릴리스 목표 (이 흐름까지만 완결)

alpha는 **아래 한 줄 흐름이 끝까지 동작하는 것**만 목표로 한다.
여기서 멈추고 실사용 피드백을 받은 뒤 나머지를 붙인다.

```
대화 붙여넣기
  → 원문 저장 (raw_content + hash, 중복 경고)
  → 발명 선택 (신규 / 현재 / 파생 / 다른 발명)
  → 분석 (map/reduce)
  → 기존 내용과 비교
  → 신규·구체화·중복·충돌 분류
  → 사용자 항목별 승인
  → Revision 생성
  → 본문 반영
  → Timeline 기록 (layer=idea)
  → 대화 목록 및 회차 표시
```

**alpha의 인포그래픽은 6개뿐이다.**

- 총 대화 수
- 상위 개념 (중요도 순 목록)
- 최근 새 개념
- 미해결 질문
- 대화별 변화 요약 (새 개념 N · 수정 N · 중복 N)
- 간단한 막대그래프 (`st.bar_chart` 1개)

**alpha에서 하지 않는 것**: 관계도, 자동 이미지 분석, 발전 타임라인
시각화(데이터는 쌓되 화면은 뒤로), 후보 방법 상태 관리 UI, 성숙도 별점.

### 23.1 0.5.0 정식 — 반드시 구현

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
| **0** | **`analysis_schema.py` + `hashing.py` (§26, §27)** | **데이터 계약이 고정된다 — 코드보다 먼저** |
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

### R5. DB 크기 증가 (`raw_content` + `analysis_json`)

원문을 DB 컬럼에 넣기로 했고(§6.2), 대화 20개 × 요소 200개면
`analysis_json`도 커진다.

**대응**
- `analysis_json`은 **요약·참조만** 담는다 (excerpt 200자 제한).
  원문 전체를 JSON에 중복 저장하지 않는다 — 원문은 `raw_content`에만 있다.
- 대화당 JSON 상한 목표 100KB
- 예상 DB 크기: 대화 50KB × 20건 × 발명 100건 ≈ 100MB (SQLite 무리 없음)
- **재검토 기준**: DB 500MB 초과 시 `raw_content` zlib 압축 검토 (§6.2),
  `analysis_json` 비대화 시 §17 테이블 승격 신호로 본다

### R11. 스키마 계약이 지켜지지 않고 무너짐

`analysis_json`을 자유 형식으로 쓰기 시작하면 6개월 뒤 구조를 알 수
없게 되고, 테이블 승격(§17)도 불가능해진다.

**대응**
- 접근자 계층 강제 (§26.4) — JSON 키는 `analysis_schema.py`에만 존재
- **grep 테스트로 위반을 자동 검출** (§26.6)
- 필드 삭제 금지, 추가만 (§26.1)
- 구현 순서에서 **0단계**로 못 박음 (§23.4) — 코드보다 먼저 확정

### R12. 재분석이 사용자 판단을 지움

이게 깨지면 **재분석 기능 자체를 아무도 쓰지 않는다.** 대화 12개짜리
발명에서 예전에 거절한 제안 40개를 매번 다시 검토할 수는 없다.

**대응**
- `ai_analysis` / `user_review` / `application_result` 3계층 분리 (§27.1)
- 내용 기반 `item_id`로 재분석을 견디는 식별자 확보 (§27.2)
- 재분석 결과에 없는 판단도 `orphaned_decisions`로 보관 (삭제 금지)
- `test_analysis_user_review.py`로 회귀 고정 (§22.2)

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

## 26. analysis_json 스키마 계약

> `analysis_json`을 **자유 형식 JSON으로 쓰지 않는다.** JSON을 단순
> 저장소로 쓰면 필드가 조금씩 늘고 이름이 흔들리다가, 1년 뒤에는
> 어느 키가 언제 생겼는지 아무도 모르는 상태가 된다. 테이블을 나중에
> 만들 수 있는 것도 **지금 스키마가 정확할 때만** 가능하다.

### 26.1 세 가지 절대 규칙

1. **JSON 키 문자열은 `analysis_schema.py` 밖에 등장하지 않는다.**
   UI와 서비스는 접근자 메서드만 쓴다 (§26.4). 테스트로 강제한다 (§26.6).
2. **필드를 삭제하지 않는다.** 추가만 한다. 쓰지 않게 된 필드는
   `deprecated`로 표시하고 읽기는 계속 지원한다.
3. **읽을 때 없는 필드는 기본값으로 채운다.** 과거 버전 JSON이
   들어와도 절대 `KeyError`가 나지 않는다.

### 26.2 최상위 구조

```json
{
  "schema_version": "1.0",
  "analysis_version": 1,
  "provider": "mock",
  "model": null,
  "prompt_version": "conversation-analysis-1.0",
  "synonym_dict_version": 3,
  "analyzed_at": "2026-08-10T12:00:00Z",

  "messages": [
    {"message_index": 0, "role": "user",
     "content_hash": "sha256:...", "source_start": 0, "source_end": 412,
     "source_excerpt": "유리 기판에 홀을 뚫는 방법을..."},
    {"message_index": 1, "role": "assistant",
     "content_hash": "sha256:...", "source_start": 412, "source_end": 2038}
  ],

  "overlap": {
    "match_type": "superset",
    "overlap_with_import_id": "conv-uuid-1",
    "already_imported_indices": [0, 1, 2],
    "newly_added_indices": [3, 4, 5],
    "modified_indices": [],
    "analyzed_range": [3, 5]
  },

  "ai_analysis": {
    "new_elements":         [],
    "reinforced_elements":  [],
    "modified_elements":    [],
    "conflicting_elements": [],
    "rejected_elements":    [],
    "open_questions":       [],
    "source_references":    [],
    "merge_proposals":      []
  },

  "user_review": {
    "decisions": [],
    "edits":     [],
    "notes":     ""
  },

  "application_result": {
    "applied_items": [],
    "revision_id":   null,
    "event_ids":     [],
    "applied_at":    null
  }
}
```

3계층으로 나눈 이유는 §27에 있다 — 요약하면 **재분석 시
`ai_analysis`만 교체되고 `user_review`는 살아남아야 하기 때문**이다.

| 최상위 키 | 의미 | 재분석 시 |
|---|---|---|
| `schema_version` | 이 JSON의 구조 버전 | 최신으로 갱신 |
| `analysis_version` | 이 대화를 몇 번째로 분석했는가 | +1 |
| `provider` / `model` / `prompt_version` | 무엇으로 분석했는가 | 갱신 |
| `synonym_dict_version` | 어떤 동의어 사전으로 정규화했는가 (§27.2.2) | 갱신 |
| `messages` | 메시지 분리 결과 (내용은 없고 해시·offset만) | 유지 |
| `overlap` | 부분 중복 판정 결과 (§6.5) | 유지 |
| `ai_analysis` | AI가 만든 것 | **통째로 교체** |
| `user_review` | 사람이 판단한 것 | **보존 + 이어받기** |
| `application_result` | 실제 반영 결과 | 보존 (새 반영 시 추가) |

**`messages`에 내용(text)을 넣지 않는 이유**: 원문은 `raw_content`에
이미 완전히 있다. 여기 또 넣으면 JSON이 두 배가 되고 두 사본이
어긋날 수 있다. `source_start`/`source_end`로 언제든 원문에서 잘라
쓸 수 있으므로 **해시와 위치만** 보존한다.
`source_excerpt`는 디버깅·표시 편의를 위한 선택 항목이다(앞 100자).

### 26.3 항목의 공통 형태

`ai_analysis`의 모든 배열 원소는 같은 뼈대를 갖는다.

```json
{
  "item_id": "a3f2c8d1e5b70942",
  "kind": "tech",
  "text": "그래핀 섬유를 장력 상태로 관통 배치",
  "normalized_text": "그래핀섬유를 장력 상태로 관통 배치",
  "target_field": "core_principle",
  "confidence": 94,
  "rationale": "사용자가 대화 #4에서 반복해서 강조",

  "origin_stance": "user_proposed",
  "declared_status": "proposed",
  "derived_status": ["newly_proposed"],

  "supersedes_item_id": null,
  "related_previous_item_id": "b1c9e70a34f2d558",
  "match_type": "similar",
  "similarity_score": 0.91,

  "sources": [
    {
      "conversation_import_id": "conv-uuid",
      "sequence_no": 4,
      "message_index": 12,
      "message_role": "user",
      "source_excerpt": "그래핀 실을 그대로 당긴 채로...",
      "source_start": 18422,
      "source_end": 18461,
      "confidence": 94
    }
  ]
}
```

### 26.4 접근자 계층

```python
# src/conversations/analysis_schema.py

CURRENT_SCHEMA_VERSION = "1.0"
CURRENT_PROMPT_VERSION = "conversation-analysis-1.0"


class AnalysisDocument:
    """analysis_json에 접근하는 유일한 경로.

    UI와 서비스는 JSON 키 문자열을 직접 쓰지 않는다 — 전부 이 클래스의
    메서드를 거친다. 스키마가 바뀌어도 고칠 곳은 이 파일 하나다.
    """

    @classmethod
    def load(cls, raw: dict | None) -> "AnalysisDocument":
        """어떤 버전으로 저장됐든 현재 구조로 올려서 돌려준다."""
        return cls(_upgrade(raw or _empty()))

    def to_json(self) -> dict: ...

    # 읽기 --------------------------------------------------
    def new_elements(self) -> list[AnalysisItem]: ...
    def modified_elements(self) -> list[AnalysisItem]: ...
    def conflicting_elements(self) -> list[AnalysisItem]: ...
    def open_questions(self) -> list[Question]: ...
    def merge_proposals(self) -> list[MergeProposal]: ...
    def pending_items(self) -> list[AnalysisItem]:
        """아직 사용자가 판단하지 않은 항목만."""

    # 사용자 판단 (§27) --------------------------------------
    def approve(self, item_id: str, *, edited_text: str | None = None) -> None: ...
    def reject(self, item_id: str, *, reason: str = "") -> None: ...
    def decision_of(self, item_id: str) -> Decision | None: ...

    # 반영 결과 ----------------------------------------------
    def record_application(self, applied_item_ids: list[str],
                           revision_id: str, event_ids: list[str]) -> None: ...

    # 재분석 -------------------------------------------------
    def replace_ai_analysis(self, new_ai: dict) -> "AnalysisDocument":
        """AI 결과만 갈아끼우고 사용자 판단은 이어받는다 (§27.3)."""
```

**DB와의 접점도 이 파일에만 둔다.** TEXT 컬럼과 문서 사이를 오가는
함수는 두 개뿐이다.

```python
def dumps_analysis(doc) -> str | None:
    """TEXT 컬럼에 넣을 문자열. 직렬화 옵션이 계약의 일부다."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def loads_analysis(text: str | None) -> AnalysisDocument:
    """깨진 JSON이 저장돼 있어도 예외를 던지지 않는다.

    대화 목록을 여는 것만으로 앱 전체가 멈추면 안 된다. 해석에 실패하면
    원문 문자열을 `_unmigrated_raw.corrupted_text`에 그대로 담아 돌려주므로
    나중에 손으로 복구할 수 있다.
    """
```

| 옵션 | 없으면 생기는 일 |
|---|---|
| `ensure_ascii=False` | 한글이 `\uXXXX`로 부풀어 DB를 열어도 못 읽는다 |
| `sort_keys=True` | 내용이 같은데 문자열이 달라져 변경 감지가 어긋난다 |
| `separators=(",", ":")` | 불필요한 공백이 끼어 같은 문제가 생긴다 |

### 26.5 버전 마이그레이션 체인

```python
_MIGRATIONS: dict[str, Callable[[dict], dict]] = {
    # "1.0": _migrate_1_0_to_1_1,     ← 다음 버전이 생기면 여기 추가
}

def _upgrade(raw: dict) -> dict:
    version = raw.get("schema_version", "0.9")   # 버전이 없으면 최초 형식
    seen = set()
    while version != CURRENT_SCHEMA_VERSION:
        if version in seen or version not in _MIGRATIONS:
            # 알 수 없는 버전 — 실패하지 않고 빈 구조 + 원본 보관
            logger.warning("알 수 없는 analysis_json 버전: %s", version)
            return _wrap_unknown(raw)
        seen.add(version)
        raw = _MIGRATIONS[version](raw)
        version = raw["schema_version"]
    return raw
```

**알 수 없는 버전을 만나도 예외를 던지지 않는다.** 원본을
`_unmigrated_raw`에 통째로 보관하고 빈 구조를 돌려준다 — 미래 버전으로
저장된 DB를 구버전 앱에서 열어도 데이터가 사라지지 않는다.

### 26.6 규칙을 테스트로 강제

```python
def test_analysis_json_keys_are_not_referenced_outside_schema_module():
    """analysis_json의 키를 다른 파일에서 직접 문자열로 쓰지 않는다.

    이 테스트가 깨지면 접근자 계층을 우회한 것이다 — 스키마를 바꿀 때
    고쳐야 할 곳이 여기저기 흩어지기 시작한다는 신호다.
    """
    guarded = {"ai_analysis", "user_review", "application_result",
               "new_elements", "reinforced_elements", "modified_elements",
               "conflicting_elements", "rejected_elements",
               "open_questions", "source_references", "merge_proposals"}
    for path in Path("src").rglob("*.py"):
        if path.name == "analysis_schema.py":
            continue
        text = path.read_text(encoding="utf-8")
        for key in guarded:
            assert f'"{key}"' not in text, f"{path}에서 {key}를 직접 참조"
```

---

## 27. AI 분석과 사용자 판단 분리

### 27.1 다섯 가지 상태를 구분한다

| 상태 | 저장 위치 |
|---|---|
| AI가 추출한 내용 | `ai_analysis.*` |
| 사용자가 **승인**한 내용 | `user_review.decisions[status="approved"]` |
| 사용자가 **수정**한 내용 | `user_review.edits[]` |
| 사용자가 **거절**한 내용 | `user_review.decisions[status="rejected"]` |
| 실제 **본문에 반영**된 내용 | `application_result.applied_items[]` |

**승인 ≠ 반영이다.** 사용자가 승인해도 (a) 중복으로 판정되어
건너뛰거나, (b) 트랜잭션이 실패하거나, (c) 다른 항목과 충돌해
보류될 수 있다. 그래서 `application_result`가 따로 있어야
"내가 승인한 것이 실제로 들어갔는가"를 확인할 수 있다.

```json
"user_review": {
  "decisions": [
    {"item_id": "a3f2c8d1", "status": "approved",
     "decided_at": "2026-08-10T12:05:00Z"},
    {"item_id": "b7e1a409", "status": "rejected",
     "reason": "이미 다른 방식으로 정리함",
     "decided_at": "2026-08-10T12:06:00Z"}
  ],
  "edits": [
    {"item_id": "c2d8f513",
     "original_text": "레이저로 유리를 가공한다",
     "edited_text": "펨토초 레이저로 유리를 개질한 뒤 식각한다",
     "edited_at": "2026-08-10T12:07:00Z"}
  ],
  "notes": ""
}
```

### 27.2 item_id — 재분석을 견디는 안정적 식별자

사용자 판단을 보존하려면 **재분석해도 같은 제안이 같은 id를 가져야
한다.** uuid를 새로 만들면 매번 다른 id가 되어 판단을 이어받을 수 없다.

**내용 기반 해시로 만든다.**

```
item_id = sha256(change_type | target_field | normalized_text)[:16]
```

#### 27.2.1 normalized_text 정규화 9단계

표현만 살짝 다른 같은 제안이 다른 id가 되지 않도록, 해시 계산 전에
아래 순서로 정규화한다. **표시용 `text`는 원문 그대로 보존한다.**

**이 순서 자체가 계약이다.** 순서를 바꾸면 같은 제안이 다른 id를 갖게
되어 과거 사용자 판단이 전부 고아가 된다.

```
1.   Unicode NFKC
2.   영문 소문자화
3.   줄바꿈·공백 통합
4.   문장부호·목록기호 제거
4.5  한국어 조사 제거
5.   내장 약어·대표 용어 치환
6.   사용자 동의어 치환
6.5  한국어 조사 재제거
7.   군더더기·반복 표현 정리
```

구현: `src/conversations/hashing.py::normalize_item_text()`

| 단계 | 흡수하는 차이 |
|---|---|
| 1 NFKC | `"（Ａ）"` ↔ `"(A)"` — **전각 문장부호를 4단계가 지울 수 있게 먼저** |
| 2 소문자 | `"Graphene Fiber"` ↔ `"graphene fiber"` |
| 3 공백 | `"A  B"` ↔ `"A B"` ↔ `"A\nB"` |
| 4 문장부호·목록기호 | `"- 그래핀 섬유."` ↔ `"그래핀 섬유"` |
| 4.5 조사 | `"그래핀은"` ↔ `"그래핀"` |
| 5 대표 용어 | `"Through Glass Via"` ↔ `"TGV"` |
| 6 사용자 동의어 | `"그래핀 실"` ↔ `"그래핀 섬유"` |
| 6.5 조사 재제거 | `"그래핀 섬유을"` → `"그래핀 섬유"` (치환이 만든 어색한 조사) |
| 7 반복·군더더기 | `"결국 그래핀 섬유"` ↔ `"그래핀 섬유"` |

**1·2단계가 3·4단계보다 앞인 이유**: NFKC가 전각 문장부호(`．` `，`
`（`)를 ASCII로 바꾼 **뒤에** 문장부호를 지워야 전각도 걸린다. 반대
순서면 전각 문장부호가 살아남아 `"그래핀 섬유．"`와 `"그래핀 섬유."`가
다른 id가 된다.

**조사 제거 안전 원칙** (§10.4의 규칙을 여기서도 그대로 따른다)

- 최소 어간 길이 **2자** — 떼고 남는 어간이 2자 미만이면 떼지 않는다
- **과잉 제거보다 미제거를 우선한다** — 잘못 뗀 것은 되돌릴 방법이 없다
- `정도` · `온도` · `재료` · `유리` 같은 일반 명사를 훼손하지 않는다
  (전부 2자 가드에 걸려 보존된다)
- 사용자 동의어 치환 뒤 조사 형태가 어색해진 경우는 **6.5단계**가 처리한다

**왜 조사를 두 번 떼는가** — 한국어 조사는 앞 음절의 받침에 따라
형태가 바뀌기 때문에, 조사를 남긴 채 동의어를 치환하면 반드시 어긋난다.

```
"그래핀 실을 사용"    → 6단계 치환 → "그래핀 섬유을 사용"   (받침 있음 → 을)
"그래핀 섬유를 사용"  → 치환 없음   → "그래핀 섬유를 사용"   (받침 없음 → 를)
                     → 같은 뜻인데 item_id가 다르다
```

4.5단계만으로는 이 예가 해결되지 않는다. `"실을"`은 떼고 남는 어간이
1자(`"실"`)라 2자 가드가 막기 때문이다. 치환으로 `"섬유을"`이 되고
나서야 어간이 2자가 되어 뗄 수 있다. **두 번 돌리면 양쪽 모두
`"그래핀 섬유 사용"`으로 수렴한다.**

#### 27.2.2 함정 — 동의어 사전이 바뀌면 item_id가 바뀐다

6단계에서 **사용자 동의어 사전을 쓰기 때문에**, 사용자가 나중에
`"전도성 섬유"`를 `"그래핀 섬유"`에 병합하면 **과거 item_id가 전부
달라진다.** 아무 대비 없이 두면 그 순간 모든 사용자 판단이 고아가 된다.

**`synonym_dict_version`은 해시 입력에 넣지 않는다.**

```
item_id = sha256(change_type | target_field | normalized_text)[:16]
```

넣고 싶은 유혹이 있지만 넣으면 안 된다 — 사전을 한 번 고치는 순간
**내용이 전혀 바뀌지 않은 항목까지 전부 새 id를 갖게 되어**, remap이
막으려던 바로 그 사고가 사전을 고칠 때마다 일어난다. 사전이 실제로
영향을 준 항목은 5·6단계 **결과**가 달라져 자연히 다른 id가 되고,
영향받지 않은 항목은 id가 그대로 유지되어야 한다.

버전은 대신 다음 네 가지에만 쓴다.

1. **추적** — 이 분석이 어떤 사전으로 정규화됐는지 기록
   (`analysis_json.synonym_dict_version`, §26.2)
2. **변경 감지** — 저장된 버전과 현재 버전을 비교해 remap 필요 여부 판단
3. **결정론적 Remap 실행** — AI 호출 없이 `(old_item_id → new_item_id)`
   매핑을 계산해 `user_review`의 판단을 옮긴다
4. **충돌 보고** — 옮길 수 없는 경우를 사용자에게 보여준다

사전이 바뀌어도 즉시 재계산하지 않는다. 다음에 그 발명을 열 때
**일괄 remap**을 한 번 수행한다.

```python
def remap_item_ids(items, decisions, new_synonym_map, new_version):
    """동의어 사전이 바뀌었을 때 판단을 새 item_id로 옮긴다.

    판단이 서로 일치할 때만 자동 이관한다. 옛 id 둘이 새 id 하나로
    합쳐지는데 판단이 서로 다르면(하나는 승인, 하나는 거부) 아무것도
    옮기지 않고 conflicts로 돌려준다 — 사용자가 직접 고른다.
    """
```

구현: `src/conversations/hashing.py::remap_item_ids()` →
`RemapResult(mapping, migrated, conflicts, unchanged)`

이 remap은 **결정론적이고 AI 호출이 없다.** 사전 버전만 비교하면
언제 돌려야 하는지 알 수 있다.

#### 27.2.3 의미는 같지만 문장이 바뀐 경우

정규화로도 못 잡는 경우가 있다 — AI가 아예 다시 쓴 문장이다.

```
분석 #1: "그래핀 섬유를 장력 상태로 관통 배치한다"
분석 #2: "장력을 유지한 그래핀 섬유를 유리에 관통시켜 배치한다"
        → normalized_text가 달라 item_id도 다름
```

이때를 위해 항목에 관계 메타데이터를 붙인다 (§26.3).

| 필드 | 의미 |
|---|---|
| `related_previous_item_id` | 이전 분석에서 가장 유사했던 항목 |
| `similarity_score` | 그 유사도 (TF-IDF, 0~1) |
| `match_type` | `exact` / `similar` / `new` |
| `supersedes_item_id` | 이 항목이 이전 항목을 **대체**한다고 사용자가 확정한 경우 |

`related_previous_item_id`와 `similarity_score`는 **시스템이 자동으로
채우지만, 판단을 자동으로 복사하지는 않는다** — §27.3의 규칙을 따른다.
`supersedes_item_id`는 사용자가 "이건 그때 그 항목의 수정본이다"라고
확인했을 때만 채워진다.

### 27.3 재분석 병합 규칙

**세 등급으로 나눈다. 유사하다는 이유만으로 승인을 자동 복사하지 않는다.**

| 등급 | 조건 | 동작 | 사용자에게 |
|---|---|---|---|
| **1. 동일** | `item_id` 일치 | 이전 판단 **그대로 유지** | 묻지 않음 |
| **2. 유사** | id는 다르나 유사도 ≥ 0.85 | **미판단 상태**로 두고 이전 항목을 나란히 제시 | **"같은 항목인가요?" 질문** |
| **3. 신규** | 유사한 이전 항목 없음 | 미판단 상태 | 새 항목으로 검토 |

```python
SIMILAR_THRESHOLD = 0.85

def merge_after_reanalysis(old: AnalysisDocument,
                           new_ai: dict) -> AnalysisDocument:
    old_decisions = {d.item_id: d for d in old.decisions()}
    for item in _iter_items(new_ai):
        if item.item_id in old_decisions:
            item.carried_over = True                    # 1등급
            item.match_type = "exact"
            continue
        prev, score = old.most_similar_item(item.text)  # TF-IDF
        if prev and score >= SIMILAR_THRESHOLD:
            item.related_previous_item_id = prev.item_id
            item.similarity_score = score
            item.match_type = "similar"                 # 2등급
            item.carried_over = False   # ← 판단을 복사하지 않는다
        else:
            item.match_type = "new"                     # 3등급
    ...
```

**2등급에서 판단을 자동 복사하지 않는 이유**: 유사도 0.87은 "거의 같다"가
아니라 "꽤 비슷하다"일 뿐이다. `"상온에서 삽입한다"`와
`"상온에서 삽입하지 않는다"`는 TF-IDF 유사도가 매우 높다. 여기서 이전
승인을 자동으로 옮기면 **사용자가 승인한 적 없는 내용이 본문에 들어간다.**

이전 판단 중 재분석 결과에 없는 id는 삭제하지 않고
`user_review.orphaned_decisions`로 옮겨 보관한다.

**1등급이 이 설계의 실질적 가치다.** 대화 12개짜리 발명을 재분석할
때마다 예전에 거절한 제안 40개를 다시 검토하라고 하면 아무도 재분석을
쓰지 않는다.

### 27.4 화면 표시

```
대화 #4 재분석 결과 (분석 #2)

▼ 새 항목 3                       ← 3등급. 이것만 새로 판단하면 된다
  ☑ 핵심 아이디어 ← ...                              신뢰 94  👤 사용자 제안

▼ 이전 항목의 수정본으로 보임 2    ← 2등급. 판단이 필요하다
  ☐ 작동 원리 ← "장력을 유지한 그래핀 섬유를 유리에 관통시켜 배치"
     ⓘ 분석 #1의 아래 항목과 91% 유사합니다.
        이전: "그래핀 섬유를 장력 상태로 관통 배치한다"  ✅ 승인됨

        이 둘은 같은 항목입니까?
         ○ 같은 항목 — 이전 승인을 이어받고 새 문장으로 대체
         ○ 다른 항목 — 별도로 검토
         ● 아직 판단 안 함        ← 기본값

▼ 이전 판단 유지 5                ← 1등급. 접혀 있음
  ✅ 승인됨  작동 원리 ← ...          (분석 #1에서 승인)
  ❌ 거절됨  예상 효과 ← ...          (분석 #1에서 거절: "근거 부족")
     [다시 판단하기]

▼ 이전 분석에만 있던 항목 2        ← 접혀 있음, 참고용
  이번 분석에서는 나오지 않았습니다. 판단 기록은 보존됩니다.
```

"같은 항목"을 선택하면 `supersedes_item_id`가 채워지고 이전 승인이
새 항목으로 옮겨진다. **이건 사용자가 명시적으로 누른 결과이지
시스템의 추정이 아니다.**

### 27.5 왜 이게 중요한가

원칙 2("AI 분석과 사용자가 승인한 내용을 구분한다")는 표시상의 문제가
아니라 **데이터 구조의 문제**다. 한 곳에 섞어 저장하면:

- 재분석이 사용자 판단을 지운다 → 재분석 기능을 못 쓴다
- "AI가 그렇게 말했다"와 "내가 그렇게 판단했다"를 구분할 수 없다 →
  특허 출원 시 발명자의 판단 근거를 증명할 수 없다
- 나중에 AI 품질을 평가할 수 없다 (승인율/거절율을 계산할 수 없다)

마지막 항목은 부수 효과지만 실제로 유용하다 — **승인율이 낮은
`change_type`이나 낮은 신뢰도 구간을 찾아 프롬프트를 개선**할 수 있다.

---

## 28. ConversationImport 삭제 정책

### 28.1 기본은 Soft Delete

발명과 같은 정책이다 (`0.4.0`의 휴지통, `deleted_at` 컬럼).
**대화 원문은 발명 착상의 근거이므로 쉽게 지워지면 안 된다.**

| 동작 | 결과 |
|---|---|
| 삭제 (기본) | `deleted_at` 기록. 목록에서 숨김. `raw_content`·분석·체인 **전부 보존** |
| 복원 | `deleted_at = NULL` |
| 영구 삭제 | 행 자체 제거. **설정 화면의 고급 작업에서만** (§28.4) |

**이미 본문에 반영된 대화를 삭제해도 본문은 되돌아가지 않는다.**
반영은 Revision과 Timeline에 남은 별개의 사건이기 때문이다.
사용자가 본문을 되돌리려면 Revision에서 복원해야 한다 — 삭제 시
이 점을 명확히 안내한다.

### 28.2 삭제 전 영향 범위 표시

```
대화 #3을 삭제하시겠습니까?

  이 대화가 만든 것
    · 본문 변경 6개 항목 (Revision #7)
    · Timeline 이벤트 9건
    · 아이디어 요소 12개 (그중 3개는 이 대화에서만 등장)

  ⚠️ 요약 체인 영향
    이 대화는 요약 체인의 중간입니다.
    대화 #4~#7의 누적 요약이 이 대화를 전제로 만들어졌습니다.

  삭제해도 본문 변경과 Timeline은 되돌아가지 않습니다.
  본문을 되돌리려면 변경 이력에서 Revision #7 이전으로 복원하세요.

  ● 휴지통으로 이동 (기본)
  ○ 취소
```

영향 범위는 전부 **조회로 계산**한다 — `created_revision_id`,
`created_event_id`, Timeline의 `meta.conversation_import_id` 역참조,
`analysis_json`의 요소 목록.

### 28.3 요약 체인 중간이 삭제될 때

체인(§5.2.2)의 중간 고리가 사라지면 후속 요약의 근거가 무너진다.

```
#1 → #2 → #3 → #4 → #5
           ↑
        삭제됨 → #4, #5의 요약은 "#3까지 반영"을 전제로 만들어졌다
```

**세 가지 처리 중 우리가 택하는 것: (b) 표시 + 재생성 제공**

| 방식 | 채택 | 이유 |
|---|---|---|
| (a) 삭제 차단 | ✗ | 사용자가 지울 수 없는 데이터가 생긴다 |
| **(b) 후속 요약을 `needs_regeneration`으로 표시** | **✓** | 데이터를 잃지 않으면서 상태를 정직하게 드러낸다 |
| (c) 원문만 숨기고 체인 근거는 보존 | ✓ (b와 병행) | Soft Delete가 이미 이걸 한다 |

Soft Delete는 행을 지우지 않으므로 **`rolling_summary_after_hash`가
그대로 남아 체인 검증은 계속 통과한다.** 즉 (c)가 기본으로 성립한다.
다만 사용자가 "이 대화는 없는 것으로 치고 싶다"는 의도이므로, 후속
요약을 `needs_regeneration`으로 표시해 선택지를 준다.

```python
def mark_chain_after(session, deleted: ConversationImport) -> list[str]:
    """삭제된 대화 이후의 요약을 '재생성 필요'로 표시한다."""
    later = (session.query(ConversationImport)
             .filter(ConversationImport.invention_id == deleted.invention_id,
                     ConversationImport.sequence_no > deleted.sequence_no)
             .order_by(ConversationImport.sequence_no))
    ids = []
    for imp in later:
        imp.summary_chain_status = "needs_regeneration"
        ids.append(imp.id)
    return ids
```

```
ℹ️ 대화 #4~#7의 누적 요약이 재생성이 필요한 상태입니다.
   현재 요약도 계속 사용할 수 있지만, 삭제한 대화의 내용이 포함되어 있습니다.

   [지금 재생성]  (AI 호출 4회 · 약 30초)   [나중에]
```

재생성은 살아 있는 대화만 순서대로 다시 얹어 체인을 새로 만든다.
**원문이 전부 보존되어 있으므로 언제든 가능하다** — 이것이 원칙 1을
지켜서 얻는 실질적 이득이다.

### 28.4 영구 삭제는 고급 작업

설정 화면의 별도 영역에서만, 발명 영구 삭제(`purge`)와 같은 수준의
확인을 거친다.

- 휴지통에 있는 대화만 대상
- 영향 범위를 다시 표시
- `raw_content`가 사라지므로 **재분석·요약 재생성이 영구히 불가능**해짐을 경고
- 발명을 `purge`하면 그 발명의 대화도 `ondelete="CASCADE"`로 함께 삭제

### 28.5 발명 휴지통과의 관계

| 발명 상태 | 대화 |
|---|---|
| 발명이 휴지통으로 이동 | 대화도 함께 숨겨짐 (조회 시 발명 기준으로 필터) |
| 발명 복원 | 대화도 함께 복원 |
| 발명 영구 삭제 | 대화도 CASCADE 삭제 |

대화에 별도의 휴지통 화면을 만들지 않는다 — **대화 기록 탭에서
"삭제된 대화 2건 보기"** 접힘 영역으로 충분하다 (§20.2).

---

## 29. 구현 0단계 완료 조건

> **이 10개가 전부 확정되기 전에는 `0.5.0-dev` 구현을 시작하지 않는다.**
> 각 항목은 (a) 이 문서에 명시되어 있고, (b) 테스트 명세가 적혀 있어야
> 체크할 수 있다.

| # | 계약 | 문서 | 테스트 명세 | 상태 |
|---|---|---|---|---|
| 1 | ConversationImport 컬럼 | §16.2 | `test_conversation_service.py` | ✅ 확정 |
| 2 | analysis_json v1 스키마 | §26.2 | `test_analysis_schema.py` | ✅ 확정 |
| 3 | item_id 생성 규칙 | §27.2 | `test_analysis_user_review.py` | ✅ 확정 |
| 4 | 재분석 판단 보존 규칙 | §27.3 | `test_analysis_user_review.py` | ✅ 확정 |
| 5 | 메시지 중복 판정 규칙 | §6.5 | `test_conversation_overlap.py` | ✅ 확정 |
| 6 | Rolling Summary 체인 규칙 | §5.2.2 | `test_rolling_summary_chain.py` | ✅ 확정 |
| 7 | Source Trace 규칙 | §12 | `test_conversation_traceability.py` | ✅ 확정 |
| 8 | 사용자/AI 발언 가중치 | §9.5, §11.1.1 | `test_importance_scoring.py` | ✅ 확정 |
| 9 | Import Soft Delete 정책 | §28 | `test_conversation_delete.py` | ✅ 확정 |
| 10 | 미래 스키마 호환 정책 | §26.1, §26.5 | `test_analysis_schema.py` | ✅ 확정 |

### 29.1 각 계약의 한 줄 요약

1. **컬럼** — 조회·정렬·필터에 쓰는 값은 전부 정규 컬럼. 분석 내용만 JSON.
2. **스키마** — `schema_version` 필수, 3계층(`ai_analysis`/`user_review`/
   `application_result`) + `messages` + `overlap`.
3. **item_id** — `sha256(change_type|target_field|normalized_text)`,
   정규화 9단계, `synonym_dict_version` 동반 기록(해시 입력 아님).
4. **재분석** — 동일 id는 유지, 유사는 **질문**, 신규는 미검토.
   유사하다고 승인을 자동 복사하지 않는다.
5. **메시지 중복** — 전체 해시(1단계) + 메시지 해시·유사도(2단계).
   `superset`이면 신규 구간만 분석.
6. **요약 체인** — 별도 테이블 없이 `ConversationImport`가 보존.
   `before_hash`/`after_hash`로 체인 검증, 끊기면 재생성 표시.
7. **Source Trace** — offset은 AI가 아니라 앱이 `find()`로 계산.
   못 찾아도 대화번호·역할·메시지번호·발췌는 항상 보장.
8. **발언 가중치** — `user_rejected`는 0.0. AI만 제안한 항목은
   핵심 필드에 자동 제안하지 않음(기본 체크 해제).
9. **삭제** — Soft Delete 기본, 영향 범위 표시, 체인 후속은
   `needs_regeneration`, 영구 삭제는 고급 작업.
10. **호환** — 필드 삭제 금지·추가만, 없는 필드는 기본값,
    미래 버전은 `_unmigrated_raw`에 원본 보존, JSON 키는
    `analysis_schema.py`에만 존재(grep 테스트로 강제).

### 29.2 0단계에서 실제로 작성할 것

구현 착수가 결정되면 **코드보다 이것부터** 만든다.

```
src/conversations/analysis_schema.py    스키마 + 접근자 + 마이그레이션
src/conversations/hashing.py            원문/메시지 해시 + item_id + 정규화
tests/test_analysis_schema.py           §26 계약 고정
tests/test_analysis_user_review.py      §27 계약 고정
tests/test_conversation_hashing.py      §6.4, §27.2 계약 고정
```

이 5개 파일이 통과하면 **데이터 계약이 코드로 고정된 것**이고,
그 위에 파서·서비스·UI를 올리는 것은 되돌리기 쉬운 작업이 된다.

### 29.3 아직 결정되지 않은 것 (구현 전 확인 필요)

| 항목 | 선택지 | 기본 제안 |
|---|---|---|
| `dormant` 판정 기준 회차 | 3 / 5 / 대화 간격 기반 | **3회차** |
| 유사 판정 임계값 | 0.80 / 0.85 / 0.90 | **0.85** (§27.3) |
| 재복사 판정 최소 겹침 | 3개 / 5개 메시지 | **3개** (§6.5.2) |
| 분석 분량 상한 | 30만 자 / 무제한 | **30만 자 + 경고** |
| 중요도 가중치 v1 | §11.2 값 | UAT 후 조정 |

전부 상수 한 곳(`src/conversations/constants.py`)에 두어 실사용
피드백으로 조정할 수 있게 한다.

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
