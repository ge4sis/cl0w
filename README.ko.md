<div align="right">

[English Version →](README.md)

</div>

<div align="center">
<pre>
  ██████╗██╗      ██████╗ ██╗    ██╗
 ██╔════╝██║     ██╔═████╗██║    ██║
 ██║     ██║     ██║██╔██║██║ █╗ ██║
 ██║████╗██║     ████╔╝██║██║███╗██║
 ╚██████╔╝███████╗╚██████╔╝╚███╔███╔╝
  ╚═════╝ ╚══════╝ ╚═════╝  ╚══╝╚══╝
</pre>

**번거로움도, 부담도, 비용도 없는 AI Agent.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LM Studio](https://img.shields.io/badge/LLM-LM%20Studio-8B5CF6)](https://lmstudio.ai)
[![Telegram](https://img.shields.io/badge/Interface-Telegram-2CA5E0?logo=telegram&logoColor=white)](https://telegram.org)
[![MCP](https://img.shields.io/badge/Tools-MCP%20Compatible-F97316)](https://modelcontextprotocol.io)
[![Runs Local](https://img.shields.io/badge/완전%20로컬-100%25%20Local-22C55E)](https://lmstudio.ai)
[![License](https://img.shields.io/badge/License-MIT-6B7280)](LICENSE)

</div>

cl0w는 사용자의 컴퓨터에서 완전히 동작하는 개인용 AI Agent입니다.
[LM Studio](https://lmstudio.ai)로 로컬 LLM을 구동하고, Telegram을 통해 어디서든 대화할 수 있습니다.
구독료도, 클라우드 API도, 데이터 외부 전송도 없습니다.

단순한 챗봇이 아닙니다. **Agent**입니다.
추론하고, MCP 도구를 직접 실행하고, 페르소나를 전환하고, 재사용 가능한 Skill을 실행하고, 파일을 이해합니다 — 텔레그램 메시지 하나로.

---

## 왜 cl0w인가요?

| | OpenClaw | cl0w |
|---|---|---|
| **비용** | 구독료 또는 API 과금 | 영구 무료 |
| **프라이버시** | 대화가 클라우드 서버에서 처리됨 | 사용자 기기 밖으로 나가지 않음 |
| **LLM** | 벤더 관리 클라우드 모델 | LM Studio로 로컬 모델 직접 운용 |
| **커스터마이징** | 웹 UI 또는 설정 파일 수준 | 순수 Markdown — 완전히 내 것 |
| **도구 연동** | 내장 도구 생태계 | 원하는 MCP 서버 자유롭게 연결 |
| **인터페이스** | CLI / IDE 확장 | Telegram — 어떤 기기에서든 |
| **인터넷 필요** | 항상 필요 | 초기 설치 이후 불필요 |

---

## 핵심 기능

### Agent 수준의 도구 사용 (MCP)
cl0w는 [Model Context Protocol(MCP)](https://modelcontextprotocol.io) 서버와 연동하여 LLM에게 실제 도구를 제공합니다.
파일 시스템 접근, 웹 검색, 코드 실행, DB 쿼리 등 — `mcp.json`에 설정하면 Agent가 필요한 시점에 자동으로 호출합니다.

### Persona 시스템
AI의 성격과 역할을 Markdown 파일로 정의합니다. 명령어 하나로 전환할 수 있습니다.
Persona는 곧 시스템 프롬프트입니다 — 어떻게 생각하고 어떻게 말할지를 완전히 직접 제어할 수 있습니다.

### Skill 시스템
자주 사용하는 프롬프트 패턴을 Markdown 파일로 저장하고 슬래시 명령어로 실행합니다.
기본 제공 Skill: 번역, 요약, 코드 리뷰, 개념 설명. 파일 하나만 추가하면 나만의 Skill을 바로 만들 수 있습니다.

### 파일 이해
파일을 전송하면 자동으로 처리합니다:
- **이미지** — 멀티모달 LLM으로 시각적 분석
- **PDF** — 전체 텍스트 추출 후 질의응답
- **Word 문서(.docx)** — 내용 분석 및 요약
- **코드 파일** — 리뷰, 설명, 리팩토링 제안
- **텍스트 / CSV / JSON** — 모든 텍스트 기반 형식

### Zero Weight (경량 설계)
"Zero Weight" 철학에 따라 매우 가볍고 효율적으로 설계되었습니다. 최소한의 시스템 리소스를 사용하며, 코드 구조가 단순하고 무거운 의존성을 배제하여 저사양 하드웨어에서도 로컬 LLM과 함께 원활하게 작동합니다.

### 보안 설계
- 모든 LLM 추론은 `127.0.0.1` 내부에서 처리 — 데이터가 외부로 전송되지 않습니다
- 텔레그램 화이트리스트: 등록된 user ID만 봇과 대화 가능
- 인바운드 포트 개방 불필요 (Long Polling 방식)
- API 키는 `.env`와 `mcp.json`에만 저장 — 두 파일 모두 기본적으로 `.gitignore` 처리

---

## 보안 상세

cl0w는 처음부터 보안을 중심에 두고 설계되었습니다:

```
[텔레그램 앱 (사용자 기기)]
        ↕  HTTPS (텔레그램 서버 경유)
[cl0w Bot — 로컬 머신]
        ↕  127.0.0.1 전용
[LM Studio — 로컬 추론]
```

| 위협 | 방어 방법 |
|---|---|
| 무단 접근 | 텔레그램 user ID 화이트리스트 (`ALLOWED_USER_IDS`) |
| 데이터 유출 | LLM이 로컬에서 동작 — 클라우드 API 미사용 |
| 자격증명 노출 | `.env`와 `mcp.json`은 `.gitignore`에 포함 |
| 네트워크 노출 | Long Polling만 사용 — 인바운드 포트 완전 차단 |
| 파일을 통한 공격 | 단일 파일 20MB 제한, 텍스트 20,000자 자동 트런케이션 |

---

## 빠른 시작

### 1. 사전 준비

- Python 3.9 이상
- [LM Studio](https://lmstudio.ai) — 모델 로드 후 로컬 서버 실행 상태
- [@BotFather](https://t.me/BotFather)에서 발급한 텔레그램 봇 토큰
- 본인의 텔레그램 user ID ([`@userinfobot`](https://t.me/userinfobot)으로 확인)

### 2. 설치

```bash
git clone https://github.com/yourname/cl0w.git
cd cl0w
```

**macOS / Linux / Git Bash (Windows)**
```bash
chmod +x setup.sh start.sh
./setup.sh
```

**Windows (명령 프롬프트)**
```bat
setup.bat
```

셋업 스크립트가 자동으로 수행하는 작업:
- `.venv` 가상환경 생성
- 의존성 전체 설치
- `.env.example` → `.env`, `mcp.json.example` → `mcp.json` 복사 (파일이 없을 경우)

### 3. 설정

`.env` 파일을 편집합니다:
```dotenv
TELEGRAM_BOT_TOKEN=텔레그램-봇-토큰
ALLOWED_USER_IDS=본인-텔레그램-user-id
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LM_STUDIO_MODEL=local-model
```

`mcp.json`에 사용할 MCP 서버를 추가하거나, 비워두면 채팅 전용 모드로 동작합니다.

### 4. 실행

**macOS / Linux / Git Bash**
```bash
./start.sh
```

**Windows (명령 프롬프트)**
```bat
start.bat
```

또는 venv를 직접 활성화하여 실행:
```bash
source .venv/bin/activate   # macOS/Linux
.venv\Scripts\activate      # Windows
python bot.py
```

텔레그램에서 봇을 검색한 후 `/start`를 전송하면 시작됩니다.

---

## 명령어

### 기본
| 명령어 | 설명 |
|---|---|
| `/start` | 대화 히스토리 + Persona 전체 초기화 |
| `/new` | 대화 히스토리만 초기화 (Persona 유지) |
| `/status` | 현재 Persona, LLM 엔드포인트, MCP 서버 상태 표시 |
| `/help` | 전체 명령어 가이드 |

### Persona
| 명령어 | 설명 |
|---|---|
| `/persona` | 현재 활성 Persona 확인 |
| `/persona list` | 사용 가능한 Persona 목록 |
| `/persona set <name>` | Persona 전환 (대화 히스토리 초기화) |
| `/persona reset` | 기본 Persona로 복귀 |

### Skill
| 명령어 | 설명 |
|---|---|
| `/skill` | 사용 가능한 Skill 목록 |
| `/translate <언어> <텍스트>` | 텍스트 번역 |
| `/summarize [텍스트]` | 텍스트 또는 직전 응답 요약 |
| `/review <코드>` | 코드 리뷰 |
| `/explain <주제>` | 코드나 개념 설명 |

### MCP
| 명령어 | 설명 |
|---|---|
| `/mcp` | MCP 서버 목록과 등록된 tool 확인 |
| `/mcp reload` | `mcp.json` 재로드 후 서버 재시작 |

---

## 활용 사례

### 즉석 번역
```
사용자:  /translate 영어 이 기능은 다음 주까지 완료할 예정입니다.
cl0w:    This feature is scheduled to be completed by next week.
```

### 코드 파일 리뷰
`.py` 또는 `.js` 파일을 전송할 때 캡션을 함께 입력합니다:
```
"버그나 보안 이슈가 있으면 알려주세요."
```
cl0w가 파일을 코드로 인식하고, 이슈 / 개선 제안 / 종합 평가를 구조적으로 반환합니다.

### PDF 회의록 요약
PDF 파일을 첨부하고 요청합니다:
```
"핵심 결정 사항과 액션 아이템만 추출해주세요."
```
cl0w가 PDF 전체 텍스트를 추출하여 깔끔한 불릿 요약을 반환합니다.

### MCP로 웹 리서치
`brave-search` MCP 설정 후:
```
사용자:  이번 주 양자컴퓨터 관련 최신 뉴스를 알려주세요.
cl0w:    [자동으로 웹 검색 후 결과를 종합하여 답변]
```
도구를 직접 호출할 필요가 없습니다 — Agent가 언제 검색할지 스스로 판단합니다.

### Persona 전환
```
사용자:  /persona set coder
cl0w:    Coder 페르소나로 전환했습니다. 대화 히스토리도 초기화되었습니다.
사용자:  이 함수를 가독성 좋게 리팩토링해주세요: [코드]
cl0w:    [전문 개발자 수준의 리팩토링 + 설명]
```

### 이미지 분석
스크린샷이나 사진을 전송할 때 캡션을 입력합니다:
```
"이 UI 레이아웃에서 어떤 문제가 있나요?"
```
cl0w가 멀티모달 LLM으로 이미지를 분석하여 디자인 피드백을 제공합니다.

### 나만의 Skill 만들기
`skills/standup.md` 파일을 생성합니다:
```markdown
---
name: standup
description: 불릿 포인트를 데일리 스탠드업 형식으로 변환
usage: /standup <내용>
---

아래 내용을 전문적인 데일리 스탠드업 형식으로 작성해주세요.
형식: 어제 한 일 / 오늘 할 일 / 블로커

{{input}}
```

바로 사용 가능합니다:
```
사용자:  /standup 로그인 버그 수정, 대시보드 작업 중, 디자인 검토 대기
cl0w:    어제 한 일: 로그인 버그를 수정했습니다.
         오늘 할 일: 대시보드 기능 개발을 진행합니다.
         블로커: 디자인 팀의 검토를 기다리고 있습니다.
```

---

## 커스터마이징

### Persona 추가

`personas/mybot.md` 파일을 생성합니다:
```markdown
---
name: mybot
description: 나만의 어시스턴트
---

당신은 간결하고 직설적인 어시스턴트입니다.
항상 불릿 포인트로만 답변합니다.
불필요한 표현은 사용하지 않습니다.
```

적용: `/persona set mybot`

### MCP 서버 추가

`mcp.json` 파일을 편집합니다:
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/yourname/Documents"]
    }
  }
}
```

적용: `/mcp reload`

---

## 프로젝트 구조

```
cl0w/
├── bot.py               # 텔레그램 봇 — 모든 핸들러
├── config.py            # 설정 로더
├── llm.py               # LM Studio API 클라이언트 + tool call 루프
├── mcp_client.py        # MCP stdio/SSE 클라이언트
├── persona_manager.py   # Persona 로더
├── skill_manager.py     # Skill 로더 + 템플릿 렌더러
├── file_handler.py      # 파일 파싱 (이미지/PDF/docx/텍스트/코드)
├── personas/            # 개인 Persona (gitignore됨)
├── personas.example/    # Persona 예시
├── skills/              # 개인 Skill (gitignore됨)
├── skills.example/      # Skill 예시
├── mcp.json             # 실제 MCP 설정 (gitignore됨)
├── mcp.json.example     # MCP 설정 템플릿
├── .env                 # 실제 시크릿 (gitignore됨)
└── .env.example         # 시크릿 템플릿
```

---

## 의존성

```
python-telegram-bot==21.1.1
openai==1.52.0
python-dotenv==1.0.1
httpx<0.28.0
pypdf>=4.0.0
python-docx>=1.1.0
```

---

## 라이선스

MIT

---

## 프로젝트 응원하기

cl0w가 도움이 되었다면 GitHub에서 ⭐을 눌러주세요! 프로젝트가 더 널리 알려지는 데 큰 힘이 됩니다.

[**cl0w에 Star 주기**](https://github.com/ge4sis/cl0w)
