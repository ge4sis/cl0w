import logging
from datetime import datetime

from telegram import Update, BotCommand
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

import config
import llm
import mcp_client as mcp_module
from persona_manager import PersonaManager
from skill_manager import SkillManager
from file_handler import process_file

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ─── Global managers ──────────────────────────────────────────────────────────
persona_mgr = PersonaManager(config.PERSONAS_DIR, config.DEFAULT_PERSONA)
skill_mgr = SkillManager(config.SKILLS_DIR)

# user_id → list of message dicts
user_sessions: dict[int, list] = {}
# user_id → active persona name (stem key)
user_persona: dict[int, str] = {}


# ─── Session helpers ──────────────────────────────────────────────────────────

def _system_prompt(user_id: int) -> str:
    persona_key = user_persona.get(user_id, config.DEFAULT_PERSONA)
    base = persona_mgr.get_system_prompt(persona_key)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"{base}\n\nCurrent date and time: {now}"


def get_session(user_id: int) -> list:
    if user_id not in user_sessions:
        user_sessions[user_id] = [{"role": "system", "content": _system_prompt(user_id)}]
    return user_sessions[user_id]


def reset_session(user_id: int):
    user_sessions[user_id] = [{"role": "system", "content": _system_prompt(user_id)}]


def reset_full(user_id: int):
    """Reset session AND persona to default."""
    user_persona[user_id] = config.DEFAULT_PERSONA
    reset_session(user_id)


# ─── Auth ─────────────────────────────────────────────────────────────────────

async def _check_auth(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    if config.ALLOWED_USER_IDS and user.id not in config.ALLOWED_USER_IDS:
        logger.warning(f"Unauthorized: {user.id} ({user.username})")
        await update.message.reply_text("권한이 없습니다.")
        return False
    return True


# ─── Utilities ────────────────────────────────────────────────────────────────

async def _send_long(update: Update, text: str):
    MAX = 4050
    for i in range(0, len(text), MAX):
        await update.message.reply_text(text[i:i + MAX])


async def _typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )


async def _reply_and_llm(update: Update, context: ContextTypes.DEFAULT_TYPE, message_dict: dict):
    """Append message_dict to session, call LLM, send response."""
    user_id = update.effective_user.id
    session = get_session(user_id)
    await _typing(update, context)
    session.append(message_dict)
    response = await llm.generate_response(session)
    session.append({"role": "assistant", "content": response})
    await _send_long(update, response)


# ─── /start ───────────────────────────────────────────────────────────────────

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return
    reset_full(update.effective_user.id)
    await update.message.reply_text(
        "👋 cl0w 에이전트가 초기화 되었습니다.\n대화와 Persona가 초기화되었습니다. 무엇을 도와드릴까요?\n\n/help 로 명령어 목록을 볼 수 있습니다."
    )


# ─── /new ─────────────────────────────────────────────────────────────────────

async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return
    reset_session(update.effective_user.id)
    await update.message.reply_text("대화 히스토리를 초기화했습니다. Persona는 유지됩니다.")


