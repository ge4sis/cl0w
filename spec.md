# cl0w — Specification

> **"Zero Hassle, Zero Weight, Zero Fee Agent"**
>
> LM Studio 기반 Local LLM + Telegram Bot Frontend로 구성된 개인용 AI Agent 서비스.
> 클라우드 의존 없이, 설치 부담 없이, 비용 없이 동작하는 것이 핵심 철학이다.

---

## 1. 프로젝트 개요

### 1.1 배경

`LocalLLMBot` 프로젝트를 기반으로 하며, 다음 한계를 극복하고 Agent 수준으로 확장한다:

| 기존 한계 | cl0w의 해결 방향 |
|---|---|
| 고정 시스템 프롬프트 | Persona 파일 기반 동적 교체 |
| MCP 설정이 `~/.lmstudio/mcp.json`에만 의존 | 프로젝트 로컬 `mcp.json`으로 관리, 봇 내 명령어로 제어 |
| 이미지만 처리 가능 | PDF, 문서, 코드 파일 등 다양한 파일 처리 |
| 반복 작업에 대한 재사용 수단 없음 | Skill 시스템으로 프롬프트 템플릿 재사용 |

### 1.2 핵심 설계 원칙

- **Zero Hassle**: 별도 서버 불필요. Telegram Long Polling + 로컬 프로세스만으로 동작.
- **Zero Weight**: 최소 의존성. 핵심 라이브러리 외 추가 프레임워크 배제.
- **Zero Fee**: LM Studio 로컬 추론. 클라우드 API 비용 없음.

---

## 2. 시스템 아키텍처

```
[User - Telegram App]
        ↕ Long Polling
[cl0w Bot (Python)]
    ├── Session Manager      # 유저별 대화 히스토리
    ├── Persona Manager      # 마크다운 파일 기반 시스템 프롬프트
    ├── Skill Manager        # 마크다운 파일 기반 프롬프트 템플릿
    ├── File Handler         # 이미지/문서/코드 파일 처리
    ├── MCP Manager          # 로컬 mcp.json → 도구 서버 관리
    └── LLM Client           # LM Studio OpenAI-compatible API
            ↕ HTTP (127.0.0.1)
[LM Studio Local Server]
```

### 2.1 기술 스택

| 구성 요소 | 기술 | 비고 |
|---|---|---|
| Interface | Telegram Bot API | Long Polling |
| Runtime | Python 3.9+ | 경량 단일 프로세스 |
| LLM Engine | LM Studio (Local) | OpenAI-compatible API |
| API Client | `openai` SDK | `base_url` 로컬로 지정 |
| MCP | Custom JSON-RPC Client | stdio / SSE 모두 지원 |
| Persona | Markdown 파일 | `personas/` 디렉토리 |
| Skill | Markdown + Frontmatter | `skills/` 디렉토리 |
| 문서 파싱 | `pypdf`, `python-docx` | PDF, Word 처리 |
| 설정 | `.env` + `mcp.json` | 민감정보 분리 |

---

## 3. 디렉토리 구조

```
cl0w/
├── bot.py                  # Telegram 봇 진입점 및 핸들러
├── config.py               # .env 로드, 전역 설정
├── llm.py                  # LM Studio API 호출 및 tool_call 루프
├── mcp_client.py           # MCP stdio/SSE 클라이언트 (기존 유지)
├── persona_manager.py      # Persona 로드/전환/초기화
├── skill_manager.py        # Skill 로드/실행
├── file_handler.py         # 파일 타입별 파싱 및 메시지 구성
├── personas/
│   ├── default.md          # 기본 Persona
│   ├── coder.md            # 개발 전문 Persona
│   └── analyst.md          # 데이터 분석 Persona
├── skills/
│   ├── translate.md        # 번역 Skill
│   ├── summarize.md        # 요약 Skill
│   ├── review.md           # 코드 리뷰 Skill
│   └── explain.md          # 개념 설명 Skill
├── mcp.json                # MCP 서버 설정 (프로젝트 로컬)
├── .env                    # 환경변수 (gitignore)
├── .env.example            # 환경변수 템플릿
└── requirements.txt
```

---

## 4. 기능 명세

