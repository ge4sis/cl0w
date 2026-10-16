from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolContext:
    """Per-request context handed to native tools (who asked, where to reply)."""
    bot: Any = None
    chat_id: Optional[int] = None


_current_ctx: contextvars.ContextVar[Optional[ToolContext]] = contextvars.ContextVar(
    "cl0w_tool_ctx", default=None
)


def set_tool_context(ctx: ToolContext) -> contextvars.Token:
    return _current_ctx.set(ctx)


def reset_tool_context(token: contextvars.Token) -> None:
    _current_ctx.reset(token)


def get_tool_context() -> Optional[ToolContext]:
    return _current_ctx.get()


class NativeTool:
    """Base class for tools implemented directly inside cl0w."""

    name: str = ""
    description: str = ""
    parameters: dict = {"type": "object", "properties": {}}

    async def run(self, args: dict, ctx: Optional[ToolContext]) -> str:
        raise NotImplementedError

    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
