<div align="right">

[한국어 버전 보기 →](README.ko.md)

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

**Zero Hassle. Zero Weight. Zero Fee. Agent.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LM Studio](https://img.shields.io/badge/LLM-LM%20Studio-8B5CF6)](https://lmstudio.ai)
[![Telegram](https://img.shields.io/badge/Interface-Telegram-2CA5E0?logo=telegram&logoColor=white)](https://telegram.org)
[![MCP](https://img.shields.io/badge/Tools-MCP%20Compatible-F97316)](https://modelcontextprotocol.io)
[![Runs Local](https://img.shields.io/badge/Runs-100%25%20Local-22C55E)](https://lmstudio.ai)
[![License](https://img.shields.io/badge/License-MIT-6B7280)](LICENSE)

</div>

cl0w is a personal AI agent that runs entirely on your own machine — powered by a local LLM via [LM Studio](https://lmstudio.ai) and operated through Telegram. No subscriptions, no cloud APIs, no data leaving your device.

It's not a chatbot. It's an **agent**: it reasons, uses tools via MCP, switches personas, runs reusable skills, and processes files — all from a Telegram message.

---

## Why cl0w?

| | OpenClaw | cl0w |
|---|---|---|
| **Cost** | Subscription or API billing | Free forever |
| **Privacy** | Conversations processed on cloud servers | Never leaves your machine |
| **LLM** | Vendor-managed cloud model | Your own local model via LM Studio |
| **Customization** | Web UI or config files | Plain Markdown files — fully yours |
| **Tools** | Built-in tool ecosystem | Any MCP server you want |
| **Interface** | CLI / IDE extension | Telegram — works on any device |
| **Internet required** | Yes | No (after initial setup) |

---

## Core Features

### Agent-grade Tool Use (MCP)
cl0w integrates with [Model Context Protocol (MCP)](https://modelcontextprotocol.io) servers, giving the LLM real tools: file system access, web search, code execution, database queries, and more. Just configure `mcp.json` and the agent uses tools automatically when needed.

### Persona System
Define multiple AI personalities in plain Markdown. Switch between them with a single command. Each persona is a custom system prompt — you're in full control of how the agent thinks and communicates.

### Skill System
Save reusable prompt templates as Markdown files. Run them as slash commands. Built-in skills include translation, summarization, code review, and concept explanation. Add your own in seconds.

### File Understanding
Send a file, get an intelligent response. cl0w handles:
- **Images** — Vision analysis via multimodal LLM
- **PDFs** — Full text extraction and Q&A
- **Word documents** — Content analysis and summarization
- **Code files** — Review, explanation, refactoring suggestions
- **Plain text / CSV / JSON** — Any text-based format

### Secure by Design
- All LLM inference happens on `127.0.0.1` — no data leaves your machine
- Telegram whitelist: only your user IDs can interact with the bot
- No inbound ports required (Long Polling only)
- API keys stored in `.env` and `mcp.json`, both gitignored by default

---

## Security

cl0w is built with a security-first mindset:

```
[Your Telegram App]
        ↕  HTTPS (Telegram servers only)
[cl0w Bot — your machine]
        ↕  127.0.0.1 only
[LM Studio — local inference]
```

| Threat | Mitigation |
|---|---|
| Unauthorized access | Telegram user ID whitelist (`ALLOWED_USER_IDS`) |
| Data exfiltration | LLM runs locally; no API calls to cloud providers |
| Credential leaks | `.env` and `mcp.json` are in `.gitignore` |
| Network exposure | Long Polling only — zero inbound ports opened |
| Prompt injection via files | File size capped at 20 MB; text truncated at 20,000 chars |

---

## Quick Start

### 1. Prerequisites

- Python 3.9+
- [LM Studio](https://lmstudio.ai) with a model loaded and the local server running
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot))

### 2. Install

```bash
git clone https://github.com/yourname/cl0w.git
cd cl0w
```

**macOS / Linux / Git Bash (Windows)**
```bash
chmod +x setup.sh start.sh
./setup.sh
```

**Windows (Command Prompt)**
```bat
setup.bat
```

The setup script:
- Creates a `.venv` virtual environment
- Installs all dependencies inside it
- Copies `.env.example` → `.env` and `mcp.json.example` → `mcp.json` if not present

### 3. Configure

Edit `.env`:
```dotenv
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
ALLOWED_USER_IDS=123456789
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LM_STUDIO_MODEL=local-model
```

Edit `mcp.json` to add MCP servers (or leave empty for chat-only mode).

### 4. Run

**macOS / Linux / Git Bash**
```bash
./start.sh
```

**Windows (Command Prompt)**
```bat
start.bat
```

Or manually with the venv activated:
```bash
source .venv/bin/activate   # macOS/Linux
.venv\Scripts\activate      # Windows
python bot.py
```

Open Telegram, find your bot, and send `/start`.

---

## Commands

### General
| Command | Description |
|---|---|
| `/start` | Reset everything (conversation + persona) |
| `/new` | Clear conversation history (keep current persona) |
| `/status` | Show current persona, LLM endpoint, MCP server states |
| `/help` | Full command reference |

### Persona
| Command | Description |
|---|---|
| `/persona` | Show active persona |
| `/persona list` | List all available personas |
| `/persona set <name>` | Switch persona (resets conversation) |
| `/persona reset` | Return to default persona |

### Skills
| Command | Description |
|---|---|
| `/skill` | List all available skills |
| `/translate <lang> <text>` | Translate text |
| `/summarize [text]` | Summarize text or last response |
| `/review <code>` | Code review |
| `/explain <topic>` | Explain code or concept |

### MCP
| Command | Description |
|---|---|
| `/mcp` | List MCP servers and their tools |
| `/mcp reload` | Reload `mcp.json` and restart servers |

---

## Use Cases

### Translate on the fly
```
You:  /translate Japanese Please review the attached document by Friday.
Bot:  金曜日までに添付の書類を確認してください。
```

### Code review from a file
Send your `.py` or `.js` file with the caption:
```
"Review this and point out any bugs or security issues."
```
cl0w reads the file, parses it as code, and returns a structured review with issues, suggestions, and verdict.

### Summarize a PDF meeting notes
Attach a PDF and ask:
```
"Extract the key decisions and action items from this."
```
cl0w extracts the full text from the PDF and returns a clean bullet-point summary.

### Web research with MCP
With `brave-search` MCP configured:
```
You:  What are the latest developments in quantum computing this week?
Bot:  [Searches the web automatically, synthesizes results]
```
No manual search needed — the agent decides when to call the tool.

### Switch persona mid-session
```
You:  /persona set coder
Bot:  Switched to Coder persona. Let's talk code!
You:  Refactor this function for readability: [code]
Bot:  [Expert code refactoring with explanation]
```

### Analyze an image
Send a screenshot or photo:
```
Caption: "What's wrong with this UI layout?"
```
cl0w analyzes the image and provides design feedback using the multimodal LLM.

### Build your own skill
Create `skills/standup.md`:
```markdown
---
name: standup
description: Generate a daily standup from bullet points
usage: /standup <bullets>
---

Turn the following bullet points into a professional daily standup update.
Format: Yesterday / Today / Blockers.

{{input}}
```
Then use it:
```
You:  /standup fixed login bug, working on dashboard, waiting for design review
Bot:  Yesterday: Fixed the login bug.
      Today: Working on the dashboard feature.
      Blockers: Awaiting design review feedback.
```

---

## Customization

### Add a Persona

Create `personas/mybot.md`:
```markdown
---
name: mybot
description: My custom assistant personality
---

You are a terse, no-nonsense assistant.
You respond in bullet points only.
You never use filler phrases.
```

Then: `/persona set mybot`

### Add an MCP Server

Edit `mcp.json`:
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/you/Documents"]
    }
  }
}
```

Then: `/mcp reload`

---

## Project Structure

```
cl0w/
├── bot.py               # Telegram bot — all handlers
├── config.py            # Configuration loader
├── llm.py               # LM Studio API client + tool call loop
├── mcp_client.py        # MCP stdio/SSE client
├── persona_manager.py   # Persona loader
├── skill_manager.py     # Skill loader + template renderer
├── file_handler.py      # File parsing (image/PDF/docx/text/code)
├── personas/            # Persona Markdown files
│   ├── default.md
│   ├── coder.md
│   └── analyst.md
├── skills/              # Skill Markdown files
│   ├── translate.md
│   ├── summarize.md
│   ├── review.md
│   └── explain.md
├── mcp.json             # Your MCP config (gitignored)
├── mcp.json.example     # MCP config template
├── .env                 # Your secrets (gitignored)
└── .env.example         # Secrets template
```

---

## Requirements

```
python-telegram-bot==21.1.1
openai==1.52.0
python-dotenv==1.0.1
httpx<0.28.0
pypdf>=4.0.0
python-docx>=1.1.0
```

---

## License

MIT
