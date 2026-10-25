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
        """Backward-compatible method returning all registered tools."""
        return self.get_tools(profiles=["all"])

    def get_tools(
        self,
        profiles: Optional[List[str]] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> List[dict]:
        """
        Dynamically returns tool schemas based on requested profiles or allowed tool names/server names.

        profiles:
            - 'core': native tools + 'exa' (search)
            - 'finance': 'yahoo-finance', 'fred', 'korean-dart', 'korea-stock-analyzer'
            - 'native': native workspace tools only
            - 'all': everything
        allowed_tools:
            - List of specific tool names (e.g. ['web_search_advanced_exa', 'shell_exec'])
              or server labels (e.g. ['exa', 'native']).
        """
        if profiles is None and allowed_tools is None:
            profiles = ["all"]

        profiles_set = {p.lower() for p in (profiles or [])}
        allowed_set = {t.lower() for t in (allowed_tools or [])}

        include_all = "all" in profiles_set or "all" in allowed_set
        include_native = (
            include_all
            or "native" in profiles_set
            or "core" in profiles_set
            or "native" in allowed_set
        )

        # Determine which MCP servers to include
        finance_servers = {"yahoo-finance", "fred", "korean-dart", "korea-stock-analyzer"}
        target_mcp_servers: Optional[set[str]] = None

        if not include_all:
            target_mcp_servers = set()
            if "core" in profiles_set:
                target_mcp_servers.add("exa")
            if "finance" in profiles_set:
                target_mcp_servers.update(finance_servers)
            # Check allowed_tools for server names
            for item in allowed_set:
                if item == "exa":
                    target_mcp_servers.add("exa")
                elif item in finance_servers:
                    target_mcp_servers.add(item)
                elif item == "finance":
                    target_mcp_servers.update(finance_servers)

        tools: List[dict] = []
        registered_names = set()

        # 1. Native tools
        for name, tool in self._native_tools.items():
            if include_native or name.lower() in allowed_set:
                tools.append(tool.openai_schema())
                registered_names.add(name)

        # 2. MCP tools
        if self._mcp_manager:
            mcp_tools = self._mcp_manager.get_all_openai_tools()
            for schema in mcp_tools:
                func_name = schema.get("function", {}).get("name", "")
                if not func_name or func_name in registered_names:
                    continue

                # Check if tool is allowed
                if include_all:
                    tools.append(schema)
                    registered_names.add(func_name)
                    continue

                # Check by specific tool name
                if func_name.lower() in allowed_set:
                    tools.append(schema)
                    registered_names.add(func_name)
                    continue

                # Check by server affiliation
                if target_mcp_servers is not None:
                    # Find which server owns this tool
                    for server_label in target_mcp_servers:
                        client = self._mcp_manager.clients.get(server_label)
                        if client and any(t.get("name") == func_name for t in client._tools_cache):
                            tools.append(schema)
                            registered_names.add(func_name)
                            break

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
