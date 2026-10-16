from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from tools.base import NativeTool, ToolContext

if TYPE_CHECKING:
    from mcp_client import MCPManager

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry uniting Native cl0w tools and MCP tools.
    Native tools take priority on naming collisions.
    """

    def __init__(self):
        self._native_tools: Dict[str, NativeTool] = {}
        self._mcp_manager: Optional[MCPManager] = None

    def register_native_tool(self, tool: NativeTool) -> None:
        self._native_tools[tool.name] = tool
        logger.info(f"[ToolRegistry] Registered native tool: {tool.name}")

    def set_mcp_manager(self, manager: Optional[MCPManager]) -> None:
        self._mcp_manager = manager

    def get_all_openai_tools(self) -> List[dict]:
        tools: List[dict] = []
        registered_names = set()

        # 1. Native tools first
        for name, tool in self._native_tools.items():
            tools.append(tool.openai_schema())
            registered_names.add(name)

        # 2. MCP tools next (skipping collisions with native tools)
        if self._mcp_manager:
            mcp_tools = self._mcp_manager.get_all_openai_tools()
            for schema in mcp_tools:
                func_name = schema.get("function", {}).get("name")
                if func_name in registered_names:
                    logger.warning(
                        f"[ToolRegistry] MCP tool '{func_name}' collides with native tool. Native tool takes precedence."
                    )
                    continue
                tools.append(schema)
                registered_names.add(func_name)

        return tools

    async def execute_tool_call(
        self, name: str, arguments: dict, ctx: Optional[ToolContext] = None
    ) -> str:
        # Check native tools
        if name in self._native_tools:
            try:
                return await self._native_tools[name].run(arguments, ctx)
            except Exception as e:
                logger.error(f"[ToolRegistry] Native tool '{name}' failed: {e}", exc_info=True)
                return f"Error executing native tool '{name}': {e}"

        # Delegate to MCP
        if self._mcp_manager:
            return await self._mcp_manager.execute_tool_call(name, arguments)

        return f"Error: Tool '{name}' not found in registry."

    def get_status(self) -> dict[str, Any]:
        return {
            "native_tools": list(self._native_tools.keys()),
            "mcp_status": self._mcp_manager.get_status() if self._mcp_manager else [],
        }
