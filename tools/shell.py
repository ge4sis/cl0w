from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from datetime import datetime
from typing import Optional

from tools.base import NativeTool, ToolContext
from tools.sandbox import (
    build_env,
    build_profile,
    check_blocked,
    default_deny_read_paths,
    sandbox_available,
    wrap_command,
)
from tools.workspace import Workspace


def _truncate_output(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head_len = max_chars // 2
    tail_len = max_chars - head_len
    omitted = len(text) - (head_len + tail_len)
    return (
        text[:head_len]
        + f"\n\n[... {omitted} characters truncated ...]\n\n"
        + text[-tail_len:]
    )


class ShellExecTool(NativeTool):
    name = "shell_exec"
    description = (
        "Execute a shell command inside the sandboxed workspace. "
        "Commands run in bash with the workspace venv active (python/pip). "
        "File writes outside the workspace are blocked by OS sandbox. "
        "Returns exit code, stdout, and stderr."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The exact shell command line string to run.",
            },
            "cwd": {
                "type": "string",
                "description": "Optional subdirectory within the workspace. Defaults to workspace root.",
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds. Defaults to config (120s).",
            },
        },
        "required": ["command"],
    }

    def __init__(
        self,
        workspace: Workspace,
        default_timeout: int = 120,
        max_output: int = 8000,
        use_sandbox: bool = True,
        extra_deny_read: Optional[list[str]] = None,
    ):
        self.workspace = workspace
        self.default_timeout = default_timeout
        self.max_output = max_output
        self.use_sandbox = use_sandbox and sandbox_available()
        self.extra_deny_read = extra_deny_read or []

    async def run(self, args: dict, ctx: Optional[ToolContext]) -> str:
        command = args.get("command", "").strip()
        if not command:
            return "Error: command is required."

        # Check explicit blocked commands
        blocked = check_blocked(command)
        if blocked:
            return f"Error: Command '{blocked}' is blocked for security reasons."

        cwd_arg = args.get("cwd")
        try:
            safe_cwd = self.workspace.resolve(cwd_arg)
        except PermissionError as e:
            return str(e)

        timeout = args.get("timeout") or self.default_timeout
        try:
            timeout = int(timeout)
        except (ValueError, TypeError):
            timeout = self.default_timeout

        self.workspace.ensure()

        env = build_env(
            workspace_root=self.workspace.root,
            home_dir=self.workspace.home_dir,
            venv_dir=self.workspace.venv_dir,
        )

        base_argv = ["/bin/bash", "-c", command]

        if self.use_sandbox:
            deny_paths = default_deny_read_paths(self.extra_deny_read)
            profile, params = build_profile(self.workspace.root, deny_paths)
            cmd_argv = wrap_command(base_argv, profile, params)
        else:
            cmd_argv = base_argv

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_argv,
                cwd=safe_cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # New process group for clean kill
            )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=float(timeout)
                )
            except asyncio.TimeoutError:
                # Terminate entire process group
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                return f"Error: Command timed out after {timeout} seconds."

            stdout_str = stdout_b.decode("utf-8", errors="replace")
            stderr_str = stderr_b.decode("utf-8", errors="replace")

            output_blocks = []
            if stdout_str:
                output_blocks.append(f"--- STDOUT ---\n{stdout_str}")
            if stderr_str:
                output_blocks.append(f"--- STDERR ---\n{stderr_str}")

            if not output_blocks:
                body = "[Success: No output produced]"
            else:
                body = "\n\n".join(output_blocks)

            truncated_body = _truncate_output(body, self.max_output)
            return f"Exit Code: {proc.returncode}\n\n{truncated_body}"

        except Exception as e:
            return f"Error executing command: {str(e)}"


class FsReadTool(NativeTool):
    name = "fs_read"
    description = (
        "Read text content of a file located within the workspace. "
        "Supports line offset and limit for paging through large files."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file (relative to workspace or absolute within workspace).",
            },
            "offset": {
                "type": "integer",
                "description": "1-based line number to start reading from. Defaults to 1.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read. Defaults to 500.",
            },
        },
        "required": ["path"],
    }

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    async def run(self, args: dict, ctx: Optional[ToolContext]) -> str:
        path = args.get("path", "")
        if not path:
            return "Error: path is required."

        try:
            safe_path = self.workspace.resolve(path)
        except PermissionError as e:
            return str(e)

        if not os.path.exists(safe_path):
            return f"Error: File not found at '{path}'"
        if os.path.isdir(safe_path):
            return f"Error: '{path}' is a directory, not a file. Use fs_list instead."

        offset = max(1, int(args.get("offset") or 1))
        limit = max(1, min(2000, int(args.get("limit") or 500)))

        try:
            lines = []
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f, start=1):
                    if idx < offset:
                        continue
                    if idx >= offset + limit:
                        lines.append(f"[... more lines exist beyond {offset + limit - 1} ...]")
                        break
                    clean = line.rstrip("\r\n")
                    lines.append(f"{idx}: {clean}")

            if not lines:
                return f"[Empty file or offset {offset} exceeds file length]"
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading file '{path}': {e}"


class FsWriteTool(NativeTool):
    name = "fs_write"
    description = (
        "Write text content to a file inside the workspace. "
        "Parent directories are created automatically if they do not exist."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file (relative to workspace or within workspace).",
            },
            "content": {
                "type": "string",
                "description": "Text content to write.",
            },
        },
        "required": ["path", "content"],
    }

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    async def run(self, args: dict, ctx: Optional[ToolContext]) -> str:
        path = args.get("path", "")
        content = args.get("content", "")
        if not path:
            return "Error: path is required."

        try:
            safe_path = self.workspace.resolve(path)
        except PermissionError as e:
            return str(e)

        if os.path.isdir(safe_path):
            return f"Error: Cannot write to '{path}' because it is an existing directory."

        try:
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            rel = self.workspace.rel(safe_path)
            return f"Success: File written to '{rel}' ({len(content)} characters)"
        except Exception as e:
            return f"Error writing file '{path}': {e}"


class FsListTool(NativeTool):
    name = "fs_list"
    description = (
        "List files and directories within a workspace directory. "
        "Shows type, size, and modified timestamp."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Subdirectory to list, relative to workspace. Defaults to '.' (root).",
            },
        },
    }

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    async def run(self, args: dict, ctx: Optional[ToolContext]) -> str:
        path = args.get("path") or "."
        try:
            safe_path = self.workspace.resolve(path)
        except PermissionError as e:
            return str(e)

        if not os.path.exists(safe_path):
            return f"Error: Path '{path}' does not exist."
        if not os.path.isdir(safe_path):
            return f"Error: '{path}' is a file, not a directory."

        try:
            entries = []
            with os.scandir(safe_path) as it:
                for entry in sorted(it, key=lambda e: (not e.is_dir(), e.name.lower())):
                    try:
                        stat = entry.stat()
                        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                        if entry.is_dir():
                            entries.append(f"[DIR]  {entry.name}/  ({mtime})")
                        else:
                            size = stat.st_size
                            size_str = (
                                f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
                            )
                            entries.append(f"[FILE] {entry.name:<25} {size_str:>10}  ({mtime})")
                    except Exception:
                        entries.append(f"[?]    {entry.name}")

            rel = self.workspace.rel(safe_path)
            header = f"Directory listing for '{rel}':\n"
            return header + ("\n".join(entries) if entries else "(empty directory)")
        except Exception as e:
            return f"Error listing directory '{path}': {e}"
