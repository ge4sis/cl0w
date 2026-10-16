from __future__ import annotations

import os
from typing import Optional

from tools.base import NativeTool, ToolContext, get_tool_context
from tools.workspace import Workspace

MAX_SEND_SIZE = 50 * 1024 * 1024  # 50 MB Telegram Bot API limit


class SendFileTool(NativeTool):
    name = "send_file"
    description = (
        "Send a generated or existing file from the workspace directly to the user "
        "in the Telegram chat. Use this whenever the user asks for a report, PDF, "
        "document, chart, or any deliverable file."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to deliver (relative to workspace or within workspace).",
            },
            "caption": {
                "type": "string",
                "description": "Optional caption or summary to accompany the file in Telegram.",
            },
        },
        "required": ["path"],
    }

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    async def run(self, args: dict, ctx: Optional[ToolContext]) -> str:
        path = args.get("path", "").strip()
        if not path:
            return "Error: path is required."

        try:
            safe_path = self.workspace.resolve(path)
        except PermissionError as e:
            return str(e)

        if not os.path.exists(safe_path):
            return f"Error: File '{path}' does not exist in workspace."
        if os.path.isdir(safe_path):
            return f"Error: '{path}' is a directory. Please provide a file path."

        file_size = os.path.getsize(safe_path)
        if file_size > MAX_SEND_SIZE:
            return (
                f"Error: File '{path}' is {file_size / (1024 * 1024):.1f} MB, "
                f"which exceeds the 50 MB Telegram limit."
            )

        active_ctx = ctx or get_tool_context()
        if not active_ctx or not active_ctx.bot or not active_ctx.chat_id:
            return "Error: Cannot send file because active Telegram chat context is unavailable."

        caption = args.get("caption") or ""
        filename = os.path.basename(safe_path)

        try:
            with open(safe_path, "rb") as f:
                await active_ctx.bot.send_document(
                    chat_id=active_ctx.chat_id,
                    document=f,
                    filename=filename,
                    caption=caption[:1024] if caption else None,
                )
            rel = self.workspace.rel(safe_path)
            return f"Success: File '{rel}' ({file_size} bytes) successfully delivered to user via Telegram."
        except Exception as e:
            return f"Error sending file '{path}' to Telegram: {e}"
