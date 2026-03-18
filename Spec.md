# Agent Gateway — Spec

> 경량·보안 중심의 멀티 LLM Agent Gateway (Telegram 인터페이스)

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 이름 | **cl0w** (가칭) |
| 목적 | 다양한 LLM 백엔드와 MCP/Skill 도구를 단일 게이트웨이로 연결 |
| 설계 원칙 | 보안 우선, 최소 코드, 단순 설정 |
| 비교 대상 | OpenClaw — 보안 취약·코드 비대화 문제 해소 |

---

## 2. 아키텍처 개요

```
                  Telegram Cloud
                       │  Bot API (polling/webhook)
┌──────────────────────▼───────────────────────────────┐
│                  Container (격리 실행)                │
│                                                      │
│  ┌────────────┐  ┌───────────────┐  ┌────────────┐   │
│  │  Telegram  │  │  Bot Handler  │  │ LLM Router │   │
│  │  Bot Layer │─▶│ (auth·session │─▶│ (provider  │   │
│  │ (python-   │  │  ·rate limit) │  │  adapter)  │   │
│  │  telegram) │◀─│               │◀─│            │   │
│  └────────────┘  └───────┬───────┘  └────────────┘   │
│                          │                           │
│                   ┌──────▼──────┐                    │
│                   │ Tool Runtime│                    │
│                   │ (MCP·Skill) │                    │
│                   └─────────────┘                    │
└──────────────────────────────────────────────────────┘
```

- **외부 HTTP 포트 불필요** — Telegram Bot API polling 방식으로 인바운드 포트 개방 없이 동작
- Webhook 방식도 선택 가능 (HTTPS 엔드포인트 필요)

---

## 3. 보안 — Container 격리

### 3-1. 실행 환경

- **Apple Container** (macOS) / **OCI 컨테이너** (Linux) 위에서만 프로세스 실행
- 컨테이너 루트 파일시스템은 **read-only** 마운트
- 단, 아래 두 경로는 **writable named volume**으로 별도 마운트 필수

  | 경로 | 용도 | 마운트 타입 |
  |------|------|-------------|
  | `/app/sessions` | 대화 히스토리 | writable volume |
  | `/app/tools` | 플러그인 핫 리로드 | writable volume (bind mount 권장) |

- 게이트웨이 프로세스는 **non-root** UID로 실행
- 모든 외부 통신은 TLS 1.3 이상 필수

### 3-2. 비밀값 관리

- API 키는 환경변수 또는 컨테이너 시크릿(Secret Mount)으로만 주입 — 설정 파일에 평문 금지
- `.env` 또는 `secrets/` 는 컨테이너 내 tmpfs에만 마운트

### 3-3. 사용자 인증 및 접근 제어

- **Telegram User ID allowlist** — 허용된 user_id만 봇 응답 (별도 JWT/API Key 불필요)
- Telegram Bot Token은 컨테이너 시크릿으로만 주입
- Rate Limit : 사용자별 메시지 상한 (기본 20 msg/min)
- Tool 실행 전 허용 목록(allowlist) 검사 — 등록되지 않은 Tool 호출 차단
- Group 채팅 비활성화 옵션 (Private chat only)

### 3-4. 멀티유저

- `ALLOWED_USER_IDS` 에 복수 user_id 등록으로 다수 사용자 지원
- 사용자별 독립 세션 및 프로바이더 설정 가능

```yaml
# config.yaml 예시
users:
  123456789:
    default_provider: claude
    rate_limit: 30
  987654321:
    default_provider: lmstudio
    rate_limit: 10
```

---

## 4. LLM 프로바이더 연동

### 4-1. 지원 대상

| Provider | 프로토콜 | 비고 |
|----------|----------|------|
| OpenAI | openai-compatible REST | GPT-4o, o-series |
| Anthropic Claude | openai-compatible REST | claude-sonnet/opus/haiku |
| Google Gemini | openai-compatible REST ✱ | gemini-1.5-pro/flash |
| LM Studio | openai-compatible REST | 로컬 — 호스트 주소 주의 ② |
| Ollama | openai-compatible REST | 로컬 — 호스트 주소 주의 ② |
| 커스텀 | openai-compatible REST | base_url 지정으로 추가 |

