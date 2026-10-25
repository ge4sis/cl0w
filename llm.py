import re
import json
import time
import logging
from typing import TYPE_CHECKING, Optional, List, Any
import httpx
from openai import AsyncOpenAI

import config
from compaction import estimate_tokens, prune_past_tool_outputs, compact_session_history, normalize_message

if TYPE_CHECKING:
    from tools.registry import ToolRegistry
    from mcp_client import MCPManager

logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    base_url=config.LM_STUDIO_BASE_URL,
    api_key=config.LM_STUDIO_API_KEY,
)

_tool_registry: Optional["ToolRegistry"] = None

# Cache for auto-detected context window size
_cached_context_size: Optional[int] = None
_context_size_timestamp: float = 0.0


def set_tool_registry(registry: "ToolRegistry"):
    global _tool_registry
    _tool_registry = registry


def set_mcp_manager(manager: "MCPManager"):
    """Backward compatibility helper."""
    global _tool_registry
    if _tool_registry:
        _tool_registry.set_mcp_manager(manager)


async def get_context_window_size() -> int:
    """
    Probes LM Studio's /v1/models endpoint to auto-detect the runtime context length
    configured on the loaded model. Falls back to config.LM_STUDIO_CONTEXT_SIZE.
    Cached for 300 seconds.
    """
    global _cached_context_size, _context_size_timestamp
    now = time.time()
    if _cached_context_size and (now - _context_size_timestamp < 300):
        return _cached_context_size

    try:
        url = f"{config.LM_STUDIO_BASE_URL.rstrip('/')}/models"
        async with httpx.AsyncClient(timeout=3.0) as http_client:
            res = await http_client.get(url)
            if res.status_code == 200:
                data = res.json()
                models = data.get("data", [])
                for m in models:
                    ctx = (
                        m.get("max_context_length")
                        or m.get("context_length")
                        or m.get("context_window")
                    )
                    if ctx and isinstance(ctx, int) and ctx > 0:
                        logger.info(f"[Context Probe] Auto-detected context length from LM Studio: {ctx:,} tokens")
                        _cached_context_size = ctx
                        _context_size_timestamp = now
                        return ctx
    except Exception as e:
        logger.debug(f"[Context Probe] Could not auto-detect context size: {e}")

    _cached_context_size = config.LM_STUDIO_CONTEXT_SIZE
    _context_size_timestamp = now
    logger.info(f"[Context Probe] Using configured context length: {_cached_context_size:,} tokens")
    return _cached_context_size


