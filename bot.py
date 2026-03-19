import asyncio, base64, importlib.util, io, json, logging, os, sys, time, httpx, yaml
from collections import defaultdict
from pathlib import Path
from typing import AsyncGenerator
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError: pass

# ── Shared HTTP client (connection reuse across LLM requests) ─────────────────
_http: httpx.AsyncClient | None = None

def http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=90)
    return _http
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
)

# ── Config ────────────────────────────────────────────────────────────────────
def _deep_merge(b: dict, o: dict) -> dict:
    out = dict(b)
    for k, v in o.items():
        out[k] = _deep_merge(out[k], v) if k in out and isinstance(out[k], dict) and isinstance(v, dict) else v
    return out

CFG: dict = yaml.safe_load(open("config.yaml", encoding="utf-8")) if Path("config.yaml").exists() else {}
# config.local.yaml — git 제외, API key 등 민감 정보 포함 가능
if Path("config.local.yaml").exists():
    _local = yaml.safe_load(open("config.local.yaml", encoding="utf-8")) or {}
    CFG = _deep_merge(CFG, _local)
_obs = CFG.get("observability", {})
logging.basicConfig(
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
    level=getattr(logging, _obs.get("log_level", "info").upper(), logging.INFO),
)
log = logging.getLogger("cl0w")
_fc = CFG.get("file", {})
MAX_MB, MAX_CH, PDF_PG, PDF_ON = _fc.get("max_size_mb", 20), _fc.get("max_text_chars", 50000), _fc.get("pdf_max_pages", 100), _fc.get("pdf_support", True)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
TXT_EXT = {".txt", ".md", ".py", ".js", ".html", ".css", ".json", ".yaml", ".yml", ".c", ".cpp", ".h"}

# ── Auth & Rate Limit ─────────────────────────────────────────────────────────
ALLOWED = {int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()}
_buckets: dict[int, list[float]] = defaultdict(list)
async def guard(u: Update) -> bool:
    uid = u.effective_user.id
    if ALLOWED and uid not in ALLOWED: return False
    limit, now = CFG.get("users", {}).get(uid, {}).get("rate_limit") or CFG.get("rate_limit", 20), time.time()
    _buckets[uid] = [t for t in _buckets[uid] if now - t < 60]
    if len(_buckets[uid]) >= limit:
        if u.message: await u.message.reply_text("⚠️ 요청이 너무 많습니다. 잠시 후 시도해 주세요.")
        return False
    _buckets[uid].append(now); return True

_sc = CFG.get("session", {})
SESS_DIR, SESS_PERSIST, SESS_MAX = Path(_sc.get("dir", "./sessions")), _sc.get("persist", True), _sc.get("max_turns", 50) * 2
if SESS_PERSIST: SESS_DIR.mkdir(exist_ok=True)
_mem: dict[int, list[dict]] = {}
_waiting_tools: dict[int, dict] = {}

def sess_get(uid: int) -> list[dict]:
    if uid not in _mem:
        p = SESS_DIR / f"{uid}.json"
        _mem[uid] = json.loads(p.read_text()) if SESS_PERSIST and p.exists() else []
    return list(_mem[uid])
def sess_put(uid: int, h: list[dict]):
    _mem[uid] = h[-SESS_MAX:]
    if SESS_PERSIST: (SESS_DIR / f"{uid}.json").write_text(json.dumps(_mem[uid]))
def sess_clear(uid: int):
    _mem[uid] = []
    if SESS_PERSIST: (SESS_DIR / f"{uid}.json").unlink(missing_ok=True)

# ── Persona ───────────────────────────────────────────────────────────────────
_DEFAULT_PERSONA = "personas/default.md"
_pfile, _pcache = _DEFAULT_PERSONA, {}
def persona_load() -> str:
    p = Path(_pfile)
    if not p.exists(): return ""
    mt = p.stat().st_mtime
    if _pfile in _pcache and _pcache[_pfile][0] == mt: return _pcache[_pfile][1]
    txt = p.read_text(encoding="utf-8")
    _pcache[_pfile] = (mt, txt); return txt
def persona_switch(name: str) -> bool:
    global _pfile
    for c in [f"personas/{name}.md", f"personas/{name}", name, f"{name}.md"]:
        if Path(c).exists():
            _pfile = c; _pcache.clear(); return True
    return False