> ✱ **Gemini openai-compatible endpoint 사용**
> `https://generativelanguage.googleapis.com/v1beta/openai/`
> — Google이 공식 제공하는 OpenAI 호환 엔드포인트. 별도 어댑터 없이 동일 클라이언트로 처리 가능.
>
> ② **로컬 LLM 컨테이너 네트워크**
> 컨테이너 내부에서 `localhost`는 컨테이너 자신을 가리키므로 호스트의 LMStudio·Ollama에 도달 불가.
> — Docker/OCI: `host.docker.internal` 사용 또는 `--network host` 옵션
> — Apple Container: 호스트 IP 또는 `host.internal` 사용 (config.yaml에 명시)

### 4-2. 라우팅 규칙

```yaml
# config.yaml 예시
default_provider: claude

providers:
  openai:
    base_url: https://api.openai.com/v1
    model: gpt-4o
  claude:
    base_url: https://api.anthropic.com/v1
    model: claude-sonnet-4-6
  gemini:
    # Google 공식 OpenAI 호환 엔드포인트 사용 — 별도 어댑터 불필요
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    model: gemini-1.5-pro
  lmstudio:
    # Docker: host.docker.internal / Apple Container: host.internal
    base_url: http://host.docker.internal:1234/v1
    model: local-model
  ollama:
    base_url: http://host.docker.internal:11434/v1
    model: llama3
```

- Telegram 메시지에서 `/provider lmstudio` 명령으로 런타임 전환
- 폴백(fallback) 체인 설정 가능: 프로바이더 오류 시 다음 프로바이더로 자동 전환

---

## 5. MCP·Skill 플러그인 시스템

### 5-1. 설계 원칙

- Tool 하나 = 파일 하나 (단일 파일 플러그인)
- 핫 리로드: 게이트웨이 재시작 없이 Tool 추가·제거
- `tools/` 디렉터리에 파일을 넣으면 자동 등록, 꺼내면 자동 해제
- **핫 리로드 구현 방식: mtime 폴링** — 외부 라이브러리(watchdog) 없이 봇 루프 안에서 매 `hot_reload_interval`초마다 `tools/` 디렉터리의 파일 수정시각을 비교, 변경 시 재스캔 (`hot_reload_interval` 기본 5초)

### 5-2. 디렉터리 구조

```
cl0w/
├── bot.py               # Telegram Bot + 게이트웨이 본체 (단일 파일)
├── config.yaml          # 전체 설정 (프로바이더·Telegram·rate limit·MCP)
├── persona.md           # 활성 Persona (핫 리로드)
├── .env                 # 시크릿 (절대 커밋 금지)
├── Dockerfile
├── docker-compose.yml
├── docker-compose.windows.yml   # Windows/macOS Docker Desktop 오버라이드
├── run.sh               # 직접 실행 스크립트 (macOS / Linux)
├── run.ps1              # 직접 실행 스크립트 (Windows PowerShell)
├── requirements.txt     # 코어 패키지 4개 (+ 선택: mcp)
│
├── tools/               # Skill 플러그인 디렉터리 (서브디렉터리 지원)
│   ├── web_search.py    # 예: 웹검색 Tool
│   └── search/          # 서브디렉터리도 자동 스캔 (rglob)
│       └── ddg.py
│
├── personas/            # Persona 라이브러리
│   ├── friendly.md      # Sol (따뜻한 도우미)
│   └── technical.md     # Hex (기술 전문가)
│
└── sessions/            # 자동 생성, user_id별 대화 히스토리 JSON
```

### 5-3. Tool 인터페이스 (Python 예시)

```python
# tools/web_search.py
TOOL_SCHEMA = {
    "name": "web_search",
    "description": "Search the web",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"]
    }
}

def run(query: str) -> str:
    # 구현
    ...
```

- `TOOL_SCHEMA` 상수 + `run()` 함수만 있으면 등록 완료
- **서브디렉터리 지원**: `tools/` 아래 중첩 디렉터리도 `rglob("*.py")` 로 자동 스캔. `_` 로 시작하는 파일은 제외. 모듈명은 점(.) 구분 경로로 자동 변환 (예: `search/ddg.py` → `search.ddg`)
- MCP 서버에 등록된 Tool은 Python Tool과 동일하게 LLM에 노출되며, `/tools` 명령 목록에도 함께 표시

### 5-4. MCP 서버 연동

선택 패키지 `mcp` 를 설치하면 MCP(Model Context Protocol) 서버를 외부 프로세스 또는 HTTP 서버로 연결할 수 있다.

#### 설정 방법 — config.yaml

