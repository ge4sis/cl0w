#!/usr/bin/env python3
"""
cl0w — Lightweight Secure Agent Gateway
Deps (required): python-telegram-bot httpx pyyaml pypdf
Deps (optional): python-dotenv  — .env auto-load when running without Docker
                 mcp             — MCP server client (stdio / SSE transport)
"""
import asyncio, base64, importlib.util, io, json, logging, os, time
from collections import defaultdict
from pathlib import Path
from typing import AsyncGenerator

# .env 자동 로드 — Docker 없이 직접 실행 시 사용 (python-dotenv 선택 설치)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx, yaml
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)

# ── Config ────────────────────────────────────────────────────────────────────
CFG: dict = yaml.safe_load(open("config.yaml")) if Path("config.yaml").exists() else {}
_obs = CFG.get("observability", {})
logging.basicConfig(
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
    level=getattr(logging, _obs.get("log_level", "info").upper(), logging.INFO),
)
log = logging.getLogger("cl0w")

# ── Auth & Rate Limit ─────────────────────────────────────────────────────────
ALLOWED = {int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()}
_buckets: dict[int, list[float]] = defaultdict(list)

async def guard(u: Update) -> bool:
    uid = u.effective_user.id
    if ALLOWED and uid not in ALLOWED:
        return False
    limit = CFG.get("users", {}).get(uid, {}).get("rate_limit") or CFG.get("rate_limit", 20)
    now = time.time()
    _buckets[uid] = [t for t in _buckets[uid] if now - t < 60]
    if len(_buckets[uid]) >= limit:
        await u.message.reply_text("⚠️ 요청이 너무 많습니다. 잠시 후 시도해 주세요.")
        return False
    _buckets[uid].append(now)
    return True

# ── Session ───────────────────────────────────────────────────────────────────
_sc = CFG.get("session", {})
SESS_DIR = Path(_sc.get("dir", "./sessions"))
SESS_PERSIST = _sc.get("persist", True)
SESS_MAX = _sc.get("max_turns", 50) * 2  # turns → messages
if SESS_PERSIST:
    SESS_DIR.mkdir(exist_ok=True)
_mem: dict[int, list[dict]] = {}

def sess_get(uid: int) -> list[dict]:
    if uid not in _mem:
        p = SESS_DIR / f"{uid}.json"
        _mem[uid] = json.loads(p.read_text()) if SESS_PERSIST and p.exists() else []
    return list(_mem[uid])  # copy — caller may mutate freely

def sess_put(uid: int, h: list[dict]):
    _mem[uid] = h[-SESS_MAX:]
    if SESS_PERSIST:
        (SESS_DIR / f"{uid}.json").write_text(json.dumps(_mem[uid]))

def sess_clear(uid: int):
    _mem[uid] = []
    if SESS_PERSIST:
        p = SESS_DIR / f"{uid}.json"
        if p.exists():
            p.unlink()

# ── Persona ───────────────────────────────────────────────────────────────────
_pfile = "persona.md"
_pcache: dict[str, tuple[float, str]] = {}

def persona_load() -> str:
    p = Path(_pfile)
    if not p.exists():
        return ""
    mt = p.stat().st_mtime
    if _pfile in _pcache and _pcache[_pfile][0] == mt:
        return _pcache[_pfile][1]
    txt = p.read_text(encoding="utf-8")
    _pcache[_pfile] = (mt, txt)
    return txt

def persona_switch(name: str) -> bool:
    global _pfile
    for c in [f"personas/{name}.md", f"personas/{name}", name, f"{name}.md"]:
        if Path(c).exists():
            _pfile = c
            _pcache.clear()
            return True
    return False

# ── Tool Loader ───────────────────────────────────────────────────────────────
TOOLS_DIR = Path(CFG.get("tools_dir", "./tools"))
TOOLS_DIR.mkdir(exist_ok=True)
HOT_IV = CFG.get("hot_reload_interval", 5)
_tools: dict[str, dict] = {}
_last_scan = 0.0