# ─── /help ────────────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return

    skill_list = "\n".join(
        f"  `/{s.name}` — {s.description}" for s in skill_mgr.list_all()
    )

    text = (
        "*cl0w 명령어 가이드*\n\n"
        "*일반*\n"
        "  `/start` — 대화 + Persona 전체 초기화\n"
        "  `/new` — 대화 히스토리만 초기화\n"
        "  `/status` — 현재 상태 확인\n"
        "  `/help` — 이 도움말\n\n"
        "*Persona*\n"
        "  `/persona` — 현재 Persona 확인\n"
        "  `/persona list` — Persona 목록\n"
        "  `/persona set <name>` — Persona 변경\n"
        "  `/persona reset` — 기본 Persona로 복귀\n\n"
        "*Skill*\n"
        "  `/skill` — Skill 목록\n"
        "  `/skill <name> [args]` — Skill 실행\n"
        f"{skill_list}\n\n"
        "*MCP*\n"
        "  `/mcp` — MCP 서버/툴 목록\n"
        "  `/mcp reload` — MCP 설정 재로드\n\n"
        "*파일*\n"
        "  이미지, PDF, Word(.docx), 텍스트, 코드 파일을 그냥 보내면 처리해줘.\n"
        "  캡션으로 지시사항을 함께 보내도 돼."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── /status ──────────────────────────────────────────────────────────────────

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return

    user_id = update.effective_user.id
    persona_key = user_persona.get(user_id, config.DEFAULT_PERSONA)
    persona = persona_mgr.get(persona_key)
    persona_info = f"{persona.name} — {persona.description}" if persona else persona_key

    mcp_status = mcp_module._mcp_manager
    if mcp_status:
        statuses = mcp_status.get_status()
        if statuses:
            mcp_lines = []
            for s in statuses:
                icon = "✅" if s["running"] else "❌"
                tools_str = ", ".join(s["tools"]) if s["tools"] else "없음"
                err = f" ({s['error']})" if s["error"] else ""
                mcp_lines.append(f"  {icon} `{s['label']}`{err}\n     tools: {tools_str}")
            mcp_text = "\n".join(mcp_lines)
        else:
            mcp_text = "  등록된 MCP 서버 없음"
    else:
        mcp_text = "  MCP 미초기화"

    session_len = len(get_session(user_id)) - 1  # exclude system prompt

    text = (
        f"*cl0w 상태*\n\n"
        f"*Persona:* {persona_info}\n"
        f"*대화 히스토리:* {session_len}턴\n"
        f"*LLM:* `{config.LM_STUDIO_BASE_URL}` / model: `{config.LM_STUDIO_MODEL}`\n\n"
        f"*MCP 서버:*\n{mcp_text}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── /persona ─────────────────────────────────────────────────────────────────

async def persona_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return

    user_id = update.effective_user.id
    args = context.args or []

    if not args:
        # Show current persona
        key = user_persona.get(user_id, config.DEFAULT_PERSONA)
        p = persona_mgr.get(key)
        if p:
            await update.message.reply_text(
                f"*현재 Persona:* {p.name}\n{p.description}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(f"현재 Persona: `{key}` (파일 없음)", parse_mode="Markdown")
        return

    sub = args[0].lower()

    if sub == "list":
        personas = persona_mgr.list_all()
        if not personas:
            await update.message.reply_text("사용 가능한 Persona가 없습니다. `personas/` 폴더를 확인해주세요.")
            return
        lines = [f"  `{p.name}` — {p.description}" for p in personas]
        await update.message.reply_text(
            "*사용 가능한 Persona:*\n" + "\n".join(lines),
            parse_mode="Markdown",
        )

    elif sub == "set":
        if len(args) < 2:
            await update.message.reply_text("사용법: `/persona set <name>`", parse_mode="Markdown")
            return
        target = args[1].lower()
        if not persona_mgr.get(target):
            await update.message.reply_text(
                f"`{target}` Persona를 찾을 수 없습니다. `/persona list` 로 확인해주세요.",
                parse_mode="Markdown",
            )
            return
        user_persona[user_id] = target
        reset_session(user_id)
        p = persona_mgr.get(target)
        await update.message.reply_text(
            f"Persona를 *{p.name}* 으로 변경했습니다. 대화 히스토리도 초기화되었습니다.",
            parse_mode="Markdown",
        )

    elif sub == "reset":
        user_persona[user_id] = config.DEFAULT_PERSONA
        reset_session(user_id)
        await update.message.reply_text("Persona를 기본값으로 초기화했습니다.")

    else:
        await update.message.reply_text(
            "알 수 없는 서브 명령어야. `/persona list`, `/persona set <name>`, `/persona reset` 을 써봐.",
            parse_mode="Markdown",
        )


# ─── /skill ───────────────────────────────────────────────────────────────────

async def skill_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return

    args = context.args or []

    if not args or args[0].lower() == "list":
        skills = skill_mgr.list_all()
        if not skills:
            await update.message.reply_text("사용 가능한 Skill이 없습니다. `skills/` 폴더를 확인해주세요.")
            return
        lines = [f"  `{s.usage}` — {s.description}" for s in skills]
        await update.message.reply_text(
            "*사용 가능한 Skill:*\n" + "\n".join(lines),
            parse_mode="Markdown",
        )
        return

    skill_name = args[0].lower()
    skill_args = args[1:]

    await _run_skill(update, context, skill_name, skill_args)


async def _run_skill(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    skill_name: str,
    skill_args: list[str],
):
    user_id = update.effective_user.id
    session = get_session(user_id)

    # Build context string from last assistant message for context-only skills
    context_text = ""
    for msg in reversed(session):
        if msg["role"] == "assistant" and isinstance(msg["content"], str):
            context_text = msg["content"]
            break

    rendered = skill_mgr.render(skill_name, skill_args, context=context_text)
    if rendered is None:
        await update.message.reply_text(
            f"`{skill_name}` Skill을 찾을 수 없습니다. `/skill` 로 목록을 확인해주세요.",
            parse_mode="Markdown",
        )
        return

    await _reply_and_llm(update, context, {"role": "user", "content": rendered})


# ─── /mcp ─────────────────────────────────────────────────────────────────────

async def mcp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return

    args = context.args or []
    sub = args[0].lower() if args else "list"

    manager = mcp_module._mcp_manager

    if sub == "list" or sub == "":
        if not manager:
            await update.message.reply_text("MCP가 초기화되지 않았습니다.")
            return
        statuses = manager.get_status()
        if not statuses:
            await update.message.reply_text("등록된 MCP 서버가 없습니다.\n`mcp.json` 파일을 확인해주세요.")
            return
        lines = []
        for s in statuses:
            icon = "✅" if s["running"] else "❌"
            tools = ", ".join(f"`{t}`" for t in s["tools"]) if s["tools"] else "없음"
            err = f"\n     오류: {s['error']}" if s["error"] else ""
            lines.append(f"{icon} *{s['label']}*{err}\n   tools: {tools}")
        await update.message.reply_text(
            "*MCP 서버 목록:*\n\n" + "\n\n".join(lines),
            parse_mode="Markdown",
        )

    elif sub == "reload":
        await update.message.reply_text("MCP 서버를 재시작하겠습니다...")
        if manager:
            await manager.reload(config.MCP_CONFIG_PATH)
        else:
            new_manager = await mcp_module.init_mcp(config.MCP_CONFIG_PATH)
            llm.set_mcp_manager(new_manager)
        statuses = mcp_module._mcp_manager.get_status() if mcp_module._mcp_manager else []
        running = sum(1 for s in statuses if s["running"])
        await update.message.reply_text(f"MCP 재로드 완료. {running}/{len(statuses)} 서버 실행 중.")

    elif sub == "status":
        await mcp_cmd.__wrapped__(update, context) if hasattr(mcp_cmd, "__wrapped__") else await mcp_cmd(update, context)

    else:
        await update.message.reply_text(
            "알 수 없는 서브 명령어입니다. `/mcp list`, `/mcp reload` 를 써보세요.",
            parse_mode="Markdown",
        )


# ─── Text handler ─────────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return
    user_text = update.message.text
    await _reply_and_llm(update, context, {"role": "user", "content": user_text})


# ─── Photo handler ────────────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return

    import base64
    await _typing(update, context)

    photo_file = await update.message.photo[-1].get_file()
    byte_array = await photo_file.download_as_bytearray()
    b64 = base64.b64encode(byte_array).decode("utf-8")
    image_url = f"data:image/jpeg;base64,{b64}"

    caption = update.message.caption
    content = []
    if caption:
        content.append({"type": "text", "text": caption})
    else:
        content.append({"type": "text", "text": "이 이미지에 대해 설명해줘."})
    content.append({"type": "image_url", "image_url": {"url": image_url}})

    user_id = update.effective_user.id
    session = get_session(user_id)
    session.append({"role": "user", "content": content})
    response = await llm.generate_response(session)
    session.append({"role": "assistant", "content": response})
    await _send_long(update, response)


# ─── Document handler ─────────────────────────────────────────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return

    await _typing(update, context)

    doc = update.message.document
    filename = doc.file_name or "file"
    caption = update.message.caption

    tg_file = await doc.get_file()
    data = await tg_file.download_as_bytearray()

    try:
        message_dict = process_file(bytes(data), filename, caption)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    user_id = update.effective_user.id
    session = get_session(user_id)
    session.append(message_dict)
    response = await llm.generate_response(session)
    session.append({"role": "assistant", "content": response})
    await _send_long(update, response)


# ─── Dynamic skill shortcut handler ───────────────────────────────────────────
# Handles /<skill-name> [args] for registered skills

async def dynamic_skill_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return

    command = update.message.text.split()[0].lstrip("/").split("@")[0].lower()
    args = context.args or []
    await _run_skill(update, context, command, args)


# ─── App setup ────────────────────────────────────────────────────────────────

async def post_init(app):
    """Load managers and initialize MCP after the bot starts."""
    persona_mgr.load_all()
    skill_mgr.load_all()

    logger.info(f"Loaded {len(persona_mgr.list_all())} personas, {len(skill_mgr.list_all())} skills.")

    manager = await mcp_module.init_mcp(config.MCP_CONFIG_PATH)
    llm.set_mcp_manager(manager)

    # Register bot commands for Telegram menu
    commands = [
        BotCommand("start", "대화 + Persona 전체 초기화"),
        BotCommand("new", "대화 히스토리 초기화"),
        BotCommand("persona", "Persona 관리"),
        BotCommand("skill", "Skill 실행"),
        BotCommand("mcp", "MCP 서버 관리"),
        BotCommand("status", "현재 상태 확인"),
        BotCommand("help", "도움말"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot commands registered.")


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Core commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("new", new_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    # Persona & Skill & MCP
    app.add_handler(CommandHandler("persona", persona_cmd))
    app.add_handler(CommandHandler("skill", skill_cmd))
    app.add_handler(CommandHandler("mcp", mcp_cmd))

    # Skill shortcuts (e.g. /translate, /summarize, /review, /explain)
    skill_mgr.load_all()  # need names at registration time
    for s in skill_mgr.list_all():
        app.add_handler(CommandHandler(s.name, dynamic_skill_handler))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("cl0w is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