# ── Tool Loader ───────────────────────────────────────────────────────────────
TOOLS_DIR = Path(CFG.get("tools_dir", "./tools"))
TOOLS_DIR.mkdir(exist_ok=True)
HOT_IV, _tools, _tool_mtimes, _last_scan = CFG.get("hot_reload_interval", 5), {}, {}, 0.0
def tools_scan():
    global _last_scan
    if time.time() - _last_scan < HOT_IV: return
    _last_scan = time.time()
    files = {p for p in Path(CFG.get("tools_dir", "./tools")).rglob("*.py") if not p.name.startswith("_")}
    for n in [n for n, t in list(_tools.items()) if t["_p"] not in files]:
        _tool_mtimes.pop(_tools[n]["_p"], None); del _tools[n]; log.info(f"tool removed: {n}")
    for p in files:
        mt = p.stat().st_mtime
        if _tool_mtimes.get(p) == mt: continue
        try:
            rel = p.relative_to(Path(CFG.get("tools_dir", "./tools")))
            mod_name = ".".join(rel.with_suffix("").parts)
            spec = importlib.util.spec_from_file_location(mod_name, p)
            mod = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(p.parent))
            try: spec.loader.exec_module(mod)
            finally: sys.path.remove(str(p.parent))
            if hasattr(mod, "TOOL_SCHEMA") and hasattr(mod, "run"):
                n = mod.TOOL_SCHEMA["name"]
                _tools[n] = {"s": mod.TOOL_SCHEMA, "fn": mod.run, "_p": p}; _tool_mtimes[p] = mt
                log.info(f"tool loaded: {n}")
        except Exception as e: log.error(f"tool error {p}: {e}")

def tools_oai() -> list[dict]:
    tools_scan()
    return [{"type": "function", "function": {"name": t["s"]["name"], "description": t["s"].get("description",""),
             "parameters": t["s"].get("input_schema", t["s"].get("parameters", {"type":"object","properties":{}}))}}
            for t in _tools.values()] + _mcp_oai()

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

def tool_is_dangerous(name: str, args: dict) -> bool:
    n = name.lower()
    if any(k in n for k in {"write","delete","rm","mv","bash","shell","execute","run"}): return True
    return ("bash" in n or "filesystem" in n) and any(k in str(args).lower() for k in {"write","delete","remove","move"})

# ── MCP Client ────────────────────────────────────────────────────────────────
_mcp_sessions, _mcp_tool_meta, _mcp_tasks, _mcp_cfg_mtime = {}, {}, {}, 0.0
def _mcp_oai() -> list[dict]:
    return [{"type": "function", "function": {"name": k, "description": v["description"], "parameters": v["input_schema"]}}
            for k, v in _mcp_tool_meta.items()]
async def _mcp_discover(name: str, sess) -> None:
    res = await sess.list_tools()
    for t in res.tools:
        _mcp_tool_meta[f"mcp_{name}__{t.name}"] = {"server": name, "tool": t.name, "description": f"[MCP:{name}] {t.description or ''}",
                                                 "input_schema": dict(t.inputSchema) if t.inputSchema else {"type": "object", "properties": {}}}
    log.info(f"MCP {name}: {len(res.tools)} tools")
async def _mcp_call(key: str, args: dict) -> str:
    meta = _mcp_tool_meta[key]
    if not (sess := _mcp_sessions.get(meta["server"])): return f"MCP '{meta['server']}' not connected"
    try:
        res = await sess.call_tool(meta["tool"], args)
        parts = [c.text for c in res.content if hasattr(c, "text")]
        return "\n".join(parts) if parts else str(res.content)
    except Exception as e: return f"MCP call error: {e}"
async def _mcp_connect(name: str, r, w) -> None:
    from mcp import ClientSession
    async with ClientSession(r, w) as sess:
        await sess.initialize(); _mcp_sessions[name] = sess
        await _mcp_discover(name, sess); await asyncio.sleep(float("inf"))

async def _mcp_session_task(name: str, cfg: dict) -> None:
    while True:
        try:
            if cfg.get("transport") == "stdio":
                from mcp.client.stdio import stdio_client, StdioServerParameters
                async with stdio_client(StdioServerParameters(command=cfg["command"], args=cfg.get("args", []), env=cfg.get("env"))) as (r, w):
                    await _mcp_connect(name, r, w)
            elif cfg.get("transport") == "sse":
                from mcp.client.sse import sse_client
                async with sse_client(cfg["url"]) as (r, w): await _mcp_connect(name, r, w)
            else: return
        except asyncio.CancelledError: break
        except Exception as e:
            log.warning(f"MCP {name} error: {e}")
            await asyncio.sleep(10)
        finally:
            _mcp_sessions.pop(name, None)
            for k in [k for k, v in _mcp_tool_meta.items() if v["server"] == name]: del _mcp_tool_meta[k]