def tools_scan():
    """Scan tools/ recursively (including subdirectories). Hot-reload on mtime change."""
    global _last_scan
    if time.time() - _last_scan < HOT_IV:
        return
    _last_scan = time.time()

    # rglob: scan all subdirectories, skip __init__.py and _ files
    files = {
        p for p in TOOLS_DIR.rglob("*.py")
        if not p.name.startswith("_")
    }

    # Unload removed files
    for n in [n for n, t in list(_tools.items()) if t["_p"] not in files]:
        del _tools[n]
        log.info(f"tool removed: {n}")

    # Load new / changed files
    for p in files:
        mt = p.stat().st_mtime
        if any(t["_p"] == p and t["_mt"] == mt for t in _tools.values()):
            continue
        try:
            # Use dotted relative path as module name to avoid name collisions
            # e.g. tools/search/ddg.py → module name "search.ddg"
            rel = p.relative_to(TOOLS_DIR)
            module_name = ".".join(rel.with_suffix("").parts)

            spec = importlib.util.spec_from_file_location(module_name, p)
            mod = importlib.util.module_from_spec(spec)

            # Add the tool's own directory to sys.path so it can import
            # sibling helper files (e.g. from utils import ...) without issues
            import sys
            parent_str = str(p.parent)
            path_added = parent_str not in sys.path
            if path_added:
                sys.path.insert(0, parent_str)
            try:
                spec.loader.exec_module(mod)
            finally:
                if path_added:
                    sys.path.remove(parent_str)

            if hasattr(mod, "TOOL_SCHEMA") and hasattr(mod, "run"):
                n = mod.TOOL_SCHEMA["name"]
                _tools[n] = {"s": mod.TOOL_SCHEMA, "fn": mod.run, "_p": p, "_mt": mt}
                log.info(f"tool loaded: {n} (from {rel})")
        except Exception as e:
            log.error(f"tool error {p}: {e}")

def tools_oai() -> list[dict]:
    """Return all tools (Python plugins + MCP servers) in OpenAI function format."""
    tools_scan()
    python = [
        {"type": "function", "function": {
            "name": t["s"]["name"],
            "description": t["s"].get("description", ""),
            "parameters": t["s"].get("input_schema", t["s"].get("parameters", {
                "type": "object", "properties": {}
            })),
        }}
        for t in _tools.values()
    ]
    return python + _mcp_oai()   # merge Python tools + MCP server tools

async def tool_run(name: str, args: dict) -> str:
    tools_scan()
    # ── MCP tool routing ──────────────────────────────────────────────────────
    if name in _mcp_tool_meta:
        return await _mcp_call(name, args)
    # ── Python file tool ──────────────────────────────────────────────────────
    if name not in _tools:
        return f"tool not found: {name}"
    try:
        r = _tools[name]["fn"](**args)
        return str(await r if asyncio.iscoroutine(r) else r)
    except Exception as e:
        return f"tool error: {e}"

# ── MCP Client ────────────────────────────────────────────────────────────────
# Optional — requires: pip install mcp
# Config: add `mcp_servers:` block to config.yaml (see example below)
#
# mcp_servers:
#   filesystem:                          # server nickname
#     transport: stdio
#     command: uvx
#     args: ["mcp-server-filesystem", "/tmp"]
#   my_api:
#     transport: sse
#     url: http://localhost:3000/sse

_mcp_sessions: dict[str, object] = {}         # name → ClientSession
_mcp_tool_meta: dict[str, dict] = {}          # "mcp_{srv}__{tool}" → {server, tool}
_mcp_tasks: dict[str, "asyncio.Task"] = {}   # name → background task
_mcp_cfg_mtime: float = 0.0                   # config.yaml last-seen mtime

def _mcp_oai() -> list[dict]:
    """Return OAI-format tool descriptors for all connected MCP servers."""
    return [
        {"type": "function", "function": {
            "name": key,
            "description": meta["description"],
            "parameters": meta["input_schema"],
        }}
        for key, meta in _mcp_tool_meta.items()
    ]