def _clean_response(raw: str) -> str:
    """Remove <think>/<thought> blocks and stray reasoning preambles."""
    cleaned = re.sub(
        r"<(?:think|thought)>.*?(?:</(?:think|thought)>|$)",
        "",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if "Thinking Process:" in cleaned and "---" in cleaned:
        parts = cleaned.split("---", 1)
        if "Thinking Process:" in parts[0]:
            cleaned = parts[1]
    cleaned = cleaned.strip()
    return cleaned if cleaned else raw


async def generate_response(
    messages: list,
    profiles: Optional[List[str]] = None,
    allowed_tools: Optional[List[str]] = None,
) -> str:
    """
    Send message history to the local LLM.
    Handles:
      1. Level 1 Tool output compaction on past turns
      2. Dynamic tool selection (profiles / allowed_tools)
      3. Level 2 Ratio-based Rolling Auto-Compaction when >= 70% of context window
      4. Tool-call execution loop
      5. finish_reason: length and silent failure safeguards
    """
    try:
        # 0. Ensure all messages are standard dicts (converts any ChatCompletionMessage objects)
        for idx in range(len(messages)):
            if not isinstance(messages[idx], dict):
                messages[idx] = normalize_message(messages[idx])

        # 1. Level 1 Auto-Compaction: prune past verbose tool outputs
        prune_past_tool_outputs(messages)

        # 2. Dynamic Tool Selection
        tools = []
        if _tool_registry:
            tools = _tool_registry.get_tools(profiles=profiles, allowed_tools=allowed_tools)

        # 3. Context Window Check & Level 2 Rolling Compaction
        context_limit = await get_context_window_size()
        threshold_tokens = int(context_limit * config.COMPACTION_THRESHOLD_RATIO)
        estimated_tokens = estimate_tokens(messages, tools)

        if estimated_tokens >= threshold_tokens:
            logger.warning(
                f"[Compaction] Tokens ({estimated_tokens:,}) exceeded threshold ({threshold_tokens:,} "
                f"= {int(config.COMPACTION_THRESHOLD_RATIO*100)}% of {context_limit:,}). Triggering rolling compaction..."
            )
            await compact_session_history(
                messages,
                context_limit=context_limit,
                target_ratio=config.COMPACTION_TARGET_RATIO,
                client=client,
                model=config.LM_STUDIO_MODEL,
            )

        kwargs = {
            "model": config.LM_STUDIO_MODEL,
            "messages": messages,
            "temperature": config.LLM_TEMPERATURE,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)

        loop_count = 0
        while (
            response.choices[0].finish_reason == "tool_calls"
            and loop_count < config.LLM_MAX_TOOL_LOOPS
        ):
            loop_count += 1
            tool_calls = response.choices[0].message.tool_calls
            messages.append(normalize_message(response.choices[0].message))

            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except Exception:
                    tool_args = {}

                print(f"[Tool] {tool_name}({tool_args})")

                if _tool_registry:
                    result_text = await _tool_registry.execute_tool_call(tool_name, tool_args)
                else:
                    result_text = "Error: Tool Registry not initialized."

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tool_name,
                    "content": str(result_text),
                })

            response = await client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        finish_reason = choice.finish_reason
        raw = choice.message.content or ""

        # Safeguard against length cutoffs (reasoning token starvation)
        if finish_reason == "length":
            logger.warning("[LLM] Generation finished with finish_reason='length'.")
            if not raw.strip():
                raw = (
                    "⚠️ [안내] 모델의 컨텍스트 한도에 도달하여 응답이 생성 도중 중단되었습니다. "
                    "세션 히스토리가 자동으로 압축되었거나, 필요 시 /new 로 새 세션을 시작해주세요."
                )
            else:
                raw += "\n\n⚠️ (컨텍스트 길이 제한에 도달하여 답변 뒷부분이 잘렸을 수 있습니다.)"

        elif not raw and finish_reason == "tool_calls":
            raw = (
                f"⚠️ 도구 실행 횟수 한도({config.LLM_MAX_TOOL_LOOPS}회)를 초과하여 대답을 생성하지 못했습니다. "
                "권한이 거부되었거나 오류가 지속되었는지 확인해주세요."
            )

        return _clean_response(raw)

    except Exception as e:
        err_msg = str(e)
        logger.error(f"[LLM Error] {err_msg}", exc_info=True)

        # Emergency Fallback: If server rejects due to context size, force aggressive compaction and retry once
        if "exceeds the available context size" in err_msg or "context" in err_msg.lower():
            logger.warning("[LLM] Server rejected context size. Executing emergency compaction & retrying once...")
            context_limit = await get_context_window_size()
            await compact_session_history(
                messages,
                context_limit=context_limit,
                target_ratio=0.20,
                client=None,  # skip llm call, use extractive summary for speed
            )
            try:
                retry_kwargs = {
                    "model": config.LM_STUDIO_MODEL,
                    "messages": messages,
                    "temperature": config.LLM_TEMPERATURE,
                }
                if tools:
                    retry_kwargs["tools"] = tools
                    retry_kwargs["tool_choice"] = "auto"
                retry_resp = await client.chat.completions.create(**retry_kwargs)
                retry_raw = retry_resp.choices[0].message.content or ""
                return _clean_response(retry_raw)
            except Exception as retry_err:
                logger.error(f"[LLM Emergency Retry Failed] {retry_err}")

        is_conn_error = any(
            err_type in type(e).__name__.lower()
            for err_type in ["connect", "timeout", "network", "apiconnection"]
        ) or any(
            err_phrase in err_msg.lower()
            for err_phrase in ["connection refused", "connecterror", "failed to connect", "timed out"]
        )
        if is_conn_error:
            return f"LLM 서버 연결 오류가 발생했습니다: {err_msg}\n\nLM Studio 실행 여부와 포트 설정을 확인해주세요."
        return f"요청 처리 중 오류가 발생했습니다: {err_msg}"
