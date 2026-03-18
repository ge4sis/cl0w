<div align="center">

<pre>
 ██████╗██╗      ██████╗ ██╗    ██╗
██╔════╝██║     ██╔═████╗██║    ██║
██║     ██║     ██║██╔██║██║ █╗ ██║
██║████╗██║     ████╔╝██║██║███╗██║
╚██████╔╝███████╗╚██████╔╝╚███╔███╔╝
 ╚═════╝ ╚══════╝ ╚═════╝  ╚══╝╚══╝
</pre>

**Lightweight · Secure · Soulful Agent Gateway**

*One bot. Every LLM. Zero hassle.*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
[![Lines of Code](https://img.shields.io/badge/bot.py-702%20lines-f59e0b?style=flat-square)]()
[![Dependencies](https://img.shields.io/badge/dependencies-4%2B-a855f7?style=flat-square)]()
[![Container](https://img.shields.io/badge/container-ready-0ea5e9?style=flat-square&logo=docker&logoColor=white)]()

[한국어 문서 →](README.ko.md)

</div>

---

## Why cl0w?

Most agent frameworks are bloated, insecure, and painful to configure.
**cl0w** is different — it fits in a single Python file and runs inside an isolated container, yet connects to every major LLM and lets you plug in tools in seconds.

| | OpenClaw | cl0w |
|---|---|---|
| Core logic | multiple files, 2000+ lines | **single file, 702 lines** |
| Dependencies | 15+ | **4 core + optional** |
| Security | process-level | **container-isolated, read-only rootfs** |
| Interface | web UI / REST | **Telegram (zero port exposure)** |
| Tool install | restart required | **drop a file, done** |
| Persona | none | **markdown-defined soul** |

---

## Features

### 🔐 Security-first Architecture
Runs exclusively inside an **Apple Container** (macOS) or **OCI container** (Linux) with a read-only root filesystem. No inbound ports — Telegram polling means your server is invisible to the internet. Secrets are injected via environment variables only; no plaintext API keys, ever.

### 🧠 Every LLM, One Interface
All providers speak OpenAI-compatible REST, so a single `httpx` client handles everything — no per-provider SDK bloat.

| Provider | Type |
|----------|------|
| OpenAI (GPT-4o, o-series) | Cloud |
| Anthropic Claude (Sonnet / Opus / Haiku) | Cloud |
| Google Gemini (1.5 Pro / Flash) | Cloud |
| LM Studio | Local |
| Ollama | Local |
| Any OpenAI-compatible endpoint | Custom |

Switch providers mid-conversation with `/provider claude`. Automatic fallback chain if a provider goes down.

### 🔌 Tools in Seconds
Drop a `.py` file into `tools/`. It's live — no restart, no config change.
Pull the file out. It's gone.

```python
# tools/my_tool.py  ← that's it
TOOL_SCHEMA = {
    "name": "my_tool",
    "description": "Does something useful",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

def run(query: str) -> str:
    return f"result for {query}"
```

### 🔗 MCP Server Integration
Connect any [Model Context Protocol](https://modelcontextprotocol.io) server — no extra SDK needed if you have the optional `mcp` package.

Configure in `config.yaml`, and cl0w auto-connects at startup. Add or remove servers by editing the file — the bot detects the change and reconnects within 10 seconds, **no restart required**.

```yaml
# config.yaml
mcp_servers:

  # stdio — run an MCP server as a subprocess
  filesystem:
    transport: stdio
    command: uvx
    args: ["mcp-server-filesystem", "/tmp"]

  # SSE — connect to an already-running MCP HTTP server
  my_api:
    transport: sse
    url: http://localhost:3000/sse
```

All tools registered by MCP servers appear alongside Python tools in `/tools` — the LLM calls them the same way.

### 🎭 Persona / Soul System
Give your agent a real identity. Write a markdown file — the agent's personality, tone, constraints, and attitude. It becomes the foundation of every response, across every LLM.

```markdown
## Identity
Name: Crow
One-liner: Sharp, honest AI partner

## Tone & Manner
- No fluff, straight to the point
- Dry humor, briefly
- Push back on wrong premises without hesitation
```

Switch personas on the fly: `/persona switch technical`

### 💬 Telegram-native UX
- **Streaming responses** — messages update in real-time as the LLM generates
- **File & image support** — send a photo, PDF, or code file; cl0w handles it
- **Per-user sessions** — persistent conversation history, per user
- **Multi-user** — allowlist multiple Telegram IDs, each with independent settings

---

## What Can You Actually Do With It?

cl0w is not a chatbot. It's a **personal agent** that lives in your Telegram and acts on your behalf — browsing the web, reading your files, calling APIs, and chaining actions together autonomously.

Here are real things you can do on day one.

---

### 🔍 Use Case 1 — Research on Demand

> Drop `tools/web_search.py`. Ask a question that requires current knowledge.

```
You:   What are the key differences between the new Claude 4 and GPT-5?
       Give me a structured comparison I can share with my team.

Crow:  🔧 web_search({"query": "Claude 4 vs GPT-5 comparison 2025"})
       🔧 web_search({"query": "GPT-5 capabilities benchmarks"})

       Here's the breakdown:

       **Context window**: Claude 4 — 200K tokens / GPT-5 — 128K tokens
       **Code**: GPT-5 edges out on competitive benchmarks...
       **Reasoning**: Claude 4 shows stronger multi-step logic...
       ...
```

The agent searches, synthesizes, and formats — without you lifting a finger.

---

### 📄 Use Case 2 — Document Intelligence

> Send any file. cl0w reads it and reasons over it.

```
You:   [attaches contract.pdf — 42 pages]
       What are the termination clauses and any hidden liabilities?

Crow:  Reading 42 pages...

       Found 3 termination clauses:
       — Section 8.2: Either party may terminate with 30-day notice...
       — Section 11.4: Immediate termination if NDA is breached...

       ⚠️  Hidden liability in Section 14.1:
       You are liable for data retention costs even after termination.
       This is unusual — most contracts put this on the vendor.
```

Works with PDFs, code files, CSVs, logs, markdown — anything text-based.

---

### 🔒 Use Case 3 — Privacy Mode with Local LLM

> Sensitive documents shouldn't leave your machine. Switch to Ollama mid-conversation.

```
You:   /provider ollama

Crow:  ✅ Switched to ollama (llama3)

You:   [attaches salary_review.pdf]
       Summarize this and suggest talking points for my negotiation.

Crow:  [Processed entirely on your machine — zero data sent to cloud]

       Summary: Your current package is 12% below market rate for your role...
       Talking points:
       1. Reference the market data in Section 3...
```

One command. Full privacy. No cloud API touched.

---

### 🎭 Use Case 4 — Persona-Driven Workflows

> Different tasks need different attitudes. Switch persona, switch mode.

```
You:   /persona switch technical

Crow:  ✅ Persona → technical  (now: Hex)

You:   Review this Python function for production readiness.
       [attaches utils.py]

Hex:   Issues found:

       [CRITICAL] Line 23: No exception handling on file I/O.
       [WARN]     Line 41: Mutable default argument `def fn(data=[]):`
       [WARN]     Line 67: Magic number 86400 — use `datetime.timedelta`
       [INFO]     No type hints. Add for maintainability.

       Refactored version:
       ```python
       def fn(data: list[str] | None = None) -> dict:
           data = data or []
           ...
```

Then switch to `/persona switch friendly` when you need to explain the same code to a non-technical teammate.

---

### 🤖 Use Case 5 — Custom Tool in 10 Lines

> Your company has an internal API. Connect it in minutes.

```python
# tools/jira_create.py
import httpx, os

TOOL_SCHEMA = {
    "name": "jira_create_ticket",
    "description": "Create a Jira ticket from a description",
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
    r = httpx.post(f"{os.environ['JIRA_URL']}/rest/api/3/issue",
                   auth=(os.environ['JIRA_USER'], os.environ['JIRA_TOKEN']),
                   json={"fields": {"summary": summary, "description": {"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":description}]}]}, "priority": {"name": priority}}})
    return f"Created: {r.json().get('key')}"
```

Drop this file in `tools/`. Now:

```
You:   The login page crashes on iOS Safari — create a Jira ticket,
       High priority, assign to the mobile team.

Crow:  🔧 jira_create_ticket({
           "summary": "Login page crash on iOS Safari",
           "description": "Reported crash on login page...",
           "priority": "High"
       })

       Created: MOB-2847
```

No deploy. No restart. The agent gained a new capability the moment you saved the file.

---

### 🔗 Use Case 6 — Agentic Chain (Multi-Step Autonomous)

> Give a complex goal. The agent figures out the steps.

```
You:   I need to prepare for my meeting with Acme Corp tomorrow.
       Find recent news about them, check if they have any open positions
       (signals of growth), and summarize what I should know in 3 bullets.

Crow:  🔧 web_search({"query": "Acme Corp news 2025"})
       🔧 web_search({"query": "Acme Corp jobs hiring 2025"})
       🔧 web_search({"query": "Acme Corp funding revenue"})

       Here's your meeting brief:

       • 📈 Growth signal: Acme is hiring 40+ engineers — Series B likely imminent.
       • 📰 Recent news: Partnership with AWS announced last month — cloud-first pivot.
       • ⚠️  Watch out: CEO publicly critical of vendor lock-in — lead with flexibility.
```

This is the agentic loop at work: the LLM plans, executes tools, reads results, and plans again — all before it sends you a single message.

---

### 💡 What Else Can You Build?

| Idea | Tools needed |
|------|-------------|
| Daily news briefing (scheduled) | `web_search` + cron job calling `/start` |
| GitHub PR reviewer | `github_api` tool |
| SQL query assistant | `db_query` tool |
| Home automation voice | `home_assistant` tool + Telegram voice |
| Personal expense tracker | `spreadsheet_read` + `web_search` |
| Language learning tutor | Custom persona (`tutor.md`) + no tools needed |
| Competitive intelligence monitor | `web_search` + `notify` tool |

Every new capability is a single Python file. The agent assembles the pieces.

---

## Platform Support

| Platform | Container | Direct Python |
|----------|-----------|---------------|
| macOS (Apple Silicon / Intel) | Apple Container or Docker Desktop | `./run.sh` |
| Linux | Docker Engine | `./run.sh` |
| **Windows** | Docker Desktop (WSL2) | `.\run.ps1` |

> **No platform is left behind.** cl0w runs anywhere Python 3.12 runs.

---

## Quick Start

Choose your path:

### Option A — Docker (recommended, all platforms)

**Prerequisites:** Docker Desktop (Windows / macOS) or Docker Engine (Linux)

```bash
# 1. Clone
git clone https://github.com/your-org/cl0w.git && cd cl0w

# 2. Configure secrets
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, API keys
```

**macOS / Linux:**
```bash
docker compose up --build
```

**Windows (Docker Desktop):**
```bash
# Uses docker-compose.windows.yml to remove the Linux-only extra_hosts entry
docker compose -f docker-compose.yml -f docker-compose.windows.yml up --build
```

> Local LLMs (Ollama / LM Studio): `host.docker.internal` resolves automatically on Docker Desktop — no extra config needed.

---

### Option B — Direct Python (no Docker)

**macOS / Linux:**
```bash
pip install -r requirements.txt python-dotenv
cp .env.example .env   # fill in your tokens
./run.sh
```

**Windows (PowerShell):**
```powershell
pip install -r requirements.txt python-dotenv
Copy-Item .env.example .env   # fill in your tokens
.\run.ps1
```

> Without Docker, container isolation is not active. Recommended for local development only.

---

```bash
# 3. (Optional) Edit your agent's persona
nano persona.md       # macOS / Linux
notepad persona.md    # Windows

# 4. Done — message your bot on Telegram
```

---

## File Structure

```
cl0w/
├── bot.py              ← entire gateway (702 lines)
├── config.yaml         ← all settings (providers, MCP servers, limits)
├── persona.md          ← active persona (hot-reloaded)
├── .env                ← secrets (never committed)
├── Dockerfile
├── docker-compose.yml
├── docker-compose.windows.yml
├── run.sh / run.ps1    ← direct-run scripts (macOS·Linux / Windows)
├── requirements.txt    ← 4 core packages (+ optional mcp)
│
├── tools/              ← drop .py files here to add tools (subdirs OK)
│   └── web_search.py   ← example: DuckDuckGo (no API key needed)
│
├── personas/           ← persona library
│   ├── friendly.md     ← Sol (warm helper)
│   └── technical.md    ← Hex (precision engineer)
│
└── sessions/           ← auto-created, per-user conversation history
```

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| *(any text)* | Chat with the current LLM |
| `/help` | Show available commands |
| `/provider <name>` | Switch LLM provider (`claude`, `openai`, `ollama`, …) |
| `/tools` | List active tools |
| `/persona` | Show current persona |
| `/persona switch <name>` | Hot-swap to a different persona |
| `/status` | Provider · model · persona · tool count |
| `/reset` | Clear conversation history |

---

## Configuration

`config.yaml` controls everything. The most useful knobs:

```yaml
default_provider: claude

fallback_chain:       # auto-failover order
  - claude
  - openai

providers:
  ollama:
    base_url: http://host.docker.internal:11434/v1
    model: llama3

rate_limit: 20        # messages per minute per user

session:
  persist: true
  max_turns: 50

hot_reload_interval: 5   # seconds between tool directory scans

# MCP servers (optional — requires: pip install mcp)
# Changes detected automatically — no restart needed
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

## Adding a Local LLM

**Ollama**
```yaml
# config.yaml
providers:
  ollama:
    base_url: http://host.docker.internal:11434/v1
    model: llama3       # any model you've pulled
```

**LM Studio**
```yaml
providers:
  lmstudio:
    base_url: http://host.docker.internal:1234/v1
    model: local-model
```

> `host.docker.internal` resolves to your host machine from inside the container.
> On Apple Container, use `host.internal` instead.

---

## Security Model

```
┌─────────────────────────────────────────────────┐
│  Container (read-only rootfs)                   │
│                                                 │
│  • non-root UID                                 │
│  • no inbound ports (polling only)              │
│  • secrets via env / tmpfs only                 │
│  • user allowlist (Telegram ID)                 │
│  • rate limit per user                          │
│  • tool execution timeout (30s)                 │
│  • file size cap (20 MB)                        │
│                                                 │
│  writable volumes (isolated):                   │
│    /app/tools    ← plugin bind-mount            │
│    /app/sessions ← named volume                 │
└─────────────────────────────────────────────────┘
```

---

## Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Runtime | Python 3.12 | Broad LLM ecosystem |
| Telegram | python-telegram-bot | Async, polling + webhook |
| HTTP | httpx | Single async client for all LLMs |
| Config | pyyaml | Minimal, human-readable |
| PDF parsing | pypdf | Pure Python, ~500 KB |
| **Total deps** | **4 core** | That's the whole list |
| MCP client | mcp *(optional)* | stdio + SSE transport |

---

## Roadmap

- [x] MCP server integration (stdio + SSE, hot-reload)
- [ ] Voice message → text (Whisper via Tool)
- [ ] Multi-agent orchestration (agent-to-agent calls)
- [ ] Web UI companion (read-only dashboard)
- [ ] One-click install script (no Docker required)
- [ ] MCP server registry integration

---

## Contributing

1. Fork → branch → PR
2. Keep `bot.py` under 750 lines
3. New features go in `tools/` when possible
4. Every PR needs a one-line "why" in the description

---

## License

MIT — do whatever you want, just don't blame us.

---

<div align="center">

*Built to be small enough to read in one sitting,*
*powerful enough to replace your entire AI workflow.*

**[⭐ Star this repo](https://github.com/your-org/cl0w)** if cl0w saves you time.

[한국어 문서 →](README.ko.md)

</div>
