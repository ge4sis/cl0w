import asyncio
import os
import shutil
import tempfile
import unittest

from tools.base import NativeTool, ToolContext, get_tool_context, set_tool_context, reset_tool_context
from tools.workspace import Workspace
from tools.sandbox import (
    build_env,
    check_blocked,
    default_deny_read_paths,
    sandbox_available,
)
from tools.shell import FsListTool, FsReadTool, FsWriteTool, ShellExecTool
from tools.delivery import SendFileTool
from tools.registry import ToolRegistry


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cl0w_test_ws_")
        self.ws = Workspace(self.tmp)
        self.ws.ensure()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_containment_and_resolve(self):
        safe = self.ws.resolve("sub/file.txt")
        self.assertTrue(safe.startswith(self.ws.root))

        # Traversal attempt must raise PermissionError
        with self.assertRaises(PermissionError):
            self.ws.resolve("../outside.txt")

        # Symlink escape attempt must raise PermissionError
        outside_target = tempfile.gettempdir()
        symlink_path = os.path.join(self.ws.root, "bad_link")
        try:
            os.symlink(outside_target, symlink_path)
            with self.assertRaises(PermissionError):
                self.ws.resolve("bad_link/evil.txt")
        except OSError:
            pass

    def test_save_upload(self):
        data = b"hello test file"
        rel = self.ws.save_upload(data, "test.txt")
        self.assertTrue(rel.startswith("uploads/"))
        full = os.path.join(self.ws.root, rel)
        self.assertTrue(os.path.exists(full))
        with open(full, "rb") as f:
            self.assertEqual(f.read(), data)