```yaml
# pip install mcp 필요
mcp_servers:

  # stdio — MCP 서버를 서브프로세스로 실행
  filesystem:
    transport: stdio
    command: uvx
    args: ["mcp-server-filesystem", "/tmp"]
    env:                  # 선택: 서버에 전달할 환경변수
      MY_KEY: "value"

  # stdio — 직접 작성한 Python MCP 서버
  my_server:
    transport: stdio
    command: python
    args: ["my_mcp_server.py"]

  # SSE — 이미 실행 중인 MCP HTTP 서버에 연결
  remote_tools:
    transport: sse
    url: http://localhost:3000/sse
```

#### 동작 방식

| 단계 | 내용 |
|------|------|
| 봇 시작 | `mcp_servers` 에 정의된 모든 서버에 자동 연결, Tool 목록 수집 |
| 연결 유지 | stdio: `asyncio.sleep(∞)` 로 서브프로세스 세션 유지. SSE: HTTP 롱폴링 |
| 자동 재연결 | 연결 끊김 시 10초 후 자동 재시도 |
| 핫 리로드 | config.yaml 변경 감지 시(10초 폴링) 추가/삭제된 서버만 시작·중지 — **봇 재시작 불필요** |
| Tool 통합 | MCP Tool은 Python Skill Tool과 동일하게 LLM system prompt에 등록 |

#### 트랜스포트별 특이사항

- **stdio**: 봇 프로세스가 MCP 서버를 자식 프로세스로 관리. 봇 종료 시 자식도 함께 종료.
- **SSE**: MCP 서버가 별도로 실행 중이어야 함. URL만 설정하면 연결.

### 5-5. 대화 히스토리 저장

- `sessions/<user_id>.json` 에 대화 히스토리 누적 저장 (선택)

- config.yaml 에서 활성화·최대 보관 턴 수 설정

```yaml
session:
  persist: true          # false면 메모리 내 유지만
  max_turns: 50          # 초과 시 오래된 턴부터 삭제
  dir: ./sessions
```

---

## 6. Persona / Soul 시스템

### 6-1. 개념

에이전트는 고유한 Persona(성격·태도·말투)를 가진다. 사용자가 `persona.md` 파일에 자유 형식으로 Persona를 기술하면, 봇 기동 시 이를 읽어 **모든 LLM 요청의 system prompt 앞에 자동 삽입**한다.

### 6-2. persona.md 작성 형식

자유 형식 마크다운이지만, 아래 섹션을 권장한다.

```markdown
# Persona

## Identity
이름: Crow
한 줄 소개: 날카롭고 솔직한 AI 파트너

## Personality
- 군더더기 없는 직설 화법
- 유머는 건조하고 짧게
- 틀린 전제에는 주저 없이 반박
- 칭찬보다 정확한 피드백 우선

## Tone & Manner
- 경어 사용하되 딱딱하지 않게
- 이모지 최소화
- 긴 서론 없이 바로 핵심부터

## Constraints
- 근거 없는 낙관론 금지
- 확실하지 않으면 "모르겠다"고 말할 것
```

- 섹션명·항목은 자유롭게 변경 가능
- 파일이 없으면 Persona 없이 기본 동작

### 6-3. 적용 방식

```
system prompt =
  [persona.md 전체 내용]
  ---
  [Tool 목록 및 사용 지침 (자동 생성)]
```

- `persona.md` 수정 시 **봇 재시작 없이 핫 리로드** (hot_reload: true 시)

### 6-4. Persona 런타임 전환

- `personas/` 디렉터리에 여러 persona 파일 보관 가능
- `/persona switch <name>` 명령으로 재시작 없이 즉시 교체

```
cl0w/
├── persona.md           # 현재 활성 Persona (기본)
└── personas/
    ├── friendly.md
    ├── technical.md
    └── concise.md
```

---

## 7. 설치 및 설정

### 7-1. 플랫폼별 실행 방법

| 플랫폼 | 컨테이너 실행 | Docker 없이 직접 실행 |
|--------|-------------|----------------------|
| macOS (Apple Silicon/Intel) | `docker compose up --build` | `./run.sh` |
| Linux | `docker compose up --build` | `./run.sh` |
| **Windows** | `docker compose -f docker-compose.yml -f docker-compose.windows.yml up --build` | `.\run.ps1` |

> **Windows 전용 오버라이드**: `docker-compose.windows.yml` 은 Linux 전용 `extra_hosts: host-gateway` 항목을 `!reset []` 로 제거. Docker Desktop(Windows/macOS)에서는 `host.docker.internal` 이 자동 등록되므로 별도 설정 불필요.

