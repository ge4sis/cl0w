import re
import json
from openai import AsyncOpenAI
from typing import TYPE_CHECKING, Optional

import config

if TYPE_CHECKING:
    from tools.registry import ToolRegistry
    from mcp_client import MCPManager

client = AsyncOpenAI(
    base_url=config.LM_STUDIO_BASE_URL,
    api_key=config.LM_STUDIO_API_KEY,
)

_tool_registry: Optional["ToolRegistry"] = None


def set_tool_registry(registry: "ToolRegistry"):
    global _tool_registry
    _tool_registry = registry


def set_mcp_manager(manager: "MCPManager"):
    """Backward compatibility helper."""
    global _tool_registry
    if _tool_registry:
        _tool_registry.set_mcp_manager(manager)


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


async def generate_response(messages: list) -> str:
    """
    Send message history to the local LLM.
    Handles tool_call loops via MCP when available.
    Returns cleaned response string.
    """
    try:
        kwargs = {
            "model": config.LM_STUDIO_MODEL,
            "messages": messages,
            "temperature": config.LLM_TEMPERATURE,
        }

        tools = []
        if _tool_registry:
            tools = _tool_registry.get_all_openai_tools()
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
            messages.append(response.choices[0].message)

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

        raw = response.choices[0].message.content or ""
        if not raw and response.choices[0].finish_reason == "tool_calls":
            raw = (
                f"⚠️ 도구 실행 횟수 한도({config.LLM_MAX_TOOL_LOOPS}회)를 초과하여 대답을 생성하지 못했습니다. "
                "권한이 거부되었거나 오류가 지속되었는지 확인해주세요."
            )
        return _clean_response(raw)

    except Exception as e:
        print(f"[LLM Error] {e}")
        return "LLM 서버에 연결할 수 없어요. LM Studio가 실행 중인지 확인해주세요."
