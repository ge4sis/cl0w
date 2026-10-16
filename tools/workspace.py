from __future__ import annotations

import os
import re
from datetime import datetime


def _safe_filename(name: str) -> str:
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    name = re.sub(r'[\x00-\x1f/:*?"<>|]', "_", name)
    name = name.lstrip(".") or "file"
    if len(name) > 150:
        stem, ext = os.path.splitext(name)
        name = stem[: 150 - len(ext)] + ext
    return name


class Workspace:
    """
    The single directory the agent is allowed to work in.

    Layout:
        uploads/  files received from Telegram
        outputs/  generated deliverables
        .home/    HOME for subprocesses (keeps caches out of the real home)
        .venv/    dedicated Python environment
    """

    def __init__(self, root: str):
        self.root = os.path.realpath(os.path.expanduser(root))
        self.uploads_dir = os.path.join(self.root, "uploads")
        self.outputs_dir = os.path.join(self.root, "outputs")
        self.home_dir = os.path.join(self.root, ".home")
        self.venv_dir = os.path.join(self.root, ".venv")

    def ensure(self) -> None:
        for d in (self.root, self.uploads_dir, self.outputs_dir, self.home_dir):
            os.makedirs(d, exist_ok=True)

    def contains(self, real_path: str) -> bool:
        return real_path == self.root or real_path.startswith(self.root + os.sep)

    def resolve(self, path: str | None) -> str:
        """
        Resolve a user/LLM supplied path (relative to the workspace or absolute)
        to a real absolute path. Symlinks are resolved before the boundary check.
        Raises PermissionError when the result is outside the workspace.
        """
        path = (path or ".").strip() or "."
        candidate = path if os.path.isabs(path) else os.path.join(self.root, path)
        real = os.path.realpath(candidate)
        if not self.contains(real):
            raise PermissionError(
                f"Access denied: '{path}' is outside the workspace ({self.root})."
            )
        return real

    def rel(self, real_path: str) -> str:
        return os.path.relpath(real_path, self.root)

    def save_upload(self, data: bytes, filename: str) -> str:
        """Save an incoming file into uploads/ and return its workspace-relative path."""
        self.ensure()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = f"{stamp}_{_safe_filename(filename)}"
        target = os.path.join(self.uploads_dir, base)
        stem, ext = os.path.splitext(target)
        n = 1
        while os.path.exists(target):
            target = f"{stem}_{n}{ext}"
            n += 1
        with open(target, "wb") as f:
            f.write(data)
        return self.rel(target)