```bash
# 1. 클론
git clone <repo> cl0w && cd cl0w

# 2. 시크릿 설정
cp .env.example .env        # Windows: Copy-Item .env.example .env
# .env 에 아래 항목 입력:
#   TELEGRAM_BOT_TOKEN=...     # @BotFather에서 발급
#   ALLOWED_USER_IDS=123,456   # 허용할 Telegram user_id 목록
#   ANTHROPIC_API_KEY=...
#   OPENAI_API_KEY=...

# 3. Persona 작성 (선택 — 없으면 기본 동작)
nano persona.md             # Windows: notepad persona.md

# 4. 컨테이너 실행 (플랫폼별 위 표 참고)
docker compose up --build
```

#### Docker 없이 직접 실행 (개발 환경)

```bash
# macOS / Linux
pip install -r requirements.txt python-dotenv
./run.sh

# Windows (PowerShell)
pip install -r requirements.txt python-dotenv
.\run.ps1
```

> `python-dotenv` 는 선택 패키지. Docker 없이 실행할 때 `.env` 파일을 자동으로 로드함.

### 7-2. Tool 추가·제거

```bash
# 추가: tools/ 에 파일 복사하면 즉시 활성화
cp my_tool.py cl0w/tools/

# 제거: 파일 삭제하면 즉시 비활성화
rm cl0w/tools/my_tool.py
```

### 7-3. config.yaml 핵심 옵션

```yaml
telegram:
  mode: polling           # polling | webhook
  # webhook_url: https://your.domain/webhook   # webhook 모드 시만 필요

default_provider: claude

fallback_chain:
  - claude
  - openai

rate_limit: 20            # 메시지/분 per user

session:
  persist: true
  max_turns: 50
  dir: ./sessions

tools_dir: ./tools
hot_reload_interval: 5    # Tool 디렉터리 스캔 주기 (초, 기본 5)

observability:
  log_level: info          # debug | info | warn | error
  # admin_chat_id: 123456789   # 오류 알림 받을 Telegram chat_id

# MCP 서버 (선택 — pip install mcp 필요)
# config.yaml 저장 시 10초 이내 자동 반영 (봇 재시작 불필요)
# mcp_servers:
#   filesystem:
#     transport: stdio
#     command: uvx
#     args: ["mcp-server-filesystem", "/tmp"]
#   remote_tools:
#     transport: sse
#     url: http://localhost:3000/sse
```

---

## 8. 구현 스택 (경량 우선)

| 레이어 | 선택 | 이유 |
|--------|------|------|
| 런타임 | Python 3.12 | 생태계·LLM SDK 호환 |
| Telegram Bot | **python-telegram-bot** (async) | polling/webhook 모두 지원, 경량 |
| LLM 클라이언트 | **httpx** (비동기) | SDK 없이 직접 REST 호출, 전 프로바이더 공통 |
| 설정 파싱 | **pyyaml** | 의존성 최소 |
| PDF 파싱 | **pypdf** | 순수 Python, 경량 (~500KB) |
| 핫 리로드 | mtime 폴링 (내장) | watchdog 라이브러리 불필요 |
| 컨테이너 | Dockerfile (`FROM python:3.12-slim`) | 이미지 < 120MB 목표 |
| **코어 의존성** | **python-telegram-bot, httpx, pyyaml, pypdf** | **4개** |
| MCP 클라이언트 | **mcp** *(선택)* | stdio + SSE 트랜스포트 |
| .env 로더 | **python-dotenv** *(선택)* | Docker 없이 직접 실행 시 필요 |

**코드량 상한: `bot.py` 단일 파일 750줄 이하** (현재 702줄)

> pypdf는 PDF 처리가 필요 없는 배포에서는 제거 가능 (`file.pdf_support: false` 시 import 생략)

---

## 9. Telegram 인터페이스

### 9-1. 사용자 명령어

| 명령어 | 동작 |
|--------|------|
| `(일반 텍스트)` | 현재 프로바이더로 메시지 전송, 응답 반환 |
| `/help` | 사용 가능한 명령어 목록 표시 |
| `/provider <name>` | 프로바이더 전환 (예: `/provider lmstudio`) |
| `/tools` | 현재 등록된 Tool 목록 출력 |
| `/reset` | 현재 대화 세션(컨텍스트) 초기화 |
| `/status` | 현재 프로바이더·모델·로드된 Persona 이름 출력 |
| `/persona` | 현재 로드된 persona.md 내용 출력 |
| `/persona switch <name>` | 다른 Persona 파일로 즉시 전환 |

### 9-2. 스트리밍 응답

- LLM 응답을 청크 단위로 수신하여 Telegram 메시지를 **실시간 편집(edit_message)** 으로 업데이트
- **edit_message 호출 간격 최소 1초** — Telegram API는 동일 메시지 편집을 초당 1회로 제한(초과 시 429). 청크를 버퍼에 누적하다 1초마다 1회 flush
- 긴 응답은 4096자 Telegram 한도에 맞춰 자동 분할 전송

