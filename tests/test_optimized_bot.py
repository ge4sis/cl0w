import asyncio
import json
import os
import sys
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

# ── 작업 디렉토리를 프로젝트 루트로 고정 ──────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# ── telegram stub (bot.py import 전에 등록해야 함) ────────────────────────────
def _make_telegram_stub():
    telegram = types.ModuleType("telegram")
    telegram.Update = MagicMock()
    telegram.constants = types.ModuleType("telegram.constants")
    telegram.constants.ParseMode = MagicMock()
    telegram.InlineKeyboardButton = MagicMock()
    telegram.InlineKeyboardMarkup = MagicMock()

    ext = types.ModuleType("telegram.ext")
    ext.Application = MagicMock()
    ext.CommandHandler = MagicMock()
    ext.MessageHandler = MagicMock()
    ext.CallbackQueryHandler = MagicMock()
    ext.filters = MagicMock()
    ext.ContextTypes = MagicMock()

    telegram.ext = ext
    sys.modules.setdefault("telegram", telegram)
    sys.modules.setdefault("telegram.constants", telegram.constants)
    sys.modules.setdefault("telegram.ext", ext)

if "telegram" not in sys.modules:
    _make_telegram_stub()

# ── bot 모듈 임포트 ───────────────────────────────────────────────────────────
import bot  # noqa: E402

@pytest.mark.asyncio
class TestOptimizedBot:

    def test_constants_defined(self):
        """상수들이 정의되어 있는지 확인"""
        assert hasattr(bot, "MAX_MB")
        assert hasattr(bot, "MAX_CH")
        assert hasattr(bot, "IMG_EXT")
        assert hasattr(bot, "TXT_EXT")
        assert isinstance(bot.IMG_EXT, set)
        assert ".jpg" in bot.IMG_EXT
        assert ".py" in bot.TXT_EXT

    async def test_stream_reply_recursion_limit(self):
        """stream_reply 재귀 제한(10회) 작동 여부 테스트"""
        u = MagicMock()
        u.message.reply_text = AsyncMock(return_value=AsyncMock())
        uid = 123
        history = []

        # 무한히 도구 호출을 생성하는 mock llm_stream
        async def mock_llm_stream(uid, hist):
            yield {
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": f"call_{len(hist)}",
                        "function": {"name": "test_tool", "arguments": "{}"}
                    }]
                },
                "finish_reason": "tool_calls"
            }

        with patch("bot.llm_stream", side_effect=mock_llm_stream), \
             patch("bot.tool_run", AsyncMock(return_value="done")):
            
            result = await bot.stream_reply(u, uid, history)
            
            # recursive call 횟수 확인 (level 10 초과 시 "" 리턴)
            assert result == ""
            # u.message.reply_text가 "⚠️ 도구 호출 루프..." 메시지를 포함하여 호출되었는지 확인
            calls = [c.args[0] for c in u.message.reply_text.call_args_list if len(c.args) > 0]
            assert any("루프가 너무 깁니다" in str(msg) for msg in calls)

    async def test_on_persona_direct_switch(self):
        """/persona [name] 으로 직접 전환되는지 테스트 (switch 키워드 없이)"""
        u = MagicMock()
        u.effective_user.id = 1
        u.message.reply_text = AsyncMock()
        ctx = MagicMock()
        ctx.args = ["friendly"] # switch 키워드 생략

        with patch("bot.guard", AsyncMock(return_value=True)), \
             patch("bot.persona_switch", return_value=True) as mock_switch:
            await bot.on_persona(u, ctx)
            mock_switch.assert_called_with("friendly")
            u.message.reply_text.assert_called()
            assert "✅" in u.message.reply_text.call_args[0][0]

    async def test_mcp_cleanup_on_error(self):
        """MCP 세션 에러/취소 시 cleanup이 확실히 되는지 테스트"""
        name = "test_server"
        cfg = {"transport": "stdio", "command": "v", "args": []}
        
        # _mcp_sessions 에 미리 값을 넣어둠
        bot._mcp_sessions[name] = MagicMock()
        bot._mcp_tool_meta[f"mcp_{name}__tool"] = {"server": name}

        # raise Exception 하여 finally 구문 실행 유도
        with patch("mcp.client.stdio.stdio_client", side_effect=Exception("crash")):
             # _mcp_session_task는 while True이므로 timeout 처리하거나 한 번만 돌게 mock
             task = asyncio.create_task(bot._mcp_session_task(name, cfg))
             await asyncio.sleep(0.1)
             task.cancel()
             try: await task
             except asyncio.CancelledError: pass

        # finally 블록에 의해 제거되었어야 함
        assert name not in bot._mcp_sessions
        assert not any(v["server"] == name for v in bot._mcp_tool_meta.values())

    async def test_guard_no_message_robustness(self):
        """guard가 u.message가 None인 경우에도 크래시 없이 작동하는지"""
        u = MagicMock()
        u.effective_user.id = 1
        u.message = None # 메시지 객체가 없는 경우 (예: 일부 콜백)
        
        # rate limit 초과 상황 유도
        bot._buckets[1] = [time.time()] * 100 
        
        with patch.dict(bot.CFG, {"rate_limit": 20}):
            result = await bot.guard(u)
            assert result is False # 거부됨
            # 크래시 없어야 함