def _mcp_server_start(n: str, c: dict): _mcp_tasks[n] = asyncio.create_task(_mcp_session_task(n, c))
def _mcp_server_stop(n: str):
    if (t := _mcp_tasks.pop(n, None)): t.cancel()
    for k in [k for k, v in _mcp_tool_meta.items() if v["server"] == n]: del _mcp_tool_meta[k]
    _mcp_sessions.pop(n, None)
async def _mcp_config_watcher():
    global _mcp_cfg_mtime
    while True:
        await asyncio.sleep(10)
        try:
            mt = max(Path("config.yaml").stat().st_mtime if Path("config.yaml").exists() else 0,
                     Path("config.local.yaml").stat().st_mtime if Path("config.local.yaml").exists() else 0)
            if mt == _mcp_cfg_mtime: continue
            _mcp_cfg_mtime = mt
            new_cfg = _deep_merge(yaml.safe_load(open("config.yaml")) if Path("config.yaml").exists() else {},
                                 yaml.safe_load(open("config.local.yaml")) if Path("config.local.yaml").exists() else {})
            new_srv = new_cfg.get("mcp_servers", {})
            cur, des = set(_mcp_tasks.keys()), set(new_srv.keys())
            for n in des - cur: _mcp_server_start(n, new_srv[n])
            for n in cur - des: _mcp_server_stop(n)
        except Exception as e: log.error(f"MCP watcher: {e}")
async def _mcp_init(app):
    global _mcp_cfg_mtime
    _mcp_cfg_mtime = max(Path("config.yaml").stat().st_mtime if Path("config.yaml").exists() else 0,
                         Path("config.local.yaml").stat().st_mtime if Path("config.local.yaml").exists() else 0)
    for n, c in CFG.get("mcp_servers", {}).items(): _mcp_server_start(n, c)
    asyncio.create_task(_mcp_config_watcher())

# ── LLM Router ────────────────────────────────────────────────────────────────
_uprov, _EXTRA_H, _ENV_KEYS = {}, {"claude": {"anthropic-version": "2023-06-01"}}, {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}
def prov_for(uid: int) -> tuple[str, dict]:
    n = _uprov.get(uid) or CFG.get("users",{}).get(uid,{}).get("default_provider") or CFG.get("default_provider","gemini")
    return n, CFG.get("providers", {}).get(n, {})