### 4.1 세션 관리 (기존 유지 + 확장)

- `user_id`별 대화 히스토리 메모리 보관
- `/new` 명령 시 히스토리 초기화 (현재 Persona는 유지)
- `/start` 명령 시 히스토리 + Persona 모두 초기화 (default로 복귀)
- 세션 시작 시 현재 날짜/시간 시스템 프롬프트에 자동 주입

---

### 4.2 Persona 기능

#### 개념

`personas/` 디렉토리의 `.md` 파일 하나가 곧 하나의 Persona.
파일 내용이 **그대로 시스템 프롬프트**로 사용된다.
Frontmatter로 표시 이름과 설명을 지정한다.

#### Persona 파일 형식

```markdown
---
name: Coder
description: 코드 작성과 리뷰에 특화된 전문 개발자 어시스턴트
---

당신은 숙련된 풀스택 개발자입니다.
코드 작성 시 항상 명확한 주석과 함께 최적화된 코드를 제공합니다.
...
```

#### Persona 명령어

| 명령어 | 동작 |
|---|---|
| `/persona` | 현재 활성 Persona 이름과 설명 표시 |
| `/persona list` | 사용 가능한 Persona 목록 표시 |
| `/persona set <name>` | 해당 Persona로 전환 (대화 히스토리 초기화) |
| `/persona reset` | default Persona로 복귀 (대화 히스토리 초기화) |

#### Persona Manager 동작

- 봇 시작 시 `personas/` 디렉토리의 모든 `.md` 파일 로드
- 유저별로 현재 활성 Persona 상태 보관 (`user_persona` dict)
- Persona 전환 시 해당 유저의 세션 시스템 프롬프트를 즉시 교체
- `default.md`가 없으면 기본 하드코딩 프롬프트 사용

---

### 4.3 Skill 기능

#### 개념

반복적으로 사용하는 프롬프트 패턴을 파일로 저장하고 명령어로 호출하는 기능.
Claude Code의 `/skill` 개념과 유사하게, 유저 메시지에 Skill 프롬프트를 결합하여 LLM에 전달한다.

#### Skill 파일 형식

```markdown
---
name: translate
description: 텍스트를 지정한 언어로 번역
usage: /translate <언어> <텍스트>
---

다음 텍스트를 {{language}}로 자연스럽게 번역해주세요.
번역 결과만 출력하고 설명은 생략하세요.

번역할 텍스트:
{{input}}
```

- `{{input}}`: 유저가 입력한 내용으로 치환
- `{{language}}`: 추가 인자로 치환 (선택적)
- 인자가 없는 Skill은 유저 메시지 전체를 `{{input}}`으로 사용

#### Skill 명령어

| 명령어 | 동작 |
|---|---|
| `/skill` 또는 `/skill list` | 사용 가능한 Skill 목록과 usage 표시 |
| `/skill <name> [args...]` | 해당 Skill 실행 |
| `/<name> [args...]` | Skill 단축 명령 (등록된 Skill 이름으로 직접 호출) |

**예시:**
```
/translate 영어 안녕하세요, 오늘 날씨가 좋네요.
/summarize
/review
```

`/summarize`, `/review` 처럼 인자 없이 호출 시 — 이전 대화 컨텍스트를 `{{input}}`으로 사용.

#### Skill Manager 동작

- 봇 시작 시 `skills/` 디렉토리의 모든 `.md` 파일 로드
- Frontmatter 파싱으로 name, description, usage 추출
- 명령어 수신 시 템플릿의 `{{placeholder}}`를 인자로 치환
- 치환된 프롬프트를 유저 메시지로 세션에 추가 후 LLM 호출

---

### 4.4 MCP 설정 편의 기능

#### 설정 파일 위치 변경

- 기존: `~/.lmstudio/mcp.json` (LM Studio 전역 설정에 의존)
- 변경: 프로젝트 루트의 `mcp.json` (cl0w 전용 설정)
- `.env`의 `MCP_CONFIG_PATH` 변수로 경로 오버라이드 가능