### 9-3. Tool 실행 흐름

```
사용자 메시지
    └─▶ LLM (tool_call 포함 응답)
            └─▶ Tool Runtime 실행
                    └─▶ 결과를 LLM에 재전송
                            └─▶ 최종 답변을 Telegram으로 전송
```

- Tool 실행 중에는 "처리 중..." 상태 메시지 표시
- Tool 이름과 입력값은 Telegram 메시지에 간략 표시 (투명성)

### 9-4. 파일·이미지 처리

사용자가 Telegram을 통해 파일을 전송하면 아래 흐름으로 처리한다.

#### 처리 흐름

```
Telegram 파일 수신
    │
    ├─ 이미지 (JPEG·PNG·GIF·WEBP)
    │       └─▶ base64 인코딩 → Vision 지원 프로바이더에 image content block으로 전달
    │           (Vision 미지원 프로바이더 선택 중이면 오류 안내 후 전환 유도)
    │
    ├─ 텍스트 계열 (.txt .md .csv .json .py .yaml 등)
    │       └─▶ UTF-8 디코딩 → 컨텍스트에 코드블록으로 삽입 (추가 라이브러리 없음)
    │
    ├─ PDF (.pdf)
    │       └─▶ pypdf 텍스트 추출 → 컨텍스트에 삽입
    │           (이미지 전용 PDF 등 텍스트 추출 실패 시 사용자에게 안내)
    │
    └─ 그 외 포맷 (.docx .xlsx .zip 등)
            └─▶ "지원하지 않는 형식입니다. Tool을 추가하면 처리 가능합니다." 안내 메시지 전송
```

#### 제약 조건

| 항목 | 기본값 | config.yaml 키 |
|------|--------|----------------|
| 단일 파일 최대 크기 | 20 MB | `file.max_size_mb` |
| 텍스트 계열 컨텍스트 삽입 상한 | 50,000 자 | `file.max_text_chars` |
| PDF 최대 페이지 수 | 100 페이지 | `file.pdf_max_pages` |

- 상한 초과 시 앞부분만 잘라 삽입하고 사용자에게 "[파일이 잘려 일부만 포함됨]" 안내
- 이미지는 Vision 미지원 프로바이더 사용 중일 때 자동으로 사용자에게 프로바이더 전환 안내

#### Vision 지원 프로바이더

| Provider | Vision 지원 |
|----------|------------|
| OpenAI GPT-4o | ✅ |
| Claude (Sonnet·Opus) | ✅ |
| Gemini 1.5 Pro/Flash | ✅ |
| LM Studio / Ollama | 모델 의존 (config에 `vision: true` 명시 시 활성화) |

---

## 10. 관찰가능성

- **오류 알림**: 처리 오류·프로바이더 장애 발생 시 config에 지정한 관리자 Telegram 채널로 즉시 알림
- **로그**: 컨테이너 stdout에 구조화 로그 출력 (JSON Lines 형식)
- **로그 레벨**: config.yaml `log_level` 로 조정 (debug / info / warn / error)

```
[오류 알림 예시 — 관리자 채널]
⚠️ cl0w 오류
provider: claude
error: APIConnectionError
user: 123456789
time: 2026-03-17 14:32:01
```

---

## 11. 보안 체크리스트

- [ ] 컨테이너 non-root 실행
- [ ] read-only 루트 파일시스템 + sessions·tools 전용 writable volume 분리
- [ ] Telegram Bot Token 컨테이너 시크릿 주입
- [ ] ALLOWED_USER_IDS allowlist 적용 (미등록 user_id 메시지 무시)
- [ ] API 키 평문 저장 금지
- [ ] Tool allowlist 적용
- [ ] Rate limit 적용 (20 msg/min per user)
- [ ] 입력 메시지 길이 제한 (기본 4096자)
- [ ] Tool 실행 타임아웃 (기본 30s)
- [ ] Group 채팅 비활성화 (Private chat only, 선택)
- [ ] 수신 파일 크기 제한 (기본 20MB)
- [ ] 파일 텍스트 삽입 상한 적용 (기본 50,000자)
- [ ] 로컬 LLM 엔드포인트 host.docker.internal 사용 확인 (localhost 오설정 방지)

---

*이 Spec은 현재 구현된 내용을 기준으로 작성되었습니다. 추가 기능 개발 시 이 문서를 먼저 업데이트하세요.*
