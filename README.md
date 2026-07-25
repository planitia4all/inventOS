# InventOS

발명가를 위한 AI 운영체제 — MVP

> 아이디어를 기록하는 노트가 아니라, 선행특허의 초록과 비교하며 발명을 발전시키는
> 간단한 프로그램입니다.

## 핵심 사용자 흐름

```text
새 발명 등록 (제목 + 최초 아이디어만 있으면 저장 가능)
  → AI 검색어 생성 또는 수동 검색어 입력
  → 선행특허 검색 (Mock / KIPRIS Plus / 수동 등록)
  → 검색 결과에서 특허 선택 → 발명에 연결 (초록 원문 보관)
  → 같은 점 / 다른 점 / 차별화 아이디어 기록
  → 버전 저장
  → Markdown 발명노트 내보내기
```

특허 API 또는 AI API가 설정되지 않아도 발명 기록·수동 특허 등록·비교
기록·Markdown 내보내기는 항상 정상 동작합니다.

## 기술 스택

- UI: Streamlit
- Backend: Python 3.11+
- Database: SQLite (SQLAlchemy 2.0 ORM)
- HTTP: httpx
- 특허 검색: KIPRIS Plus (선택), Mock(데모), 수동 등록 — `PatentProvider` 인터페이스로 교체 가능
- AI: Anthropic Claude (선택), Mock — `AIProvider` 인터페이스로 교체 가능

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

### 5. 테스트 실행

```bash
pytest
```

## 폴더 구조

```text
inventos/
├─ app.py                       # Streamlit 엔트리포인트
├─ src/
│  ├─ config/settings.py        # .env 기반 설정
│  ├─ database/                 # SQLAlchemy 엔진/모델
│  ├─ inventions/                # 발명 CRUD/버전 관리
│  ├─ attachments/               # 첨부파일 저장
│  ├─ patents/
│  │  ├─ providers/              # PatentProvider (base/manual/mock/kipris/epo_ops/uspto)
│  │  ├─ repository.py, service.py, schemas.py
│  ├─ ai/
│  │  ├─ providers/              # AIProvider (anthropic)
│  │  ├─ base.py, mock_provider.py
│  ├─ similarity/tfidf.py        # TF-IDF 코사인 유사도
│  ├─ reports/markdown_exporter.py
│  └─ ui/pages/                  # 발명 목록/상세/특허검색/설정
├─ data/                         # SQLite DB + 첨부파일 (git 제외)
└─ tests/
```

## 데이터 저장 위치

- `data/inventos.db` — SQLite 데이터베이스
- `data/attachments/<invention_id>/` — 첨부 이미지/PDF

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

## 법적 안내

본 프로그램의 검색 결과, 유사도 및 AI 분석은 발명 검토를 위한 참고자료입니다.
신규성, 진보성, 권리범위 및 특허침해 여부에 대한 법적 판단을 제공하지 않습니다.
특허 출원 또는 사업화 전에는 변리사 등 전문가의 검토가 필요합니다.

## MVP 범위에서 제외된 기능

특허 명세서 자동 작성, 청구항 자동 확정, 특허 침해 자동 판정, 사업성 평가,
다중 사용자 협업, 클라우드 동기화, PDF/DOCX 내보내기 등은 이번 범위에
포함되지 않습니다.
