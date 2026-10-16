from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from typing import Optional

from tools.workspace import Workspace

# Candidate font paths to detect on the local machine
FONT_CANDIDATES = [
    ("NanumGothic (workspace)", "fonts/NanumGothic.otf"),
    ("NanumGothicBold (workspace)", "fonts/NanumGothicBold.otf"),
    ("AppleGothic (system)", "/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
    ("AppleSDGothicNeo (system)", "/System/Library/Fonts/AppleSDGothicNeo.ttc"),
]


class VenvManager:
    """Manages the workspace-dedicated Python virtualenv."""

    def __init__(self, workspace: Workspace, default_packages: list[str]):
        self.workspace = workspace
        self.default_packages = default_packages
        self.status: str = "uninitialized"  # uninitialized | ready | installing | failed
        self.last_error: Optional[str] = None
        self._task: Optional[asyncio.Task] = None

    @property
    def venv_bin(self) -> str:
        bin_dir = "Scripts" if os.name == "nt" else "bin"
        return os.path.join(self.workspace.venv_dir, bin_dir)

    @property
    def python_exe(self) -> str:
        exe = "python.exe" if os.name == "nt" else "python"
        return os.path.join(self.venv_bin, exe)

    @property
    def pip_exe(self) -> str:
        exe = "pip.exe" if os.name == "nt" else "pip"
        return os.path.join(self.venv_bin, exe)

    def is_created(self) -> bool:
        return os.path.exists(self.python_exe)

    async def ensure_venv_background(self) -> None:
        """Starts initialization in background if not already ready."""
        if self.is_created() and self.status == "ready":
            return
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._init_venv())

    async def _init_venv(self) -> None:
        self.workspace.ensure()
        try:
            if not self.is_created():
                self.status = "installing"
                uv_path = shutil.which("uv")
                if uv_path:
                    cmd = [uv_path, "venv", self.workspace.venv_dir]
                else:
                    cmd = [sys.executable, "-m", "venv", self.workspace.venv_dir]

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError(f"venv creation failed: {stderr.decode()}")

            # Install packages if specified
            if self.default_packages:
                self.status = "installing"
                uv_path = shutil.which("uv")
                if uv_path:
                    # uv pip install into the venv
                    install_cmd = [
                        uv_path,
                        "pip",
                        "install",
                        "--python",
                        self.python_exe,
                    ] + self.default_packages
                else:
                    install_cmd = [
                        self.pip_exe,
                        "install",
                        "--quiet",
                    ] + self.default_packages

                proc = await asyncio.create_subprocess_exec(
                    *install_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError(f"package install failed: {stderr.decode()}")

            self.status = "ready"
            self.last_error = None
        except Exception as e:
            self.status = "failed"
            self.last_error = str(e)


def build_environment_guide(workspace: Workspace, venv_mgr: VenvManager) -> str:
    """
    Build a concise, fact-checked environment guide string
    to append to the system prompt when the native shell tool is enabled.
    """
    # Check fonts
    found_fonts = []
    for label, path in FONT_CANDIDATES:
        full_path = (
            os.path.join(workspace.root, path) if not os.path.isabs(path) else path
        )
        if os.path.exists(full_path):
            found_fonts.append(f"{label}: '{path}'")

    font_text = ", ".join(found_fonts) if found_fonts else "None pre-detected"
    pkgs_text = ", ".join(venv_mgr.default_packages) if venv_mgr.default_packages else "standard library"

    guide = (
        "\n\n[Workspace & Tool Guidelines]\n"
        f"- You have access to a workspace located at '{workspace.root}'.\n"
        "- All paths for shell_exec, fs_read, fs_write, and send_file must be relative to the workspace "
        "(or absolute within it). DO NOT use simulated paths like 'sandbox:/mnt/...'.\n"
        "- Subdirectories:\n"
        "  • 'uploads/': files uploaded by the user are automatically stored here.\n"
        "  • 'outputs/': place all generated deliverable files here (e.g. outputs/report.pdf).\n"
        "- Python environment:\n"
        f"  • Commands in shell_exec use the workspace dedicated Python environment with pre-installed packages: {pkgs_text}.\n"
        "  • You may run 'pip install <package>' anytime if additional libraries are needed.\n"
        f"- Korean font paths for PDF/image generation:\n"
        f"  • {font_text}\n"
        "- REPORT & DOCUMENT RULES:\n"
        "  1. [Language Fidelity]: When requested in Korean or dealing with Korean users, NEVER evade into English to avoid font issues. The entire document (titles, tables, analysis text) MUST be written in Korean using the verified Korean fonts above.\n"
        "  2. [Report Quality]: Do NOT produce bare key-value lists. A proper report MUST contain: (a) Title & Executive Summary (개요/총평), (b) Structured Data Table or Key Metrics, (c) In-depth Market Analysis & Implications (시장 분석 및 시사점).\n"
        "  3. [Korean PDF Code Snippet]:\n"
        "     • ReportLab: `from reportlab.pdfbase import pdfmetrics; from reportlab.pdfbase.ttfonts import TTFont; pdfmetrics.registerFont(TTFont('Nanum', 'fonts/NanumGothic.otf'))` then use `fontName='Nanum'` in all ParagraphStyle.\n"
        "     • FPDF2: `pdf = FPDF(); pdf.add_font('Nanum', '', 'fonts/NanumGothic.otf'); pdf.set_font('Nanum', size=11)`.\n"
        "- CRITICAL DELIVERY RULE:\n"
        "  Whenever the user asks you to create, generate, or send a file (PDF, Word docx, Excel xlsx, CSV, chart image, etc.), "
        "you MUST call the `send_file` tool with the path (e.g. `outputs/file.pdf`) to deliver it directly to the Telegram chat. "
        "Never stop at just writing the file to disk."
    )
    return guide
