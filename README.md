# InventOS

발명가를 위한 AI 운영체제 — MVP

> InventOS는 "특허 관리 프로그램"이 아니라 "생각이 발전하는 과정을 기록하는
> 시스템"입니다. 아이디어를 저장하는 것보다, 그 아이디어가 시간이 지나며
> 어떻게 발전했는지를 기록하는 것이 더 중요합니다.

## 핵심 사용자 흐름

```text
새 아이디어 빠르게 기록 (메모 한 줄이면 저장 가능, 제목은 자동 생성)
  → 필요할 때 내용 구체화 (해결하려는 문제 / 핵심 원리 / 실험 기록 등)
  → AI 검색어 생성 또는 수동 검색어 입력
  → 비슷한 기술(선행특허) 검색 (Mock / KIPRIS Plus / 수동 등록)
  → 검색 결과에서 특허 선택 → 발명에 연결 (초록 원문 보관)
  → 같은 점 / 다른 점 / 차별화 아이디어 기록
  → 버전 저장, Timeline에서 발전 과정 확인
  → Markdown 발명노트 내보내기
```

특허 API 또는 AI API가 설정되지 않아도 발명 기록·수동 특허 등록·비교
기록·Markdown 내보내기는 항상 정상 동작합니다.

## 발명은 문서가 아니라 "발전하는 객체"

하나의 발명은 아이디어 → 실험 → 문제 발견 → 개선안 → 특허 검토처럼
시간에 따라 계속 발전합니다. 그래서 데이터 모델도 "발명 = 필드가 많은
문서 한 건"이 아니라, 서로 분리된 여러 객체가 하나의 발명 아래 쌓이는
구조로 되어 있습니다.

| 객체 | 역할 |
|---|---|
| `Invention.original_idea` | 최초 원본 메모. AI 정리나 내용 구체화로 절대 덮어쓰지 않는다 |
| `InventionRevision` | 원본/본문을 고칠 때마다 자동으로 남는 스냅샷 (되돌리기용) |
| `InventionEvent` (Timeline) | "무슨 일이 있었는지"를 시간순으로 보여주는 자동 기록 |
| `InventionAIResult` | AI가 만든 결과(정리/개선안 등). 사용자가 '반영'을 눌러야만 발명 내용에 복사된다 |
| `Experiment` | 실험 날짜/조건/결과/실패 원인/개선 아이디어 — 발명 본문과 동등하게 중요한 1급 데이터 |
| `Tag` / `InventionTag` | 중복 없이 관리하는 태그 사전 (문자열을 발명마다 따로 들고 있지 않음) |
| `Invention.parent_invention_id` | 파생 아이디어(부모→자식) 관계. 예: Separator 접합 → Graphene Fiber 방식 |

파생 아이디어 관계는 지금 UI에 노출하지 않지만 `InventionService.create_child()` /
`list_children()`으로 이미 동작합니다.

## 기술 스택

- UI: Streamlit
- Backend: Python 3.11+
- Database: SQLite (SQLAlchemy 2.0 ORM) + FTS5 통합 검색
- HTTP: httpx
- 특허 검색: KIPRIS Plus (선택), Mock(데모), 수동 등록 — `PatentProvider` 인터페이스로 교체 가능
- AI: Anthropic Claude (선택), Mock — `AIProvider` 인터페이스로 교체 가능

## 아키텍처: 계층 분리 원칙

지금은 Streamlit 안에서 화면을 그리지만, 나중에 React/Next.js + FastAPI 같은
구조로 옮기기 쉽도록 세 계층을 처음부터 분리해 두었습니다.

```text
src/ui/pages/*.py       ← UI (Streamlit). 화면 조합만 하고 비즈니스 규칙을 넣지 않는다.
src/{도메인}/service.py  ← Business Logic. 검증·트랜잭션·Timeline 기록이 전부 여기 있다.
src/database/models.py  ← Database (SQLAlchemy ORM). 테이블 정의만 담당한다.
```

지켜야 하는 규칙:

- **UI는 서비스 계층만 호출한다.** `src/ui/pages/*.py`는 절대 SQLAlchemy 쿼리를
  직접 만들지 않고, `InventionService`/`PatentService`/`TagService` 같은
  서비스 객체를 통해서만 데이터에 접근한다.
- **서비스 계층은 Streamlit을 모른다.** `src/inventions`, `src/patents`,
  `src/ai`, `src/tags`, `src/timeline`, `src/experiments`, `src/search` 등은
  `import streamlit`을 하지 않는다 — 나중에 이 계층을 그대로 FastAPI 라우터
  뒤에 붙일 수 있어야 한다.
- **DB 세션 하나 = 논리적 트랜잭션 하나.** `src/ui/components/actions.py`의
  `run_and_rerun()`이 "쓰기를 완전히 끝내고 커밋한 뒤에만 화면을 새로고침"하는
  규칙을 강제한다 (Streamlit의 `st.rerun()`을 세션이 열린 채로 부르면 방금
  저장한 내용이 커밋되지 않고 사라지는 문제가 있었다 — 이 헬퍼로 고쳤다).

## 설치 및 실행

### 1. Python 설치 확인

Python 3.11 이상이 필요합니다.

```bash
python --version
```

### 2. 가상환경 생성 및 패키지 설치

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. (선택) 환경변수 설정

API 키를 사용하려면 `.env.example`을 `.env`로 복사한 뒤 값을 채워 넣습니다.
API 키가 없어도 프로그램은 정상 동작합니다 (Mock 데이터로 대체).

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

`.env` 주요 항목:

| 변수 | 설명 |
|---|---|
| `INVENTOS_DATA_DIR` | 데이터 저장 경로 (기본값: `./data`) |
| `KIPRIS_API_KEY` | KIPRIS Plus 특허 검색 API 키 |
| `INVENTOS_AI_PROVIDER` | `mock` 또는 `anthropic` |
| `ANTHROPIC_API_KEY` | Claude API 키 (AI 검색어 생성/번역/요약/비교 초안용) |
| `ANTHROPIC_MODEL` | 기본값 `claude-sonnet-5` |

### 4. 실행

```bash
streamlit run app.py
```

브라우저가 자동으로 열리지 않으면 `http://localhost:8501` 로 접속하세요.
기존 DB를 열면 새 컬럼/테이블을 자동으로 추가하고(`run_migrations`), 예전
데이터(상태값, keywords)를 새 구조로 옮깁니다 — 기록은 항상 보존됩니다.

### 5. 테스트 실행

```bash
pytest
```

## 폴더 구조

```text
inventos/
├─ app.py                        # Streamlit 엔트리포인트
├─ src/
│  ├─ config/settings.py         # .env 기반 설정
│  ├─ database/
│  │  ├─ models.py                # SQLAlchemy ORM 전체 모델
│  │  ├─ engine.py                # 엔진/세션 생성
│  │  └─ migrations.py            # 컬럼 추가 + 데이터 마이그레이션 (파괴적 변경 없음)
│  ├─ inventions/                 # 발명 CRUD, 원본 보존, 버전 관리
│  ├─ tags/                       # Tag/InventionTag 서비스
│  ├─ timeline/                   # Timeline(InventionEvent) 자동 기록
│  ├─ experiments/                # 실험 기록 서비스
│  ├─ comments/                   # 팀 협업 대비 Comment 스텁 (UI 미노출)
│  ├─ search/fts.py               # FTS5 통합 검색 색인
│  ├─ drafts/                     # 작성 중 내용 임시 저장
│  ├─ attachments/                # 첨부파일 저장 (종류 분류 포함)
│  ├─ patents/
│  │  ├─ providers/               # PatentProvider (base/manual/mock/kipris/epo_ops/uspto)
│  │  └─ repository.py, service.py, schemas.py
│  ├─ ai/
│  │  ├─ providers/               # AIProvider (anthropic)
│  │  ├─ base.py, mock_provider.py
│  │  └─ results_service.py       # AI 결과 초안(InventionAIResult) 생성/적용
│  ├─ similarity/tfidf.py         # TF-IDF 코사인 유사도
│  ├─ reports/markdown_exporter.py
│  └─ ui/
│     ├─ pages/                   # 홈/빠른기록/목록/상세/특허검색/설정
│     └─ components/              # layout(모바일 CSS), actions(안전한 저장+새로고침)
├─ data/                          # SQLite DB + 첨부파일 (git 제외)
└─ tests/
```

