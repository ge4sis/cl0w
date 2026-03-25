import json
import subprocess
import os
import asyncio
import httpx
from typing import Optional, Dict, List, Any


class MCPClient:
    """
    Lightweight JSON-RPC client for Model Context Protocol (MCP).
    Supports stdio-based local MCP servers.
    """

    def __init__(self, command: str, args: list, env: Optional[Dict[str, str]] = None, label: str = "mcp_server"):
        self.command = command
        self.args = args
        self.env = env or {}
        self.label = label
        self.process: Any = None
        self._message_id = 0
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._tools_cache: List[Dict[str, Any]] = []
        self._is_initialized = False
        self.error: Optional[str] = None

    async def start(self):
        env = os.environ.copy()
        env.update(self.env)
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.command, *self.args,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                limit=1024 * 1024 * 5,
            )
            asyncio.create_task(self._read_stdout())
            asyncio.create_task(self._read_stderr())
            await self._initialize()
            self._is_initialized = True
            await self.fetch_tools()
            self.error = None
        except Exception as e:
            self.error = str(e)
            print(f"[MCP {self.label}] Failed to start: {e}")
            self.process = None

    async def stop(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self.process.kill()

    def is_running(self) -> bool:
        return self.process is not None and self._is_initialized and self.error is None

    def _get_next_id(self):
        self._message_id += 1
        return self._message_id

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.process or self.process.returncode is not None:
            raise RuntimeError(f"MCP Server '{self.label}' is not running.")

        msg_id = str(self._get_next_id())
        message: Dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            message["params"] = params

        future: asyncio.Future = asyncio.Future()
        self._pending_requests[msg_id] = future

        raw = json.dumps(message) + "\n"
        if self.process.stdin:
            self.process.stdin.write(raw.encode("utf-8"))
            await self.process.stdin.drain()

        try:
            response = await asyncio.wait_for(future, timeout=15.0)
            if "error" in response:
                raise RuntimeError(f"MCP RPC Error: {response['error']}")
            return response.get("result", {})
        finally:
            self._pending_requests.pop(msg_id, None)

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        if not self.process or self.process.returncode is not None:
            return
        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        raw = json.dumps(message) + "\n"
        if self.process.stdin:
            self.process.stdin.write(raw.encode("utf-8"))
            await self.process.stdin.drain()

    async def _read_stdout(self):
        while self.process and self.process.returncode is None and self.process.stdout:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                try:
                    data = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue
                msg_id = str(data.get("id"))
                if msg_id in self._pending_requests:
                    fut = self._pending_requests[msg_id]
                    if not fut.done():
                        fut.set_result(data)
            except Exception as e:
                print(f"[MCP {self.label}] Read error: {e}")
                break

    async def _read_stderr(self):
        while self.process and self.process.returncode is None and self.process.stderr:
            line = await self.process.stderr.readline()
            if not line:
                break

    async def _initialize(self):
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "cl0w", "version": "1.0.0"},
        })
        await self._send_notification("notifications/initialized")
        return result

    async def fetch_tools(self) -> list:
        if not self._is_initialized:
            return []
        result = await self._send_request("tools/list")
        self._tools_cache = result.get("tools", [])
        return self._tools_cache

    async def call_tool(self, name: str, arguments: dict) -> list:
        if not self._is_initialized:
            raise RuntimeError("MCP Client not initialized")
        result = await self._send_request("tools/call", {"name": name, "arguments": arguments})
        return result.get("content", [])

    def get_openai_tools_schema(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {}),
                },
            }
            for tool in self._tools_cache
        ]


class MCPSSEClient(MCPClient):
    """MCP Client that connects over HTTP POST/SSE for remote endpoints."""

    def __init__(self, url: str, label: str = "mcp_server"):
        super().__init__("", [], {}, label)
        self.url = url
        self.http = httpx.AsyncClient(timeout=30.0)

    async def start(self):
        try:
            self.process = True  # sentinel
            await self._initialize()
            self._is_initialized = True
            await self.fetch_tools()
            self.error = None
        except Exception as e:
            self.error = str(e)
            print(f"[MCP HTTP {self.label}] Failed to start: {e}")
            self.process = None

    def is_running(self) -> bool:
        return self.process is not None and self._is_initialized and self.error is None

    async def stop(self):
        await self.http.aclose()
        self.process = None

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        msg_id = str(self._get_next_id())
        message: Dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            message["params"] = params

        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        response = await self.http.post(self.url, json=message, headers=headers)
        response.raise_for_status()

        for line in response.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
                try:
                    result = json.loads(data_str)
                    if "error" in result:
                        raise RuntimeError(f"MCP RPC Error: {result['error']}")
                    return result.get("result", {})
                except json.JSONDecodeError:
                    pass
        raise RuntimeError(f"Failed to parse MCP response: {response.text}")

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        try:
            await self.http.post(self.url, json=message, headers=headers)
        except Exception:
            pass


class MCPManager:
    """Manages multiple MCP clients loaded from mcp.json."""

    def __init__(self, mcp_json_path: str):
        self.mcp_json_path = os.path.expanduser(mcp_json_path)
        self.clients: Dict[str, Any] = {}

    async def load_and_start_all(self):
        if not os.path.exists(self.mcp_json_path):
            print(f"[MCPManager] No mcp.json found at {self.mcp_json_path}")
            return

        try:
            with open(self.mcp_json_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[MCPManager] Error reading mcp.json: {e}")
            return

        servers = data.get("mcpServers", {})
        for label, cfg in servers.items():
            command = cfg.get("command")
            args = cfg.get("args", [])
            env = cfg.get("env", {})
            url = cfg.get("url")

            if command:
                client = MCPClient(command=command, args=args, env=env, label=label)
            elif url:
                client = MCPSSEClient(url=url, label=label)
            else:
                print(f"[MCPManager] Skipping '{label}': no command or url.")
                continue

            self.clients[label] = client
            await client.start()
            status = "OK" if client.is_running() else f"FAILED ({client.error})"
            print(f"[MCPManager] '{label}': {status}, {len(client._tools_cache)} tools.")

    async def stop_all(self):
        for client in self.clients.values():
            await client.stop()
        self.clients.clear()

    async def reload(self, mcp_json_path: Optional[str] = None):
        """Stop all servers, reload config, restart."""
        await self.stop_all()
        if mcp_json_path:
            self.mcp_json_path = os.path.expanduser(mcp_json_path)
        await self.load_and_start_all()

    def get_all_openai_tools(self) -> list:
        tools = []
        for client in self.clients.values():
            tools.extend(client.get_openai_tools_schema())
        return tools

    def get_status(self) -> list[dict]:
        """Returns status info for each server."""
        result = []
        for label, client in self.clients.items():
            result.append({
                "label": label,
                "running": client.is_running(),
                "tools": [t.get("name") for t in client._tools_cache],
                "error": client.error,
            })
        return result

    async def execute_tool_call(self, name: str, arguments: dict) -> str:
        target = None
        for client in self.clients.values():
            for tool in client._tools_cache:
                if tool.get("name") == name:
                    target = client
                    break
            if target:
                break

        if not target:
            return f"Error: Tool '{name}' not found in any running MCP server."

        try:
            content = await target.call_tool(name, arguments)
            text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
            return "\n".join(text_parts)
        except Exception as e:
            return f"Error executing tool '{name}': {e}"


_mcp_manager: Optional[MCPManager] = None


async def init_mcp(mcp_json_path: str = "./mcp.json") -> MCPManager:
    global _mcp_manager
    _mcp_manager = MCPManager(mcp_json_path)
    await _mcp_manager.load_and_start_all()
    return _mcp_manager