async def _mcp_discover(name: str, sess) -> None:
    result = await sess.list_tools()
    added = 0
    for t in result.tools:
        key = f"mcp_{name}__{t.name}"
        _mcp_tool_meta[key] = {
            "server": name,
            "tool": t.name,
            "description": f"[MCP:{name}] {t.description or ''}",
            "input_schema": (
                dict(t.inputSchema)
                if t.inputSchema
                else {"type": "object", "properties": {}}
            ),
        }
        added += 1
    log.info(f"MCP {name}: {added} tools discovered")

async def _mcp_call(key: str, args: dict) -> str:
    meta = _mcp_tool_meta[key]
    sess = _mcp_sessions.get(meta["server"])
    if not sess:
        return f"MCP server '{meta['server']}' not connected"
    try:
        result = await sess.call_tool(meta["tool"], args)
        parts = [c.text for c in result.content if hasattr(c, "text")]
        return "\n".join(parts) if parts else str(result.content)
    except Exception as e:
        return f"MCP call error: {e}"

async def _mcp_session_task(name: str, cfg: dict) -> None:
    """Long-running task: connect → discover tools → keep alive → auto-reconnect."""
    try:
        from mcp import ClientSession, StdioServerParameters
    except ImportError:
        log.error("MCP support requires: pip install mcp")
        return

    while True:
        try:
            if cfg.get("transport") == "stdio":
                from mcp.client.stdio import stdio_client
                params = StdioServerParameters(
                    command=cfg["command"],
                    args=cfg.get("args", []),
                    env=cfg.get("env"),
                )
                async with stdio_client(params) as (r, w):
                    async with ClientSession(r, w) as sess:
                        await sess.initialize()
                        _mcp_sessions[name] = sess
                        await _mcp_discover(name, sess)
                        await asyncio.sleep(float("inf"))   # keep alive

            elif cfg.get("transport") == "sse":
                from mcp.client.sse import sse_client
                async with sse_client(cfg["url"]) as (r, w):
                    async with ClientSession(r, w) as sess:
                        await sess.initialize()
                        _mcp_sessions[name] = sess
                        await _mcp_discover(name, sess)
                        await asyncio.sleep(float("inf"))   # keep alive

            else:
                log.error(f"MCP {name}: unknown transport '{cfg.get('transport')}'")
                return

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning(f"MCP {name} disconnected: {e} — retry in 10s")
            _mcp_sessions.pop(name, None)
            # Remove stale tools for this server
            stale = [k for k, v in _mcp_tool_meta.items() if v["server"] == name]
            for k in stale:
                del _mcp_tool_meta[k]
            await asyncio.sleep(10)

def _mcp_server_start(name: str, cfg: dict) -> None:
    """Start a background task for one MCP server and register it."""
    task = asyncio.create_task(_mcp_session_task(name, cfg))
    _mcp_tasks[name] = task
    log.info(f"MCP server connecting: {name} ({cfg.get('transport')})")

def _mcp_server_stop(name: str) -> None:
    """Cancel a running MCP server task and purge its tools."""
    task = _mcp_tasks.pop(name, None)
    if task:
        task.cancel()
    stale = [k for k, v in _mcp_tool_meta.items() if v["server"] == name]
    for k in stale:
        del _mcp_tool_meta[k]
    _mcp_sessions.pop(name, None)
    log.info(f"MCP server removed: {name}")

async def _mcp_config_watcher() -> None:
    """Watch config.yaml for mcp_servers changes every 10 s.
    Starts tasks for newly added servers, cancels tasks for removed ones.
    No bot restart required."""
    global _mcp_cfg_mtime
    cfg_path = Path("config.yaml")
    while True:
        await asyncio.sleep(10)
        try:
            mt = cfg_path.stat().st_mtime if cfg_path.exists() else 0.0
            if mt == _mcp_cfg_mtime:
                continue
            _mcp_cfg_mtime = mt
            new_cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
            new_servers: dict = new_cfg.get("mcp_servers", {})
            current = set(_mcp_tasks.keys())
            desired = set(new_servers.keys())

            for name in desired - current:          # added
                _mcp_server_start(name, new_servers[name])
            for name in current - desired:          # removed
                _mcp_server_stop(name)
        except Exception as e:
            log.error(f"MCP config watcher: {e}")