## 데이터 저장 위치

- `data/inventos.db` — SQLite 데이터베이스
- `data/attachments/<invention_id>/` — 첨부 파일 (사진/스케치/PDF/음성/동영상 등)
- `data/drafts.json` — 작성 중인 내용 임시 저장

`data/` 폴더를 백업하면 발명 기록 전체가 보존됩니다.

## Provider 구성

### 특허 Provider (`PatentProvider`)

| Provider | 상태 | 비고 |
|---|---|---|
| Mock | 구현 완료 | API 키 없이 데모 검색 결과 제공 (실제 특허 아님을 명시) |
| 수동 등록 | 구현 완료 | 발명 상세 화면에서 직접 특허 정보 입력 |
| KIPRIS Plus | 구현 완료 (미검증) | `KIPRIS_API_KEY` 필요. 실제 서비스 키로 실시간 검증되지 않았으므로, 사용 전 `src/patents/providers/kipris_provider.py`의 응답 필드 매핑을 재확인하세요 |
| EPO OPS / USPTO | 인터페이스만 존재 | MVP 범위에서 미구현 |

### AI Provider (`AIProvider`)

| Provider | 상태 |
|---|---|
| Mock | 결정론적 규칙 기반, 항상 사용 가능 |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` 설정 시 사용. 검색어 생성/비교 초안은 JSON 스키마로 응답을 강제하며, 초안은 사용자가 '적용' 버튼을 눌러야 저장됩니다 |

AI가 만든 결과는 `InventionAIResult`로 원본과 분리해서 저장되고, `AIResultService.apply()`를
호출해야만 발명 필드로 복사됩니다 — 이 백엔드 구조는 준비되어 있지만, 발명
상세 화면에 "아이디어 정리 / 부족한 부분 찾기" 같은 개별 AI 버튼은 아직
없습니다(다음 단계 작업).

## 통합 검색

제목뿐 아니라 원본 메모, 정리된 발명 내용, 태그, 첨부파일 이름까지 SQLite
FTS5로 한 번에 검색합니다(`src/search/fts.py`). 발명 내용이 바뀔 때마다
색인을 다시 만들고, 기존 DB를 열 때도 색인이 비어 있으면 한 번 자동으로
채웁니다.

## 법적 안내

본 프로그램의 검색 결과, 유사도 및 AI 분석은 발명 검토를 위한 참고자료입니다.
신규성, 진보성, 권리범위 및 특허침해 여부에 대한 법적 판단을 제공하지 않습니다.
특허 출원 또는 사업화 전에는 변리사 등 전문가의 검토가 필요합니다.

## 향후 확장을 위해 준비만 해 둔 것 (UI 없음)

다음은 DB/서비스 구조만 만들어 두고 UI에는 아직 연결하지 않았습니다.
필요해질 때 UI만 추가하면 됩니다.

- **파생 아이디어(부모-자식)**: `Invention.parent_invention_id`,
  `InventionService.create_child()` / `list_children()`
- **공동 발명자/팀 협업**: `Invention.owner_id`(다중 사용자용 자리),
  `InventionComment` + `CommentService`

승인, 팀 공유, 특허 출원 관리, 일정 관리, 작업 할당 같은 나머지 협업 기능은
아직 구조조차 만들지 않았습니다 — 실제로 필요해지는 시점에 설계하는 편이
과도한 설계를 피할 수 있다고 판단했습니다.

## MVP 범위에서 제외된 기능

특허 명세서 자동 작성, 청구항 자동 확정, 특허 침해 자동 판정, 사업성 평가,
클라우드 동기화, PDF/DOCX 내보내기, PWA(홈 화면 설치·오프라인 동기화)는
이번 범위에 포함되지 않습니다.