async def llm_stream(uid: int, history: list[dict]) -> AsyncGenerator[dict, None]:
    tools, persona = tools_oai(), persona_load()
    t_names = [t["function"]["name"] for t in tools]
    sys_c = (persona + (f"\n---\nAvailable tools: {t_names}" if t_names else "")).strip()
    msgs = ([{"role": "system", "content": sys_c}] if sys_c else []) + history
    p_name0, _ = prov_for(uid)
    for pname in [p_name0] + [p for p in CFG.get("fallback_chain", []) if p != p_name0]:
        pc = CFG.get("providers", {}).get(pname, {})
        if not pc.get("base_url"): continue
        key = os.environ.get(_ENV_KEYS.get(pname, ""), "")
        headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {}), **_EXTRA_H.get(pname, {})}
        payload = {"model": pc.get("model", "gpt-4o"), "messages": msgs, "stream": True, **({"tools": tools, "tool_choice": "auto"} if tools else {})}
        try:
            async with http().stream("POST", f"{pc['base_url']}/chat/completions", headers=headers, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if line.startswith("data:"):
                        if (d := line[5:].strip()) == "[DONE]": return
                        yield json.loads(d)["choices"][0]
            return
        except Exception as e: log.warning(f"provider {pname}: {e}")
    raise RuntimeError("모든 프로바이더 응답 실패")

# ── Streaming Reply ───────────────────────────────────────────────────────────
_CHUNK = 4000  # Telegram max message length (hard limit 4096, use 4000 for safety)

async def stream_reply(u: Update, uid: int, history: list[dict], level: int = 0) -> str:
    if level > 10:
        await u.message.reply_text("⚠️ 도구 호출 루프가 너무 깁니다. 중단합니다.")
        return ""
    sent = await u.message.reply_text("💭 …")
    text, window, last_edit, tc_acc = "", "", 0.0, {}
    async def _f(final=False):
        nonlocal last_edit
        if final or time.time() - last_edit >= 1.0:
            try: await sent.edit_text(window or "…"); last_edit = time.time()
            except: pass
    try:
        async for ch in llm_stream(uid, history):
            delta = ch.get("delta", {})
            for tc in delta.get("tool_calls", []):
                i = tc.get("index", 0); tc_acc.setdefault(i, {"id": "", "name": "", "args": ""})
                tc_acc[i]["id"] = tc.get("id") or tc_acc[i]["id"]
                tc_acc[i]["name"] += tc.get("function", {}).get("name") or ""
                tc_acc[i]["args"] += tc.get("function", {}).get("arguments") or ""
            if chunk := delta.get("content") or "":
                text += chunk; window += chunk
                while len(window) > 4000:
                    ov = window[4000:]; await _f(True); sent = await u.message.reply_text("💭 …")
                    window, last_edit = ov, 0.0
                await _f()
            if ch.get("finish_reason") in ("stop", "tool_calls", "end_turn"): break
        await _f(True)
        if tc_acc:
            for tc in tc_acc.values():
                args = json.loads(tc["args"]) if tc["args"] else {}
                if tool_is_dangerous(tc["name"], args):
                    _waiting_tools[uid] = {"u": u, "history": history, "tc_acc": tc_acc, "level": level}
                    kb = [[InlineKeyboardButton("✅ 승인", callback_data=f"tool_ok_{uid}"), InlineKeyboardButton("❌ 거절", callback_data=f"tool_no_{uid}")]]
                    await u.message.reply_text(f"⚠️ **위험 도구 감지**: `{tc['name']}`\n```json\n{tc['args']}\n```", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
                    return text
            history.append({"role": "assistant", "content": text or None, "tool_calls": [{"id": t["id"], "type": "function", "function": {"name": t["name"], "arguments": t["args"]}} for t in tc_acc.values()]})
            for tc in tc_acc.values():
                try: await sent.edit_text(f"🔧 `{tc['name']}`\n```json\n{tc['args'][:300]}\n```", parse_mode=ParseMode.MARKDOWN)
                except: pass
                res = await tool_run(tc["name"], json.loads(tc["args"]) if tc["args"] else {})
                history.append({"role": "tool", "tool_call_id": tc["id"], "content": res})
            return await stream_reply(u, uid, history, level + 1)
        history.append({"role": "assistant", "content": text})
    except Exception as e: log.error(f"stream error: {e}"); await sent.edit_text(f"❌ {e}")
    return text

async def on_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); d = q.data
    if not (d.startswith("tool_ok_") or d.startswith("tool_no_")): return
    uid = int(d.split("_")[-1])
    if uid not in _waiting_tools: return await q.edit_message_text("❌ 대기 중인 세션 없음")
    s = _waiting_tools.pop(uid); ou, h, ta = s["u"], s["history"], s["tc_acc"]
    h.append({"role": "assistant", "content": None, "tool_calls": [{"id": t["id"], "type": "function", "function": {"name": t["name"], "arguments": t["args"]}} for t in ta.values()]})
    if d.startswith("tool_no_"):
        await q.edit_message_text("🚫 도구 실행 거절됨")
        for t in ta.values(): h.append({"role": "tool", "tool_call_id": t["id"], "content": "user rejected for security."})
    else:
        await q.edit_message_text("✅ 실행 승인됨")
        for t in ta.values():
            res = await tool_run(t["name"], json.loads(t["args"]) if t["args"] else {})
            h.append({"role": "tool", "tool_call_id": t["id"], "content": res})
    await stream_reply(ou, uid, h, s.get("level", 0) + 1); sess_put(uid, h)

# ── File Processing ───────────────────────────────────────────────────────────

def file_block(data, name, mime=""):
    suf = Path(name).suffix.lower()
    if len(data) > MAX_MB * 1024 * 1024: raise ValueError(f"파일 과다 ({MAX_MB}MB)")
    if suf in IMG_EXT or mime.startswith("image/"):
        mt = mime or f"image/{suf[1:] or 'jpeg'}"
        return {"type": "image_url", "image_url": {"url": f"data:{mt};base64,{base64.b64encode(data).decode()}"}}
    if suf in TXT_EXT:
        t = data.decode("utf-8", errors="replace")
        return {"type": "text", "text": f"```{suf[1:]}\n{t[:MAX_CH]}\n```" + ("\n[잘림]" if len(t) > MAX_CH else "")}
    if suf == ".pdf" and PDF_ON:
        from pypdf import PdfReader
        t = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages[:PDF_PG]).strip()
        if not t: raise ValueError("PDF 텍스트 추출 불가")
        return {"type": "text", "text": f"[PDF: {name}]\n{t[:MAX_CH]}" + ("\n[잘림]" if len(t) > MAX_CH else "")}
    raise ValueError(f"지원 지양: {suf}")

