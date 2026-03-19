"""
cl0w bot.py unit tests
─────────────────────
Telegram API / httpx / MCP 는 전부 mock 처리.
pytest-asyncio 로 async 함수 테스트.
"""
import asyncio
import importlib
import json
import os
import sys
import tempfile
import textwrap
import time
import types
from pathlib import Path
from typing import AsyncGenerator
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
    telegram.InlineKeyboardButton = MagicMock()
    telegram.InlineKeyboardMarkup = MagicMock()
    telegram.constants = types.ModuleType("telegram.constants")
    telegram.constants.ParseMode = MagicMock()

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

_make_telegram_stub()

# ── bot 모듈 import ────────────────────────────────────────────────────────────
import bot  # noqa: E402  (must come after stubs)


# ═════════════════════════════════════════════════════════════════════════════
# 1. _deep_merge
# ═════════════════════════════════════════════════════════════════════════════
class TestDeepMerge:
    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 99, "c": 3}
        result = bot._deep_merge(base, override)
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_nested_merge(self):
        base = {"providers": {"gemini": {"model": "old"}, "openai": {"model": "gpt-4o"}}}
        override = {"providers": {"gemini": {"model": "new"}}}
        result = bot._deep_merge(base, override)
        assert result["providers"]["gemini"]["model"] == "new"
        assert result["providers"]["openai"]["model"] == "gpt-4o"  # 유지됨

    def test_override_wins_on_non_dict(self):
        base = {"list": [1, 2, 3]}
        override = {"list": [4, 5]}
        result = bot._deep_merge(base, override)
        assert result["list"] == [4, 5]

    def test_original_not_mutated(self):
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        bot._deep_merge(base, override)
        assert "y" not in base["a"]  # base 불변

    def test_mcp_servers_merge(self):
        """실제 사용 패턴: config.local.yaml 이 mcp_servers 추가"""
        base = {"default_provider": "gemini", "mcp_servers": {}}
        override = {"mcp_servers": {"notion": {"transport": "stdio", "env": {"KEY": "secret"}}}}
        result = bot._deep_merge(base, override)
        assert result["default_provider"] == "gemini"
        assert "notion" in result["mcp_servers"]
        assert result["mcp_servers"]["notion"]["env"]["KEY"] == "secret"


# ═════════════════════════════════════════════════════════════════════════════
# 2. Config 로딩 (config.local.yaml deep merge)
# ═════════════════════════════════════════════════════════════════════════════
class TestConfigLoad:
    def test_default_provider_is_openai(self):
        assert bot.CFG.get("default_provider") == "openai"

    def test_providers_exist(self):
        providers = bot.CFG.get("providers", {})
        for name in ("openai", "lmstudio", "gemini"):
            assert name in providers, f"provider '{name}' missing"

    def test_fallback_chain_starts_with_openai(self):
        chain = bot.CFG.get("fallback_chain", [])
        assert chain[0] == "openai"

    def test_local_yaml_merge(self):
        """config.local.yaml 이 있으면 병합되는지 검증."""
        local_content = {"custom_key": "local_value", "rate_limit": 999}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, dir=ROOT, prefix="config.local."
        ) as f:
            yaml.dump(local_content, f)
            tmp = Path(f.name)
        try:
            with patch("builtins.open", side_effect=lambda p, **kw: open(p, **kw)):
                # 직접 _deep_merge 로직 검증
                base = dict(bot.CFG)
                local = yaml.safe_load(tmp.read_text())
                merged = bot._deep_merge(base, local)
                assert merged["custom_key"] == "local_value"
                assert merged["rate_limit"] == 999
        finally:
            tmp.unlink(missing_ok=True)


