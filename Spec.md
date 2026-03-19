# cl0w — Zero Hassle Agent Gateway Specification

> **Concept**: "Zero Hassle, High Agency, Secure by Intent"
> 
> cl0w는 복잡한 설정 없이 즉시 개인용 AI 에이전트를 구축할 수 있도록 설계된 경량 게이트웨이입니다. 
> 시스템 격리(Docker)보다는 사용자와의 상호작용(HITL)을 통해 보안과 편의성의 균형을 잡습니다.

---

## 1. 핵심 철학
- **Zero Hassle**: `git clone` 후 즉시 실행 가능한 수준의 단순함 지향.
- **High Agency**: 에이전트가 로컬 파일과 시스템에 접근하여 실질적인 도움을 줄 수 있는 권한 부여.
- **Secure by Intent**: 물리적 격리 대신, **사용자 승인(HITL)** 및 **명확한 허용 목록(Allowed Users)**을 통한 보안 구현.

---

## 2. 아키텍처 개요
- **인터페이스**: Telegram (Bot API Polling 방식 사용, 인바운드 포트 개방 필요 없음).
- **런타임**: Python 3.12+ (기본 실행 환경: `.venv` 로컬 권장).
- **구성**:
  - `bot.py`: 단일 파일 게이트웨이 코어.
  - `tools/`: 파이썬 기반 플러그인 (핫 리로드 지원).
  - `mcp_servers`: 외부 MCP 서버 연동 (stdio / SSE).

---

## 3. 보안 매커니즘

### 3-1. 사용자 인증 (Gatekeeper)
- **Telegram User ID Allowlist**: `ALLOWED_USER_IDS` 에 등록된 사용자만 봇과 대화 가능.
- **Private Chat Only**: 기본적으로 1:1 채팅에서만 동작하여 그룹 내 예기치 않은 명령 실행 방지.

### 3-2. HITL (Human-in-the-Loop)
- **위험 도구 승인**: 파일 삭제, 시스템 명령어 실행 등 '파괴적'이거나 '시스템 변조' 가능성이 있는 도구는 실행 전 Telegram 인라인 버튼을 통해 사용자의 명시적 승인을 거침.
- **투명성**: 모든 도구의 이름과 인자(Arguments)는 실행 전후로 메시지에 표시됨.

### 3-3. 로컬 실행 권한
- 관리자(root/Admin) 권한이 아닌 일반 사용자 권한으로 실행할 것을 권장함.

---

## 4. 핵심 기능

### 4-1. 멀티 프로바이더 (LLM Router)
- **OpenAI-Interface 우선**: OpenAI(GPT) 및 OpenAI 호환 API를 공식 지원하는 로컬 LLM(Ollama, LM Studio 등)을 중심으로 지원.
- **범용 호환성**: Anthropic(Claude), Google Gemini 등 타 프로바이더는 OpenAI 호환 엔드포인트 또는 프록시(LiteLLM 등)를 통해 연결 권장.
- `/provider` 명령어로 실시간 전환 가능.

### 4-2. 확장성 (Tools & MCP)
- **Skill**: OpenAI Function Calling 규격을 따르는 파이썬 파일을 `tools/`에 넣는 것으로 기능 확장 (핫 리로드).
- **MCP**: Model Context Protocol 서버 연동을 통해 에이전트 환경(파일시스템, DB 등) 확장.

### 4-3. 파일 및 페르소나
- **파일 처리**: 이미지(Vision), PDF, 텍스트 파일 등을 컨텍스트에 포함.
- **Persona**: `personas/` 에 저장된 마크다운 파일을 통해 에이전트의 성격 실시간 전환 가능.

---

## 5. 설치 및 실행 (Zero Hassle)

### 5-1. 빠른 시작
1. 저장소 클론 및 패키지 설치:
   ```bash
   git clone <repo> && cd cl0w
   pip install -r requirements.txt
   ```
2. 환경 변수 설정 (`.env`):
   ```
   TELEGRAM_BOT_TOKEN=your_token
   ALLOWED_USER_IDS=your_id
   OPENAI_API_KEY=sk-...
   ```
3. 실행:
   ```bash
   python bot.py
   ```

---

## 6. 개발 원칙 (경량화 및 표준 지향)
- **최소 의존성**: `python-telegram-bot`, `httpx`, `pyyaml` (필수), `pypdf`, `mcp` (선택).
- **인터페이스 표준화**: 다양한 SDK를 직접 내장하는 대신, **OpenAI Chat Completions API 표준**을 상호작용의 근간으로 삼음.
- **단일 파일 코어**: 복잡한 모듈화보다는 `bot.py` 750줄 이내의 단순한 구조 유지.
- **유연한 명세**: 구체적인 구현 코드보다는 기능적 요구사항과 보안 원칙을 우선시하여 에이전트의 구현 자율성 보장.
