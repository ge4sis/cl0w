import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

_allowed_ids_str = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS: list[int] = []
if _allowed_ids_str:
    try:
        ALLOWED_USER_IDS = [int(u.strip()) for u in _allowed_ids_str.split(",") if u.strip()]
    except ValueError:
        print("Warning: ALLOWED_USER_IDS contains invalid integers.")

# LM Studio
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOOL_LOOPS = int(os.getenv("LLM_MAX_TOOL_LOOPS", "5"))

# cl0w paths
MCP_CONFIG_PATH = os.getenv("MCP_CONFIG_PATH", "./mcp.json")
PERSONAS_DIR = os.getenv("PERSONAS_DIR", "./personas")
SKILLS_DIR = os.getenv("SKILLS_DIR", "./skills")
DEFAULT_PERSONA = os.getenv("DEFAULT_PERSONA", "default")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN in environment variables.")