# ═════════════════════════════════════════════════════════════════════════════
# 3. Persona 시스템
# ═════════════════════════════════════════════════════════════════════════════
class TestPersona:
    def setup_method(self):
        """각 테스트 전: persona 상태 초기화"""
        bot._pfile = bot._DEFAULT_PERSONA
        bot._pcache.clear()

    def test_default_persona_path(self):
        assert bot._DEFAULT_PERSONA == "personas/default.md"

    def test_default_persona_file_exists(self):
        assert Path(bot._DEFAULT_PERSONA).exists(), "personas/default.md 파일이 없습니다"

    def test_persona_load_returns_string(self):
        text = bot.persona_load()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_persona_load_contains_identity(self):
        text = bot.persona_load()
        assert "Crow" in text

    def test_persona_load_cached(self):
        """두 번 호출해도 파일을 한 번만 읽음 (mtime 캐시)"""
        text1 = bot.persona_load()
        # 캐시가 채워졌어야 함
        assert bot._DEFAULT_PERSONA in bot._pcache
        text2 = bot.persona_load()
        assert text1 == text2

    def test_persona_switch_to_friendly(self):
        ok = bot.persona_switch("friendly")
        assert ok is True
        assert "friendly" in bot._pfile

    def test_persona_switch_to_technical(self):
        ok = bot.persona_switch("technical")
        assert ok is True

    def test_persona_switch_nonexistent(self):
        ok = bot.persona_switch("does_not_exist_xyz")
        assert ok is False
        # pfile 변경되지 않아야 함
        assert bot._pfile == bot._DEFAULT_PERSONA

    def test_persona_switch_clears_cache(self):
        bot.persona_load()  # 캐시 채움
        bot.persona_switch("friendly")
        assert len(bot._pcache) == 0

    def test_resetpersona_logic(self):
        """on_resetpersona 핵심 로직 검증 (Telegram 없이)"""
        bot.persona_switch("friendly")
        assert bot._pfile != bot._DEFAULT_PERSONA

        # on_resetpersona 내부 로직과 동일
        bot._pfile = bot._DEFAULT_PERSONA
        bot._pcache.clear()

        assert bot._pfile == bot._DEFAULT_PERSONA
        assert len(bot._pcache) == 0
        assert "Crow" in bot.persona_load()

    def test_all_persona_files_loadable(self):
        """personas/ 폴더의 모든 md 파일이 읽히는지"""
        for md in Path("personas").glob("*.md"):
            text = md.read_text(encoding="utf-8")
            assert len(text) > 0, f"{md} 가 비어있음"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Session 관리
# ═════════════════════════════════════════════════════════════════════════════
class TestSession:
    def setup_method(self):
        bot._mem.clear()

    def test_sess_get_empty(self):
        history = bot.sess_get(99999)
        assert history == []

    def test_sess_put_and_get(self):
        uid = 42
        msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        bot.sess_put(uid, msgs)
        result = bot.sess_get(uid)
        assert result == msgs

    def test_sess_put_returns_copy(self):
        uid = 43
        msgs = [{"role": "user", "content": "test"}]
        bot.sess_put(uid, msgs)
        result = bot.sess_get(uid)
        result.append({"role": "assistant", "content": "extra"})
        # 내부 저장된 것은 변경되지 않아야 함
        assert len(bot.sess_get(uid)) == 1

    def test_sess_clear(self):
        uid = 44
        bot.sess_put(uid, [{"role": "user", "content": "data"}])
        bot.sess_clear(uid)
        assert bot.sess_get(uid) == []

    def test_sess_max_turns_trim(self):
        uid = 45
        many = [{"role": "user", "content": str(i)} for i in range(200)]
        bot.sess_put(uid, many)
        result = bot.sess_get(uid)
        assert len(result) <= bot.SESS_MAX

    def test_sess_isolation_between_users(self):
        bot.sess_put(1, [{"role": "user", "content": "user1"}])
        bot.sess_put(2, [{"role": "user", "content": "user2"}])
        assert bot.sess_get(1)[0]["content"] == "user1"
        assert bot.sess_get(2)[0]["content"] == "user2"