class TestSandbox(unittest.TestCase):
    def test_check_blocked(self):
        self.assertEqual(check_blocked("sudo rm -rf /"), "sudo")
        self.assertEqual(check_blocked("echo hello && shutdown -r now"), "shutdown")
        self.assertEqual(check_blocked("FOO=1 osascript -e 'beep'"), "osascript")
        self.assertIsNone(check_blocked("python script.py --arg sudo_name"))
        self.assertIsNone(check_blocked("ls -la"))

    def test_build_env_scrubs_secrets(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "secret_tg_token"
        os.environ["LM_STUDIO_API_KEY"] = "secret_lm_key"
        os.environ["OPENAI_API_KEY"] = "secret_openai_key"

        env = build_env(workspace_root="/tmp/ws", home_dir="/tmp/ws/.home", venv_dir="/tmp/ws/.venv")
        self.assertNotIn("TELEGRAM_BOT_TOKEN", env)
        self.assertNotIn("LM_STUDIO_API_KEY", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual(env["HOME"], "/tmp/ws/.home")
        self.assertTrue(env["PATH"].startswith("/tmp/ws/.venv/bin"))


class TestShellAndFilesystemTools(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cl0w_test_tools_")
        self.ws = Workspace(self.tmp)
        self.ws.ensure()

    async def asyncTearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_fs_write_read_list(self):
        writer = FsWriteTool(self.ws)
        reader = FsReadTool(self.ws)
        lister = FsListTool(self.ws)

        # Write
        res_write = await writer.run({"path": "notes/todo.txt", "content": "Line 1\nLine 2\nLine 3"}, None)
        self.assertIn("Success", res_write)

        # Read
        res_read = await reader.run({"path": "notes/todo.txt", "offset": 2, "limit": 2}, None)
        self.assertIn("2: Line 2", res_read)
        self.assertIn("3: Line 3", res_read)
        self.assertNotIn("1: Line 1", res_read)

        # List
        res_list = await lister.run({"path": "notes"}, None)
        self.assertIn("todo.txt", res_list)

    async def test_shell_exec_and_sandbox(self):
        tool = ShellExecTool(
            workspace=self.ws,
            default_timeout=15,
            use_sandbox=True,
            extra_deny_read=[os.path.join(self.tmp, "deny_this.txt")],
        )

        # Basic command
        res = await tool.run({"command": "echo 'cl0w native shell test'"}, None)
        self.assertIn("Exit Code: 0", res)
        self.assertIn("cl0w native shell test", res)

        # File creation inside workspace succeeds
        res = await tool.run({"command": "echo 'created by shell' > inside.txt && cat inside.txt"}, None)
        self.assertIn("Exit Code: 0", res)
        self.assertIn("created by shell", res)

        # File write outside workspace should be blocked by Seatbelt on macOS
        if sandbox_available():
            forbidden_target = os.path.expanduser("~/cl0w_test_forbidden_should_fail")
            res_fail = await tool.run({"command": f"touch '{forbidden_target}'"}, None)
            self.assertNotEqual(res_fail.split("\n")[0], "Exit Code: 0")
            self.assertFalse(os.path.exists(forbidden_target))

    async def test_shell_exec_timeout(self):
        tool = ShellExecTool(workspace=self.ws, default_timeout=2, use_sandbox=False)
        res = await tool.run({"command": "sleep 10"}, None)
        self.assertIn("timed out after 2 seconds", res)


class DummyBot:
    def __init__(self):
        self.sent_documents = []

    async def send_document(self, chat_id, document, filename=None, caption=None):
        self.sent_documents.append({
            "chat_id": chat_id,
            "data": document.read(),
            "filename": filename,
            "caption": caption,
        })


class TestDeliveryTool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cl0w_test_deliv_")
        self.ws = Workspace(self.tmp)
        self.ws.ensure()

    async def asyncTearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_send_file(self):
        # Create a report file in outputs/
        report_path = os.path.join(self.ws.outputs_dir, "report.pdf")
        with open(report_path, "wb") as f:
            f.write(b"%PDF-1.4 dummy pdf content")

        tool = SendFileTool(self.ws)
        bot = DummyBot()
        ctx = ToolContext(bot=bot, chat_id=123456789)

        # Missing path
        err = await tool.run({}, ctx)
        self.assertIn("path is required", err)

        # Path outside workspace
        err = await tool.run({"path": "/etc/passwd"}, ctx)
        self.assertIn("outside the workspace", err)

        # Success send
        res = await tool.run({"path": "outputs/report.pdf", "caption": "Here is your report"}, ctx)
        self.assertIn("Success", res)
        self.assertEqual(len(bot.sent_documents), 1)
        self.assertEqual(bot.sent_documents[0]["chat_id"], 123456789)
        self.assertEqual(bot.sent_documents[0]["filename"], "report.pdf")
        self.assertEqual(bot.sent_documents[0]["caption"], "Here is your report")


class TestToolRegistry(unittest.IsolatedAsyncioTestCase):
    async def test_native_takes_precedence(self):
        registry = ToolRegistry()

        class DummyNative(NativeTool):
            name = "my_tool"
            description = "Native version"
            parameters = {"type": "object"}
            async def run(self, args, ctx):
                return "native_output"

        registry.register_native_tool(DummyNative())

        # Mock MCP Manager
        class DummyMCPManager:
            def get_all_openai_tools(self):
                return [
                    {"type": "function", "function": {"name": "my_tool", "description": "MCP version"}},
                    {"type": "function", "function": {"name": "other_mcp", "description": "Other"}},
                ]
            async def execute_tool_call(self, name, args):
                return "mcp_output"
            def get_status(self):
                return []

        registry.set_mcp_manager(DummyMCPManager())

        tools = registry.get_all_openai_tools()
        names = [t["function"]["name"] for t in tools]
        self.assertIn("my_tool", names)
        self.assertIn("other_mcp", names)
        # Should only have 1 instance of 'my_tool'
        self.assertEqual(names.count("my_tool"), 1)

        # Execution of 'my_tool' must invoke native tool
        out = await registry.execute_tool_call("my_tool", {})
        self.assertEqual(out, "native_output")

        # Execution of 'other_mcp' delegates to MCP
        out = await registry.execute_tool_call("other_mcp", {})
        self.assertEqual(out, "mcp_output")


if __name__ == "__main__":
    unittest.main()