# ── Telegram Handlers ─────────────────────────────────────────────────────────
H_TXT = "*cl0w* 안내: /status, /provider, /tools, /persona [switch 이름], /reset, /help"
async def on_start(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if await guard(u): await u.message.reply_text("안녕하세요! *cl0w* 입니다.\n\n" + H_TXT, parse_mode=ParseMode.MARKDOWN)
async def on_status(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    pn, pc = prov_for(u.effective_user.id)
    await u.message.reply_text(f"*프로바이더*: {pn} (`{pc.get('model','?')}`)\n*Persona*: `{Path(_pfile).stem}`\n*Tools*: {len(_tools)+len(_mcp_tool_meta)}개", parse_mode=ParseMode.MARKDOWN)
async def on_provider(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    cur, _ = prov_for(u.effective_user.id)
    if not ctx.args:
        avail = [f"• {p} {'(현재)' if p == cur else ''}" for p in CFG.get("providers", {}).keys()]
        return await u.message.reply_text("🌐 *LLM 프로바이더 목록*:\n\n" + "\n".join(avail), parse_mode=ParseMode.MARKDOWN)
    n = ctx.args[0].lower()
    if n in CFG.get("providers", {}):
        _uprov[u.effective_user.id] = n; await u.message.reply_text(f"✅ 프로바이더 전환: `{cur}` → `{n}`", parse_mode=ParseMode.MARKDOWN)
    else: await u.message.reply_text(f"❌ '{n}'은(는) 유효한 프로바이더가 아닙니다.")
async def on_tools(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    ls = [f"• `{x['function']['name']}` — {x['function'].get('description','')}" for x in tools_oai()]
    await u.message.reply_text("\n".join(ls) or "Tool 없음", parse_mode=ParseMode.MARKDOWN)
async def on_reset(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if await guard(u): sess_clear(u.effective_user.id); await u.message.reply_text("✅ 세션 초기화 완료")
async def on_persona(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    if ctx.args:
        global _pfile
        if ctx.args[0] == "reset":
            _pfile = _DEFAULT_PERSONA; _pcache.clear(); await u.message.reply_text("✅ Persona 초기화 완료 (default.md)")
            return
        name = ctx.args[1] if ctx.args[0] == "switch" and len(ctx.args) > 1 else ctx.args[0]
        ok = persona_switch(name); await u.message.reply_text(f"✅ Persona `{name}`" if ok else "❌ 파일 없음")
    else: await u.message.reply_text(f"```\n{persona_load()[:3800]}\n```", parse_mode=ParseMode.MARKDOWN)
async def on_msg(u: Update, _: ContextTypes.DEFAULT_TYPE):
    if not await guard(u): return
    uid, msg, blocks = u.effective_user.id, u.message, []
    fr, fn, mi = None, "f", ""
    if msg.photo: fr, fn, mi = await msg.photo[-1].get_file(), "p.jpg", "image/jpeg"
    elif msg.document: fr, fn, mi = await msg.document.get_file(), msg.document.file_name or "d", msg.document.mime_type or ""
    if fr:
        try: blocks.append(file_block(bytes(await fr.download_as_bytearray()), fn, mi))
        except ValueError as e: return await msg.reply_text(f"❌ {e}")
    t = (msg.text or msg.caption or "").strip()
    if t:
        if len(t) > CFG.get("max_input_chars", 4000): return await msg.reply_text("❌ 과다")
        blocks.append({"type": "text", "text": t})
    if not blocks: return
    um = {"role": "user", "content": t} if len(blocks) == 1 and blocks[0]["type"] == "text" else {"role": "user", "content": blocks}
    h = sess_get(uid) + [um]; await stream_reply(u, uid, h); sess_put(uid, h)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    t = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not t: raise SystemExit("BOT_TOKEN missing")
    app = Application.builder().token(t).post_init(_mcp_init).build()
    for c, f in [("start",on_start),("help",on_start),("status",on_status),("provider",on_provider),("tools",on_tools),("reset",on_reset),("persona",on_persona)]:
        app.add_handler(CommandHandler(c, f))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_msg))
    log.info("cl0w up"); app.run_polling(drop_pending_updates=True)
if __name__ == "__main__": main()