async def _mcp_init(app) -> None:
    """PTB post_init hook — start MCP server tasks + config watcher."""
    global _mcp_cfg_mtime
    cfg_path = Path("config.yaml")
    _mcp_cfg_mtime = cfg_path.stat().st_mtime if cfg_path.exists() else 0.0

    for name, cfg in CFG.get("mcp_servers", {}).items():
        _mcp_server_start(name, cfg)

    # Config watcher: picks up mcp_servers changes without restart
    asyncio.create_task(_mcp_config_watcher())

# ── LLM Router ────────────────────────────────────────────────────────────────
_uprov: dict[int, str] = {}
_EXTRA_HEADERS = {"claude": {"anthropic-version": "2023-06-01"}}
_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

def prov_for(uid: int) -> tuple[str, dict]:
    name = (
        _uprov.get(uid)
        or CFG.get("users", {}).get(uid, {}).get("default_provider")
        or CFG.get("default_provider", "openai")
    )
    return name, CFG.get("providers", {}).get(name, {})

async def llm_stream(uid: int, history: list[dict]) -> AsyncGenerator[dict, None]:
    """Yields OpenAI-style choice objects from the streaming response."""
    tools = tools_oai()
    persona = persona_load()
    tool_names = [t["function"]["name"] for t in tools]
    sys_content = (
        persona + (f"\n---\nAvailable tools: {tool_names}" if tool_names else "")
    ).strip()
    msgs = ([{"role": "system", "content": sys_content}] if sys_content else []) + history

    pname0, _ = prov_for(uid)
    chain = [pname0] + [p for p in CFG.get("fallback_chain", []) if p != pname0]

    for pname in chain:
        pc = CFG.get("providers", {}).get(pname, {})
        if not pc.get("base_url"):
            continue
        key = os.environ.get(_ENV_KEYS.get(pname, ""), "")
        headers = {
            "Content-Type": "application/json",
            **( {"Authorization": f"Bearer {key}"} if key else {}),
            **_EXTRA_HEADERS.get(pname, {}),
        }
        payload: dict = {"model": pc.get("model", "gpt-4o"), "messages": msgs, "stream": True}
        if tools:
            payload.update({"tools": tools, "tool_choice": "auto"})
        try:
            async with httpx.AsyncClient(timeout=90) as c:
                async with c.stream(
                    "POST", f"{pc['base_url']}/chat/completions",
                    headers=headers, json=payload
                ) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        d = line[5:].strip()
                        if d == "[DONE]":
                            return
                        try:
                            yield json.loads(d)["choices"][0]
                        except Exception:
                            continue
            return
        except Exception as e:
            log.warning(f"provider {pname}: {e}")

    raise RuntimeError("모든 프로바이더가 응답하지 않습니다")

