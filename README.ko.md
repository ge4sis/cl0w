<div align="center">

```
 ██████╗██╗      ██████╗ ██╗    ██╗
██╔════╝██║     ██╔═████╗██║    ██║
██║     ██║     ██║██╔██║██║ █╗ ██║
██║████╗██║     ████╔╝██║██║███╗██║
╚██████╔╝███████╗╚██████╔╝╚███╔███╔╝
 ╚═════╝ ╚══════╝ ╚═════╝  ╚══╝╚══╝
```

**경량 · 보안 · 개성 있는 Agent Gateway**

*하나의 봇으로. 모든 LLM을. 아무 번거로움 없이.*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
[![Lines of Code](https://img.shields.io/badge/bot.py-681줄-f59e0b?style=flat-square)]()
[![Dependencies](https://img.shields.io/badge/의존성-4개%2B-a855f7?style=flat-square)]()
[![Container](https://img.shields.io/badge/컨테이너-ready-0ea5e9?style=flat-square&logo=docker&logoColor=white)]()

[English →](README.md)

</div>

---

## cl0w 는 무엇인가?

대부분의 에이전트 프레임워크는 무겁고, 보안이 취약하며, 설정이 복잡합니다.
**cl0w** 는 다릅니다. 단일 Python 파일에 담기면서도 격리된 컨테이너 안에서 실행되고, 모든 주요 LLM에 연결되며, Tool을 몇 초 만에 붙이고 뗄 수 있습니다.

| | OpenClaw | cl0w |
|---|---|---|
| 핵심 로직 | 여러 파일, 2000줄 이상 | **단일 파일, 681줄** |
| 의존성 | 15개 이상 | **4개 코어 + 선택** |
| 보안 | 프로세스 수준 | **컨테이너 격리, read-only 파일시스템** |
| 인터페이스 | 웹 UI / REST | **Telegram (포트 개방 없음)** |
| Tool 설치 | 재시작 필요 | **파일 넣으면 즉시 활성화** |
| 에이전트 개성 | 없음 | **마크다운으로 정의하는 Soul** |

---

## 주요 기능

### 🔐 보안 우선 아키텍처
**Apple Container**(macOS) 또는 **OCI 컨테이너**(Linux) 안에서만 실행되며, 루트 파일시스템은 read-only로 마운트됩니다. Telegram polling 방식을 사용하므로 인바운드 포트를 열 필요가 없어 서버가 인터넷에 노출되지 않습니다. API 키는 환경변수로만 주입되며, 설정 파일에 평문으로 저장되는 일은 절대 없습니다.

### 🧠 모든 LLM, 하나의 인터페이스
모든 프로바이더가 OpenAI 호환 REST를 사용하므로 단일 `httpx` 클라이언트로 처리됩니다. 프로바이더별 SDK가 필요 없습니다.

| 프로바이더 | 유형 |
|----------|------|
| OpenAI (GPT-4o, o-series) | 클라우드 |
| Anthropic Claude (Sonnet / Opus / Haiku) | 클라우드 |
| Google Gemini (1.5 Pro / Flash) | 클라우드 |
| LM Studio | 로컬 |
| Ollama | 로컬 |
| OpenAI 호환 커스텀 엔드포인트 | 직접 추가 |

대화 도중 `/provider ollama` 명령으로 LLM을 즉시 전환할 수 있습니다. 프로바이더 장애 시 fallback 체인이 자동으로 다음 프로바이더로 전환합니다.

### 🔌 Tool을 초 단위로 붙이고 떼기
`tools/` 디렉터리에 `.py` 파일을 넣으면 — 즉시 활성화됩니다. 재시작도, 설정 변경도 필요 없습니다.
파일을 꺼내면 — 즉시 해제됩니다.

```python
# tools/my_tool.py  ← 이게 전부입니다
TOOL_SCHEMA = {
    "name": "my_tool",
    "description": "유용한 작업을 수행합니다",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

def run(query: str) -> str:
    return f"{query}에 대한 결과"
```

### 🔗 MCP 서버 연동
[Model Context Protocol](https://modelcontextprotocol.io) 서버를 연결하세요. 선택 패키지 `mcp` 만 설치하면 됩니다.

`config.yaml` 에 설정하면 봇 시작 시 자동으로 연결됩니다. 파일을 수정해 서버를 추가하거나 제거하면 **10초 이내에 자동 반영** — 재시작이 필요 없습니다.

```yaml
# config.yaml
mcp_servers:

  # stdio — MCP 서버를 서브프로세스로 실행
  filesystem:
    transport: stdio
    command: uvx
    args: ["mcp-server-filesystem", "/tmp"]

  # SSE — 이미 실행 중인 MCP HTTP 서버에 연결
  my_api:
    transport: sse
    url: http://localhost:3000/sse
```

MCP 서버에 등록된 Tool은 Python Tool과 동일하게 `/tools` 목록에 표시되며, LLM이 동일한 방식으로 호출합니다.

### 🎭 Persona / Soul 시스템
에이전트에게 진짜 개성을 부여하세요. 마크다운 파일 하나를 작성하면 — 에이전트의 성격, 말투, 태도, 제약이 모든 LLM 요청의 system prompt에 자동으로 반영됩니다.

```markdown
## Identity
이름: Crow
한 줄 소개: 날카롭고 솔직한 AI 파트너

## Tone & Manner
- 군더더기 없는 직설 화법
- 건조한 유머, 짧게
- 틀린 전제에는 주저 없이 반박
```

`/persona switch technical` 명령으로 즉시 다른 Persona로 전환할 수 있습니다.

### 💬 Telegram 네이티브 UX
- **스트리밍 응답** — LLM이 생성하는 동안 메시지가 실시간으로 업데이트
- **파일·이미지 지원** — 사진, PDF, 코드 파일을 그대로 전송
- **사용자별 세션** — 대화 히스토리가 사용자 단위로 영구 저장
- **멀티유저** — Telegram ID allowlist로 복수 사용자 지원, 각자 독립 설정 가능

---

## 실제로 무엇을 할 수 있나요?

cl0w는 챗봇이 아닙니다. Telegram 안에 살면서 당신을 **대신해 행동하는 개인 에이전트**입니다 — 웹을 검색하고, 파일을 읽고, API를 호출하고, 여러 행동을 자율적으로 연결합니다.

첫날부터 바로 쓸 수 있는 실제 사용 사례를 소개합니다.

---

### 🔍 사용 사례 1 — 즉석 리서치

> `tools/web_search.py` 를 넣고, 최신 정보가 필요한 질문을 던지세요.

```
나:     Claude 4 와 GPT-5 의 핵심 차이점을 팀에 공유할 수 있게
        정리해줘.

Crow:  🔧 web_search({"query": "Claude 4 vs GPT-5 비교 2025"})
       🔧 web_search({"query": "GPT-5 성능 벤치마크"})

       비교 정리입니다:

       **컨텍스트 윈도우**: Claude 4 — 200K / GPT-5 — 128K
       **코딩**: 코딩 벤치마크에서 GPT-5가 소폭 우세...
       **추론**: 다단계 논리 문제에서 Claude 4가 강세...
```

에이전트가 검색하고, 읽고, 정리합니다. 당신은 질문만 하면 됩니다.

---

### 📄 사용 사례 2 — 문서 분석

> 파일을 그냥 보내세요. cl0w가 읽고 판단합니다.

```
나:     [contract.pdf 첨부 — 42페이지]
        해지 조항이랑 숨겨진 리스크 있으면 찾아줘.

Crow:  42페이지 분석 중...

       해지 조항 3개 발견:
       — 8.2조: 30일 사전 통보 시 양측 모두 해지 가능...
       — 11.4조: NDA 위반 시 즉시 해지...

       ⚠️  14.1조 주의:
       계약 종료 후에도 데이터 보관 비용을 귀사가 부담하는 조항.
       일반적으로는 벤더 측 부담 — 이례적인 조항입니다.
```

PDF, 코드 파일, CSV, 로그, 마크다운 — 텍스트 기반이면 무엇이든 됩니다.

---

### 🔒 사용 사례 3 — 민감한 문서는 로컬 LLM으로

> 회사 내부 자료나 개인 정보는 클라우드에 보내지 마세요. 한 명령으로 전환합니다.

```
나:     /provider ollama

Crow:  ✅ ollama (llama3) 으로 전환했습니다.

나:     [salary_review.pdf 첨부]
        이거 요약하고 연봉 협상 포인트 뽑아줘.

Crow:  [내 컴퓨터에서만 처리 — 클라우드 API에 데이터 전송 없음]

       요약: 현재 패키지가 동일 직급 시장 평균 대비 12% 낮습니다.
       협상 포인트:
       1. 3섹션의 시장 데이터를 근거로 제시...
```

명령 하나로 완전한 프라이버시. 클라우드 API는 전혀 호출되지 않습니다.

---

### 🎭 사용 사례 4 — Persona로 업무 모드 전환

> 업무마다 다른 태도가 필요합니다. Persona를 바꾸면 에이전트의 성격이 바뀝니다.

```
나:     /persona switch technical

Crow:  ✅ Persona → technical  (현재: Hex)

나:     이 Python 함수 프로덕션 투입 가능한지 리뷰해줘.
       [utils.py 첨부]

Hex:   발견된 문제:

       [치명] 23번줄: 파일 I/O에 예외처리 없음.
       [경고] 41번줄: 가변 기본 인수 `def fn(data=[]):` — 사이드 이펙트 위험.
       [경고] 67번줄: 매직 넘버 86400 — `datetime.timedelta` 로 교체 권장.
       [안내] 타입 힌트 없음. 유지보수를 위해 추가 권장.

       수정 버전:
       ```python
       def fn(data: list[str] | None = None) -> dict:
           data = data or []
           ...
```

같은 코드를 비기술직 동료에게 설명할 때는 `/persona switch friendly` 로 전환하면 됩니다.

---

### 🤖 사용 사례 5 — 10줄짜리 커스텀 Tool 연결

> 회사 내부 시스템이 있나요? 몇 분 만에 연결할 수 있습니다.

```python
# tools/jira_create.py
import httpx, os

TOOL_SCHEMA = {
    "name": "jira_create_ticket",
    "description": "설명을 받아 Jira 티켓을 생성합니다",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary":     {"type": "string"},
            "description": {"type": "string"},
            "priority":    {"type": "string", "enum": ["Low","Medium","High","Critical"]},
        },
        "required": ["summary", "description"],
    },
}

def run(summary: str, description: str, priority: str = "Medium") -> str:
    r = httpx.post(
        f"{os.environ['JIRA_URL']}/rest/api/3/issue",
        auth=(os.environ['JIRA_USER'], os.environ['JIRA_TOKEN']),
        json={"fields": {"summary": summary, "priority": {"name": priority}, ...}}
    )
    return f"생성됨: {r.json().get('key')}"
```

파일을 `tools/` 에 저장하면 즉시 활성화됩니다:

```
나:     iOS Safari에서 로그인 화면이 깨지는 버그,
        Jira 티켓 High 우선순위로 만들어줘.

Crow:  🔧 jira_create_ticket({
           "summary": "iOS Safari 로그인 화면 버그",
           "description": "로그인 페이지에서...",
           "priority": "High"
       })

       생성됨: MOB-2847
```

배포도, 재시작도 없습니다. 파일을 저장한 순간 에이전트가 새 능력을 얻습니다.

---

### 🔗 사용 사례 6 — 자율 다단계 실행 (Agentic Loop)

> 복잡한 목표를 던지세요. 에이전트가 단계를 스스로 계획합니다.

```
나:     내일 Acme Corp 미팅 준비해줘.
        최근 뉴스, 채용 현황(성장 신호), 알아야 할 것 3줄로 정리.

Crow:  🔧 web_search({"query": "Acme Corp 최근 뉴스 2025"})
       🔧 web_search({"query": "Acme Corp 채용 2025"})
       🔧 web_search({"query": "Acme Corp 투자 매출"})

       미팅 브리핑:

       • 📈 성장 신호: 엔지니어 40명 이상 채용 중 — 시리즈 B 임박 가능성.
       • 📰 최근 뉴스: 지난달 AWS와 파트너십 발표 — 클라우드 퍼스트 전환 중.
       • ⚠️  주의: CEO가 벤더 종속 문제를 공개적으로 비판 — 유연성을 전면에 내세우세요.
```

에이전트 루프의 핵심입니다: LLM이 계획하고, 도구를 실행하고, 결과를 읽고, 다시 계획합니다 — 메시지 하나를 보내기 전에 이 모든 과정이 자동으로 일어납니다.

---

### 💡 또 무엇을 만들 수 있나요?

| 아이디어 | 필요한 Tool |
|---------|-----------|
| 매일 아침 뉴스 브리핑 | `web_search` + 크론 작업 |
| GitHub PR 자동 리뷰어 | `github_api` tool |
| SQL 쿼리 도우미 | `db_query` tool |
| 홈 자동화 음성 제어 | `home_assistant` tool + Telegram 음성 |
| 개인 지출 분석기 | `spreadsheet_read` + `web_search` |
| 언어 학습 튜터 | 커스텀 Persona (`tutor.md`) — Tool 불필요 |
| 경쟁사 모니터링 | `web_search` + `notify` tool |

모든 새 기능은 Python 파일 하나입니다. 에이전트가 조각들을 조립합니다.

---

## 플랫폼 지원

| 플랫폼 | 컨테이너 실행 | Docker 없이 직접 실행 |
|--------|-------------|----------------------|
| macOS (Apple Silicon / Intel) | Apple Container 또는 Docker Desktop | `./run.sh` |
| Linux | Docker Engine | `./run.sh` |
| **Windows** | Docker Desktop (WSL2 백엔드) | `.\run.ps1` |

> **어떤 플랫폼도 소외되지 않습니다.** Python 3.12가 돌아가는 곳이면 cl0w도 돌아갑니다.

---

## 빠른 시작

실행 방법을 선택하세요:

### 방법 A — Docker (권장, 전 플랫폼)

**사전 준비:** Docker Desktop (Windows / macOS) 또는 Docker Engine (Linux)

```bash
# 1. 클론
git clone https://github.com/your-org/cl0w.git && cd cl0w

# 2. 시크릿 설정
cp .env.example .env
# TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, API 키 입력
```

> 내 Telegram ID를 모른다면? [@userinfobot](https://t.me/userinfobot) 에 `/start` 를 보내면 알려줍니다.

**macOS / Linux:**
```bash
docker compose up --build
```

**Windows (Docker Desktop):**
```bash
# docker-compose.windows.yml 이 Linux 전용 extra_hosts 항목을 제거합니다
docker compose -f docker-compose.yml -f docker-compose.windows.yml up --build
```

> 로컬 LLM(Ollama / LM Studio): Docker Desktop에서는 `host.docker.internal` 이 자동으로 등록되므로 별도 설정 불필요합니다.

---

### 방법 B — 직접 Python 실행 (Docker 없이)

**macOS / Linux:**
```bash
pip install -r requirements.txt python-dotenv
cp .env.example .env   # 토큰 입력
./run.sh
```

**Windows (PowerShell):**
```powershell
pip install -r requirements.txt python-dotenv
Copy-Item .env.example .env   # 토큰 입력
.\run.ps1
```

> Docker 없이 실행하면 컨테이너 격리가 비활성화됩니다. 로컬 개발 환경 전용으로 사용하세요.

---

```bash
# 3. (선택) Persona 편집
nano persona.md        # macOS / Linux
notepad persona.md     # Windows

# 4. 완료 — Telegram에서 봇에게 메시지를 보내세요
```

---

## 파일 구조

```
cl0w/
├── bot.py              ← 게이트웨이 전체 (681줄)
├── config.yaml         ← 모든 설정 (프로바이더, MCP 서버, 한도)
├── persona.md          ← 활성 Persona (핫 리로드)
├── .env                ← 시크릿 (절대 커밋 금지)
├── Dockerfile
├── docker-compose.yml
├── docker-compose.windows.yml
├── run.sh / run.ps1    ← 직접 실행 스크립트 (macOS·Linux / Windows)
├── requirements.txt    ← 코어 패키지 4개 (+ 선택: mcp)
│
├── tools/              ← .py 파일을 넣으면 Tool 즉시 활성화 (서브디렉터리 지원)
│   └── web_search.py   ← 예제: DuckDuckGo 검색 (API 키 불필요)
│
├── personas/           ← Persona 라이브러리
│   ├── friendly.md     ← Sol (따뜻한 도우미)
│   └── technical.md    ← Hex (기술 전문가)
│
└── sessions/           ← 자동 생성, 사용자별 대화 히스토리
```

---

## Telegram 명령어

| 명령어 | 동작 |
|--------|------|
| *(일반 텍스트)* | 현재 LLM과 대화 |
| `/provider <이름>` | LLM 전환 (`claude`, `openai`, `ollama` 등) |
| `/tools` | 활성화된 Tool 목록 |
| `/persona` | 현재 Persona 내용 확인 |
| `/persona switch <이름>` | 다른 Persona로 즉시 전환 |
| `/status` | 프로바이더 · 모델 · Persona · Tool 수 |
| `/reset` | 대화 히스토리 초기화 |

---

## 설정

`config.yaml` 에서 모든 것을 제어합니다. 자주 쓰는 옵션:

```yaml
default_provider: claude

fallback_chain:         # 자동 폴백 순서
  - claude
  - openai

providers:
  ollama:
    base_url: http://host.docker.internal:11434/v1
    model: llama3

rate_limit: 20          # 사용자당 분당 메시지 수

session:
  persist: true
  max_turns: 50

hot_reload_interval: 5  # Tool 디렉터리 스캔 주기 (초)

# MCP 서버 (선택 — pip install mcp 필요)
# config.yaml 변경 시 자동 감지 — 재시작 불필요
mcp_servers:
  filesystem:
    transport: stdio
    command: uvx
    args: ["mcp-server-filesystem", "/tmp"]
  remote_tools:
    transport: sse
    url: http://localhost:3000/sse
```

---

## 로컬 LLM 연결

**Ollama**
```bash
# 먼저 모델 pull
ollama pull llama3
```
```yaml
# config.yaml
providers:
  ollama:
    base_url: http://host.docker.internal:11434/v1
    model: llama3
```

**LM Studio**
```yaml
providers:
  lmstudio:
    base_url: http://host.docker.internal:1234/v1
    model: local-model
```

> `host.docker.internal` 은 컨테이너 안에서 호스트 머신을 가리킵니다.
> Apple Container 환경에서는 `host.internal` 을 사용하세요.

---

## 파일 전송 처리

Telegram으로 파일을 보내면 cl0w 가 자동으로 처리합니다.

| 파일 종류 | 처리 방법 |
|----------|----------|
| 이미지 (JPG·PNG·GIF·WEBP) | base64 인코딩 → Vision API 전달 |
| 텍스트 계열 (txt·md·py·json 등) | UTF-8 디코딩 → 컨텍스트에 삽입 |
| PDF | `pypdf` 텍스트 추출 → 컨텍스트에 삽입 |
| 그 외 형식 | 안내 메시지 + Tool 확장 유도 |

---

## 보안 모델

```
┌─────────────────────────────────────────────────┐
│  컨테이너 (read-only 루트 파일시스템)             │
│                                                 │
│  • non-root UID 실행                            │
│  • 인바운드 포트 없음 (polling 전용)             │
│  • 시크릿은 환경변수 / tmpfs 만 사용             │
│  • Telegram user_id allowlist                  │
│  • 사용자별 Rate Limit                          │
│  • Tool 실행 타임아웃 (30초)                    │
│  • 파일 크기 상한 (20MB)                        │
│                                                 │
│  writable 볼륨 (격리):                          │
│    /app/tools    ← plugin bind-mount            │
│    /app/sessions ← named volume                 │
└─────────────────────────────────────────────────┘
```

---

## 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| 런타임 | Python 3.12 | LLM 생태계 호환성 |
| Telegram | python-telegram-bot | 비동기, polling·webhook 모두 지원 |
| HTTP | httpx | 모든 LLM 공통 비동기 클라이언트 |
| 설정 | pyyaml | 최소화, 사람이 읽기 쉬운 형식 |
| PDF | pypdf | 순수 Python, ~500KB |
| **총 의존성** | **4개 코어** | 이게 전부입니다 |
| MCP 클라이언트 | mcp *(선택)* | stdio + SSE 트랜스포트 |

---

## 로드맵

- [x] MCP 서버 연동 (stdio + SSE, 핫 리로드)
- [ ] 음성 메시지 → 텍스트 변환 (Whisper Tool)
- [ ] 멀티 에이전트 오케스트레이션 (에이전트 간 호출)
- [ ] 웹 UI 대시보드 (읽기 전용 모니터링)
- [ ] 원클릭 설치 스크립트 (Docker 없이)
- [ ] MCP 서버 레지스트리 연동

---

## 기여하기

1. Fork → 브랜치 → PR
2. `bot.py` 는 700줄 이내로 유지
3. 새 기능은 가능하면 `tools/` 에 추가
4. PR 설명에 한 줄짜리 "왜 필요한가" 필수

---

## 라이선스

MIT — 원하는 대로 사용하세요. 다만 책임은 본인에게 있습니다.

---

<div align="center">

*한 번에 읽을 수 있을 만큼 작고,*
*AI 워크플로우 전체를 대체할 만큼 강력합니다.*

**[⭐ 스타 눌러주기](https://github.com/your-org/cl0w)** — cl0w 가 시간을 아껴줬다면요.

[English →](README.md)

</div>