#### mcp.json 형식 (기존과 동일, Claude Desktop 호환)

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    },
    "exa": {
      "url": "https://mcp.exa.ai/mcp",
      "env": { "EXA_API_KEY": "your-key" }
    }
  }
}
```

#### MCP 명령어

| 명령어 | 동작 |
|---|---|
| `/mcp` 또는 `/mcp list` | 현재 실행 중인 MCP 서버와 등록된 tool 목록 표시 |
| `/mcp reload` | `mcp.json` 재읽기 후 모든 서버 재시작 |
| `/mcp status` | 각 서버의 실행 상태(정상/오류) 표시 |

---

### 4.5 파일 처리 기능

#### 지원 파일 타입

| 타입 | 확장자 | 처리 방식 |
|---|---|---|
| 이미지 | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` | Base64 인코딩 → Vision API |
| PDF | `.pdf` | 텍스트 추출 (`pypdf`) → 텍스트 메시지로 전달 |
| Word | `.docx` | 텍스트 추출 (`python-docx`) → 텍스트 메시지로 전달 |
| 텍스트 | `.txt`, `.md`, `.csv` | 직접 읽기 → 텍스트 메시지로 전달 |
| 코드 | `.py`, `.js`, `.ts`, `.go`, `.java`, `.cpp` 등 | 코드 블록으로 포매팅 → 텍스트 메시지로 전달 |

#### 파일 처리 동작

1. Telegram `Document` 타입 메시지 수신
2. `file_handler.py`가 확장자로 타입 판별
3. 타입에 맞는 파서로 콘텐츠 추출
4. 캡션이 있으면 지시사항 + 파일 내용, 없으면 기본 안내 메시지
5. 세션에 추가 후 LLM 호출

#### 처리 한계 및 정책

- 단일 파일 최대 크기: 20MB (Telegram Bot API 제한)
- PDF/Word 텍스트 추출 실패 시 "파일을 읽을 수 없어요" 메시지 반환
- 지원하지 않는 파일 타입 수신 시 지원 형식 안내

---

### 4.6 공통 명령어

| 명령어 | 동작 |
|---|---|
| `/start` | 봇 시작, 세션 + Persona 전체 초기화 |
| `/new` | 대화 히스토리만 초기화 (Persona 유지) |
| `/help` | 전체 명령어 목록과 사용법 안내 |
| `/status` | 현재 Persona, 활성 MCP 서버, LLM 연결 상태 표시 |

---

## 5. 모듈 설계

### 5.1 `persona_manager.py`

```python
class PersonaManager:
    def __init__(self, personas_dir: str)
    def load_all(self) -> dict[str, Persona]         # 파일 전체 로드
    def get(self, name: str) -> Persona              # 이름으로 조회
    def list_all(self) -> list[Persona]              # 목록 반환
    def get_system_prompt(self, name: str) -> str    # 시스템 프롬프트 문자열 반환

class Persona:
    name: str
    description: str
    system_prompt: str                               # frontmatter 제외한 본문
```

### 5.2 `skill_manager.py`

```python
class SkillManager:
    def __init__(self, skills_dir: str)
    def load_all(self) -> dict[str, Skill]
    def get(self, name: str) -> Skill | None
    def list_all(self) -> list[Skill]
    def render(self, name: str, args: list[str], context: str = "") -> str

class Skill:
    name: str
    description: str
    usage: str
    template: str                                    # frontmatter 제외한 본문
```

### 5.3 `file_handler.py`

```python
async def handle_document(update, context, session) -> str
def extract_text_from_pdf(bytes: bytes) -> str
def extract_text_from_docx(bytes: bytes) -> str
def build_text_message(content: str, caption: str | None, filename: str) -> dict
def build_image_message(base64_data: str, mime_type: str, caption: str | None) -> dict
```

### 5.4 `bot.py` 주요 핸들러 추가

```python
# 기존
handle_text()
handle_photo()

# 추가
handle_document()           # 문서/파일 처리
persona_cmd()               # /persona 명령어
skill_cmd()                 # /skill 명령어
mcp_cmd()                   # /mcp 명령어
status_cmd()                # /status 명령어
help_cmd()                  # /help 명령어
dynamic_skill_cmd()         # /<skill-name> 단축 명령어
```

---

## 6. 설정 파일

### 6.1 `.env` 항목