# ── Streaming Reply ───────────────────────────────────────────────────────────
async def stream_reply(u: Update, uid: int, history: list[dict]) -> str:
    """Stream LLM reply to Telegram. Mutates history. Returns final text."""
    sent = await u.message.reply_text("💭 …")
    text, last_edit, tc_acc = "", 0.0, {}

    try:
        async for ch in llm_stream(uid, history):
            delta = ch.get("delta", {})

            # Accumulate tool call fragments
            for tc in delta.get("tool_calls", []):
                i = tc.get("index", 0)
                tc_acc.setdefault(i, {"id": "", "name": "", "args": ""})
                tc_acc[i]["id"] = tc.get("id") or tc_acc[i]["id"]
                tc_acc[i]["name"] += tc.get("function", {}).get("name") or ""
                tc_acc[i]["args"] += tc.get("function", {}).get("arguments") or ""

            # Stream text with 1-second throttle (Telegram edit limit)
            if chunk := delta.get("content") or "":
                text += chunk
                if time.time() - last_edit >= 1.0:
                    try:
                        await sent.edit_text(text[-4000:] or "…")
                        last_edit = time.time()
                    except Exception:
                        pass

            if ch.get("finish_reason") in ("stop", "tool_calls", "end_turn"):
                break

        # Final flush
        if text:
            try:
                await sent.edit_text(text[-4000:])
            except Exception:
                pass

        # Execute tool calls → recurse for final answer
        if tc_acc:
            history.append({
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {"id": t["id"], "type": "function",
                     "function": {"name": t["name"], "arguments": t["args"]}}
                    for t in tc_acc.values()
                ],
            })
            for tc in tc_acc.values():
                try:
                    await sent.edit_text(
                        f"🔧 `{tc['name']}`\n```json\n{tc['args'][:300]}\n```",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    pass
                args = json.loads(tc["args"]) if tc["args"] else {}
                result = await tool_run(tc["name"], args)
                history.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            return await stream_reply(u, uid, history)

        history.append({"role": "assistant", "content": text})

    except RuntimeError as e:
        await sent.edit_text(f"❌ {e}")
    except Exception as e:
        log.error(f"stream error: {e}")
        await sent.edit_text("❌ 처리 중 오류가 발생했습니다.")

    return text

# ── File Processing ───────────────────────────────────────────────────────────
_fc = CFG.get("file", {})
MAX_MB   = _fc.get("max_size_mb", 20)
MAX_CH   = _fc.get("max_text_chars", 50_000)
PDF_PG   = _fc.get("pdf_max_pages", 100)
PDF_ON   = _fc.get("pdf_support", True)
IMG_EXT  = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
TXT_EXT  = {".txt", ".md", ".csv", ".json", ".py", ".yaml", ".yml",
            ".js", ".ts", ".html", ".xml", ".sh", ".toml", ".env"}

def file_block(data: bytes, name: str, mime: str = "") -> dict:
    """Convert raw bytes to an LLM content block. Raises ValueError on failure."""
    suf = Path(name).suffix.lower()
    if len(data) > MAX_MB * 1024 * 1024:
        raise ValueError(f"파일이 너무 큽니다 (최대 {MAX_MB}MB)")

    if suf in IMG_EXT or mime.startswith("image/"):
        b64 = base64.b64encode(data).decode()
        mt = mime or f"image/{suf.lstrip('.') or 'jpeg'}"
        return {"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}}

    if suf in TXT_EXT:
        txt = data.decode("utf-8", errors="replace")
        tail = "\n[잘림]" if len(txt) > MAX_CH else ""
        return {"type": "text", "text": f"```{suf.lstrip('.')}\n{txt[:MAX_CH]}\n```{tail}"}

    if suf == ".pdf" and PDF_ON:
        try:
            from pypdf import PdfReader
            pages = PdfReader(io.BytesIO(data)).pages[:PDF_PG]
            txt = "\n".join(p.extract_text() or "" for p in pages).strip()
            if not txt:
                raise ValueError("이미지 전용 PDF — 텍스트 추출 불가")
            tail = "\n[잘림]" if len(txt) > MAX_CH else ""
            return {"type": "text", "text": f"[PDF: {name}]\n{txt[:MAX_CH]}{tail}"}
        except ImportError:
            raise ValueError("pypdf 미설치 (pip install pypdf)")

    raise ValueError(f"지원하지 않는 형식 ({suf or mime}). Tool을 추가하면 처리 가능합니다.")

# ── Telegram Handlers ─────────────────────────────────────────────────────────
async def on_start(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    await u.message.reply_text(
        "안녕하세요! *cl0w* 에이전트입니다.\n"
        "/status — 현재 상태\n/provider — LLM 전환\n/tools — Tool 목록\n"
        "/persona — Persona 확인\n/reset — 세션 초기화",
        parse_mode=ParseMode.MARKDOWN,
    )

async def on_status(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    pn, pc = prov_for(u.effective_user.id)
    await u.message.reply_text(
        f"*프로바이더*: {pn} (`{pc.get('model', '?')}`)\n"
        f"*Persona*: `{Path(_pfile).stem}`\n"
        f"*Tools*: {len(tools_oai())}개 로드됨",
        parse_mode=ParseMode.MARKDOWN,
    )

async def on_provider(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    uid = u.effective_user.id
    if not ctx.args:
        names = ", ".join(CFG.get("providers", {}).keys())
        await u.message.reply_text(
            f"사용법: `/provider <이름>`\n사용 가능: {names}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    name = ctx.args[0].lower()
    if name not in CFG.get("providers", {}):
        await u.message.reply_text(f"❌ 알 수 없는 프로바이더: {name}")
        return
    _uprov[uid] = name
    await u.message.reply_text(f"✅ *{name}* 으로 전환했습니다.", parse_mode=ParseMode.MARKDOWN)

async def on_tools(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    t = tools_oai()
    lines = [f"• `{x['function']['name']}` — {x['function'].get('description', '')}" for x in t]
    await u.message.reply_text(
        "\n".join(lines) if lines else "등록된 Tool 없음.",
        parse_mode=ParseMode.MARKDOWN,
    )

async def on_reset(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    sess_clear(u.effective_user.id)
    await u.message.reply_text("✅ 세션 초기화 완료.")

async def on_persona(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    if ctx.args and ctx.args[0] == "switch" and len(ctx.args) > 1:
        ok = persona_switch(ctx.args[1])
        await u.message.reply_text(
            f"✅ Persona → `{ctx.args[1]}`" if ok else f"❌ 파일 없음: {ctx.args[1]}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    txt = persona_load()
    await u.message.reply_text(
        f"```\n{txt[:3800]}\n```" if txt else "Persona 미설정",
        parse_mode=ParseMode.MARKDOWN,
    )

async def on_msg(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    uid, msg = u.effective_user.id, u.message
    blocks: list[dict] = []

    # ── File / Photo ──────────────────────────────────────────────────────────
    file_ref, fname, mime = None, "file", ""
    if msg.photo:
        file_ref = await msg.photo[-1].get_file()
        fname, mime = "photo.jpg", "image/jpeg"
    elif msg.document:
        d = msg.document
        if d.file_size and d.file_size > MAX_MB * 1024 * 1024:
            await msg.reply_text(f"❌ 파일이 너무 큽니다 (최대 {MAX_MB}MB)")
            return
        file_ref = await d.get_file()
        fname, mime = d.file_name or "document", d.mime_type or ""

    if file_ref:
        raw = bytes(await file_ref.download_as_bytearray())
        try:
            blocks.append(file_block(raw, fname, mime))
        except ValueError as e:
            await msg.reply_text(f"❌ {e}")
            return

    # ── Text ──────────────────────────────────────────────────────────────────
    text = (msg.text or msg.caption or "").strip()
    max_in = CFG.get("max_input_chars", 4096)
    if len(text) > max_in:
        await msg.reply_text(f"❌ 메시지가 너무 깁니다 (최대 {max_in}자)")
        return
    if text:
        blocks.append({"type": "text", "text": text})

    if not blocks:
        await msg.reply_text("❌ 처리할 내용이 없습니다.")
        return

    # Single plain text → compact format; otherwise multi-block
    user_msg = (
        {"role": "user", "content": text}
        if len(blocks) == 1 and blocks[0]["type"] == "text"
        else {"role": "user", "content": blocks}
    )

    history = sess_get(uid) + [user_msg]
    await stream_reply(u, uid, history)
    sess_put(uid, history)  # history mutated by stream_reply to include assistant reply

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("❌ TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다.")

    app = Application.builder().token(token).post_init(_mcp_init).build()

    for cmd, fn in [
        ("start",    on_start),
        ("status",   on_status),
        ("provider", on_provider),
        ("tools",    on_tools),
        ("reset",    on_reset),
        ("persona",  on_persona),
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    app.add_handler(
        MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, on_msg)
    )

    tg = CFG.get("telegram", {})
    if tg.get("mode") == "webhook":
        app.run_webhook(
            listen="0.0.0.0", port=8443,
            webhook_url=tg.get("webhook_url", ""),
        )
    else:
        log.info("cl0w ready (polling mode)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