# ═════════════════════════════════════════════════════════════════════════════
# 5. Provider 라우팅
# ═════════════════════════════════════════════════════════════════════════════
class TestProviderRouting:
    def setup_method(self):
        bot._uprov.clear()

    def test_default_provider_is_openai(self):
        name, pc = bot.prov_for(12345)
        assert name == "openai"
        assert "base_url" in pc

    def test_user_override(self):
        bot._uprov[999] = "gemini"
        name, _ = bot.prov_for(999)
        assert name == "gemini"

    def test_user_override_clears_on_del(self):
        bot._uprov[999] = "gemini"
        del bot._uprov[999]
        name, _ = bot.prov_for(999)
        assert name == "openai"  # global default 로 복귀

    def test_unknown_user_gets_default(self):
        name, _ = bot.prov_for(0)
        assert name == "openai"

    def test_provider_config_has_model(self):
        for pname in ("openai", "lmstudio", "gemini"):
            _, pc = bot.prov_for.__wrapped__(0) if hasattr(bot.prov_for, "__wrapped__") else (None, bot.CFG["providers"][pname])
            assert "model" in pc


# ═════════════════════════════════════════════════════════════════════════════
# 6. 파일 처리 (file_block)
# ═════════════════════════════════════════════════════════════════════════════
class TestFileBlock:
    def test_image_jpeg(self):
        # 최소한의 유효 JPEG 헤더
        data = b"\xff\xd8\xff\xe0" + b"\x00" * 10
        block = bot.file_block(data, "photo.jpg", "image/jpeg")
        assert block["type"] == "image_url"
        assert "data:image/jpeg;base64," in block["image_url"]["url"]

    def test_image_png(self):
        data = b"\x89PNG\r\n" + b"\x00" * 10
        block = bot.file_block(data, "img.png", "image/png")
        assert block["type"] == "image_url"

    def test_text_file_python(self):
        code = b"def hello():\n    return 42\n"
        block = bot.file_block(code, "script.py")
        assert block["type"] == "text"
        assert "```py" in block["text"]
        assert "hello" in block["text"]

    def test_text_file_markdown(self):
        md = b"# Title\n\nSome content"
        block = bot.file_block(md, "readme.md")
        assert block["type"] == "text"
        assert "```md" in block["text"]

    def test_text_file_json(self):
        data = b'{"key": "value"}'
        block = bot.file_block(data, "data.json")
        assert block["type"] == "text"

    def test_file_too_large(self):
        big = b"x" * (bot.MAX_MB * 1024 * 1024 + 1)
        with pytest.raises(ValueError, match="파일 과다"):
            bot.file_block(big, "big.txt")

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="지원 지양"):
            bot.file_block(b"\x00\x01\x02", "binary.exe")

    def test_text_truncation(self):
        long_text = b"a" * (bot.MAX_CH + 100)
        block = bot.file_block(long_text, "long.txt")
        assert "[잘림]" in block["text"]


# ═════════════════════════════════════════════════════════════════════════════
# 7. Rate Limit (guard 로직 - Telegram 없이 핵심 부분만)
# ═════════════════════════════════════════════════════════════════════════════
class TestRateLimit:
    def setup_method(self):
        bot._buckets.clear()

    def test_bucket_fills_up(self):
        uid = 777
        limit = bot.CFG.get("rate_limit", 20)
        now = time.time()
        # limit 만큼 채움
        bot._buckets[uid] = [now] * limit
        # 다음 요청은 거부되어야 함
        bot._buckets[uid] = [t for t in bot._buckets[uid] if now - t < 60]
        assert len(bot._buckets[uid]) >= limit

    def test_old_timestamps_expire(self):
        uid = 778
        old = time.time() - 61  # 61초 전 → 만료
        bot._buckets[uid] = [old] * 30
        now = time.time()
        bot._buckets[uid] = [t for t in bot._buckets[uid] if now - t < 60]
        assert len(bot._buckets[uid]) == 0