```dotenv
# Telegram
TELEGRAM_BOT_TOKEN=
ALLOWED_USER_IDS=123456,789012

# LM Studio
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LM_STUDIO_API_KEY=lm-studio
LM_STUDIO_MODEL=local-model

# cl0w 설정
MCP_CONFIG_PATH=./mcp.json          # 기본값: 프로젝트 루트 mcp.json
PERSONAS_DIR=./personas             # 기본값
SKILLS_DIR=./skills                 # 기본값
DEFAULT_PERSONA=default             # 기본 Persona 이름
LLM_TEMPERATURE=0.7
LLM_MAX_TOOL_LOOPS=5
```

### 6.2 `mcp.json` 예시

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "~/Documents"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "your-key-here"
      }
    }
  }
}
```

---

## 7. 보안

- `.env`, `mcp.json`의 API 키 등 민감정보 → `.gitignore`에 포함
- 화이트리스트(`ALLOWED_USER_IDS`) 기반 접근 제한 유지
- LLM과의 통신은 loopback(`127.0.0.1`)만 사용
- 파일 처리 시 크기 제한 및 타입 검증

---

## 8. 에러 처리

| 상황 | 동작 |
|---|---|
| LM Studio 미가동 | "LLM 서버에 연결할 수 없어요. LM Studio가 실행 중인지 확인해주세요." |
| MCP 서버 시작 실패 | 해당 서버만 비활성화, 나머지는 정상 동작 |
| 지원하지 않는 파일 | 지원 파일 형식 목록 안내 |
| Persona 파일 없음 | "해당 Persona를 찾을 수 없어요. `/persona list`로 확인해주세요." |
| Skill 파일 없음 | "해당 Skill이 없어요. `/skill list`로 확인해주세요." |
| 응답이 길 경우 | 4050자 단위로 분할 전송 (기존 방식 유지) |

---

## 9. 구현 우선순위

| 단계 | 내용 | 핵심 파일 |
|---|---|---|
| Phase 1 | 기존 코드 이관 + 프로젝트 구조 세팅 | `bot.py`, `config.py`, `llm.py`, `mcp_client.py` |
| Phase 2 | Persona 기능 | `persona_manager.py`, `personas/` |
| Phase 3 | Skill 기능 | `skill_manager.py`, `skills/` |
| Phase 4 | 파일 처리 확장 (문서/코드) | `file_handler.py` |
| Phase 5 | MCP 명령어 편의 기능 | `mcp_client.py` 확장, `bot.py` 핸들러 추가 |
| Phase 6 | `/status`, `/help` 등 UX 개선 | `bot.py` |

---

## 10. 구현 체크리스트

### 환경 설정
- [ ] Telegram BotFather에서 봇 토큰 발급
- [ ] `.env` 작성 (`TELEGRAM_BOT_TOKEN`, `ALLOWED_USER_IDS`)
- [ ] LM Studio API Server 활성화 (포트 1234 기본)
- [ ] `mcp.json` 작성 (사용할 MCP 서버 설정)

### 코어 기능
- [ ] `bot.py` — 기존 핸들러 이관 및 명령어 확장
- [ ] `config.py` — 새 환경변수 항목 추가
- [ ] `llm.py` — model, temperature 설정 주입 가능하도록 수정
- [ ] `mcp_client.py` — 경로 설정 유연화, status 조회 기능 추가

### Persona
- [ ] `persona_manager.py` 구현
- [ ] `personas/default.md` 작성
- [ ] `/persona` 명령어 핸들러 구현

### Skill
- [ ] `skill_manager.py` 구현
- [ ] 기본 Skill 파일 3종 이상 작성 (`translate`, `summarize`, `review`)
- [ ] `/skill` 명령어 및 `/<name>` 단축 명령어 핸들러 구현

### 파일 처리
- [ ] `file_handler.py` 구현 (PDF, docx, text, code)
- [ ] `handle_document()` 핸들러 `bot.py`에 등록
- [ ] `requirements.txt`에 `pypdf`, `python-docx` 추가

### UX
- [ ] `/help` 명령어 — 전체 명령어 안내
- [ ] `/status` 명령어 — Persona/MCP/LLM 상태 표시
- [ ] `/mcp list`, `/mcp reload` 명령어