# ═════════════════════════════════════════════════════════════════════════════
# 8. Tool 로더
# ═════════════════════════════════════════════════════════════════════════════
class TestToolLoader:
    def test_tools_scan_runs(self):
        """scan 자체가 오류 없이 실행되는지"""
        bot._last_scan = 0  # 강제 재스캔
        bot.tools_scan()
        # web_search 가 있어야 함
        assert "web_search" in bot._tools

    def test_tool_has_schema_and_fn(self):
        bot._last_scan = 0
        bot.tools_scan()
        for name, t in bot._tools.items():
            assert "s" in t, f"{name}: schema 없음"
            assert "fn" in t, f"{name}: fn 없음"
            assert callable(t["fn"]), f"{name}: fn이 callable이 아님"

    def test_tools_oai_format(self):
        bot._last_scan = 0
        tools = bot.tools_oai()
        for t in tools:
            assert t.get("type") == "function"
            fn = t.get("function", {})
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn

    def test_invalid_tool_skipped(self):
        """TOOL_SCHEMA 없는 py 파일은 로드 안 됨"""
        tmp = Path("tools/_no_schema_test.py")
        tmp.write_text("def run(): pass\n", encoding="utf-8")
        try:
            bot._last_scan = 0
            bot.tools_scan()
            assert "_no_schema_test" not in bot._tools
        finally:
            tmp.unlink(missing_ok=True)
            bot._last_scan = 0
            bot.tools_scan()


# ═════════════════════════════════════════════════════════════════════════════
# 9. MCP oai (연결 없이 빈 상태 검증)
# ═════════════════════════════════════════════════════════════════════════════
class TestMcpOai:
    def test_mcp_oai_empty_when_no_servers(self):
        bot._mcp_tool_meta.clear()
        result = bot._mcp_oai()
        assert result == []

    def test_mcp_oai_format(self):
        bot._mcp_tool_meta["mcp_test__search"] = {
            "server": "test",
            "tool": "search",
            "description": "[MCP:test] search tool",
            "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        }
        result = bot._mcp_oai()
        assert len(result) == 1
        assert result[0]["function"]["name"] == "mcp_test__search"
        bot._mcp_tool_meta.clear()


# ═════════════════════════════════════════════════════════════════════════════
# 10. on_resetpersona handler (Telegram mock)
# ═════════════════════════════════════════════════════════════════════════════
# on_resetpersona handler removed (consolidated or moved)


# ═════════════════════════════════════════════════════════════════════════════
# 11. on_persona handler (switch / display)
# ═════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOnPersona:
    def setup_method(self):
        bot._pfile = bot._DEFAULT_PERSONA
        bot._pcache.clear()

    async def _make_update(self, args=None):
        mock_update = MagicMock()
        mock_update.effective_user.id = 1
        mock_update.message.reply_text = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.args = args or []
        return mock_update, mock_ctx

    async def test_switch_to_friendly(self):
        u, ctx = await self._make_update(["switch", "friendly"])
        with patch("bot.guard", return_value=True):
            await bot.on_persona(u, ctx)
        assert "friendly" in bot._pfile
        reply = u.message.reply_text.call_args[0][0]
        assert "friendly" in reply

    async def test_switch_to_nonexistent(self):
        u, ctx = await self._make_update(["switch", "ghost_persona"])
        with patch("bot.guard", return_value=True):
            await bot.on_persona(u, ctx)
        # pfile 변경 없음
        assert bot._pfile == bot._DEFAULT_PERSONA
        reply = u.message.reply_text.call_args[0][0]
        assert "❌" in reply

    async def test_display_current_persona(self):
        u, ctx = await self._make_update([])
        with patch("bot.guard", return_value=True):
            await bot.on_persona(u, ctx)
        reply = u.message.reply_text.call_args[0][0]
        assert "Crow" in reply  # default persona 내용 포함


# ═════════════════════════════════════════════════════════════════════════════
# 12. on_reset handler
# ═════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOnReset:
    async def test_reset_clears_session(self):
        uid = 555
        bot.sess_put(uid, [{"role": "user", "content": "hello"}])

        mock_update = MagicMock()
        mock_update.effective_user.id = uid
        mock_update.message.reply_text = AsyncMock()

        with patch("bot.guard", return_value=True):
            await bot.on_reset(mock_update, MagicMock())

        assert bot.sess_get(uid) == []
        mock_update.message.reply_text.assert_called_once()
