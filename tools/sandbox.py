"""
Sandboxing for shell commands.

On macOS we wrap commands with Seatbelt (`sandbox-exec`):
  * writes are allowed only inside the workspace and temp dirs
  * reads of credential / private paths are denied
  * system-altering binaries cannot be executed
  * signals can only target processes inside the same sandbox
    (so commands cannot kill the bot or other apps)
Network access is left open on purpose (pip install, downloads, APIs).

On other platforms only the textual blocklist and env scrubbing apply.
"""
from __future__ import annotations

import os
import re
import shlex
import sys
from typing import Iterable, Optional

SANDBOX_EXEC = "/usr/bin/sandbox-exec"

# Binaries that change system state, escalate privileges, or escape the sandbox
# through system daemons (LaunchServices, cfprefsd, securityd, ...).
BLOCKED_BINARIES = {
    "sudo": ["/usr/bin/sudo"],
    "su": ["/usr/bin/su"],
    "doas": [],
    "login": ["/usr/bin/login"],
    "osascript": ["/usr/bin/osascript"],
    "open": ["/usr/bin/open"],
    "launchctl": ["/bin/launchctl"],
    "shutdown": ["/sbin/shutdown"],
    "reboot": ["/sbin/reboot"],
    "halt": ["/sbin/halt"],
    "diskutil": ["/usr/sbin/diskutil"],
    "csrutil": ["/usr/bin/csrutil"],
    "nvram": ["/usr/sbin/nvram"],
    "systemsetup": ["/usr/sbin/systemsetup"],
    "networksetup": ["/usr/sbin/networksetup"],
    "pmset": ["/usr/bin/pmset"],
    "defaults": ["/usr/bin/defaults"],
    "security": ["/usr/bin/security"],
    "tccutil": ["/usr/bin/tccutil"],
    "softwareupdate": ["/usr/sbin/softwareupdate"],
    "crontab": ["/usr/bin/crontab"],
    "at": ["/usr/bin/at"],
    "screencapture": ["/usr/sbin/screencapture"],
    "shortcuts": ["/usr/bin/shortcuts"],
    "automator": ["/usr/bin/automator"],
}

# Paths (relative to the real home) whose contents must never be readable.
SENSITIVE_HOME_PATHS = [
    ".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker", ".config",
    ".netrc", ".npmrc", ".pypirc", ".git-credentials",
    ".zsh_history", ".bash_history", ".python_history",
    ".gemini", ".claude", ".codex", ".cursor",
    "Library/Keychains", "Library/Cookies", "Library/Mail", "Library/Messages",
    "Library/Safari",
    "Library/Application Support/Google/Chrome",
    "Library/Application Support/Firefox",
    "Library/Application Support/BraveSoftware",
    "Library/Application Support/Microsoft Edge",
    "Library/Application Support/Arc",
    "Library/Application Support/Claude",
]

# Environment variables passed through to subprocesses. Everything else
# (TELEGRAM_BOT_TOKEN, API keys, ...) is dropped.
ENV_ALLOWLIST = ("LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "USER", "LOGNAME", "TZ")

_SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|&\n`(){}]|\$\(")
_PREFIX_WORDS = {"nohup", "time", "exec", "command", "builtin", "env", "nice",
                 "xargs", "then", "do", "else", "!", "if", "while", "until"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def sandbox_available() -> bool:
    return sys.platform == "darwin" and os.path.exists(SANDBOX_EXEC)


def check_blocked(command: str) -> Optional[str]:
    """
    Best-effort detection of blocked binaries at command position.
    Returns the offending binary name, or None. (The Seatbelt profile is the
    real enforcement on macOS; this mainly yields a clearer error message.)
    """
    for segment in _SEGMENT_SPLIT.split(command or ""):
        try:
            words = shlex.split(segment, posix=True)
        except ValueError:
            words = segment.split()
        i = 0
        while i < len(words):
            w = words[i]
            if w in _PREFIX_WORDS or _ASSIGNMENT.match(w) or (i > 0 and w.startswith("-")):
                i += 1
                continue
            break
        if i < len(words):
            base = os.path.basename(words[i])
            if base in BLOCKED_BINARIES:
                return base
    return None


def _sb_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _temp_root() -> str:
    tmp = os.environ.get("TMPDIR") or "/tmp"
    real = os.path.realpath(tmp)
    # macOS per-user temp lives in /private/var/folders/xx/yyy/T — allow the
    # whole per-user folder (T = temp, C = caches).
    if real.startswith("/private/var/folders/"):
        return os.path.dirname(real.rstrip("/"))
    return real


def default_deny_read_paths(extra: Iterable[str] = ()) -> list[str]:
    home = os.path.expanduser("~")
    paths = [os.path.join(home, p) for p in SENSITIVE_HOME_PATHS]
    paths.extend(extra)
    return [os.path.realpath(p) for p in paths]


def build_profile(workspace_root: str, deny_read: Iterable[str]) -> tuple[str, dict]:
    """Return (profile_text, params) for sandbox-exec."""
    deny_read_rules = "\n".join(f"  (subpath {_sb_str(p)})" for p in deny_read)
    deny_exec_rules = "\n".join(
        f"  (literal {_sb_str(p)})"
        for paths in BLOCKED_BINARIES.values() for p in paths
    )
    profile = f"""(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath (param "WS"))
  (subpath (param "TMP"))
  (subpath "/private/tmp")
  (literal "/dev/null") (literal "/dev/zero") (literal "/dev/tty")
  (regex #"^/dev/fd/") (regex #"^/dev/ttys"))
(deny file-read*
{deny_read_rules})
(deny process-exec
{deny_exec_rules})
(deny signal)
(allow signal (target same-sandbox))
"""
    params = {"WS": os.path.realpath(workspace_root), "TMP": _temp_root()}
    return profile, params


def wrap_command(argv: list[str], profile: str, params: dict) -> list[str]:
    wrapped = [SANDBOX_EXEC]
    for k, v in params.items():
        wrapped += ["-D", f"{k}={v}"]
    wrapped += ["-p", profile]
    return wrapped + argv


def build_env(workspace_root: str, home_dir: str, venv_dir: Optional[str]) -> dict:
    """Scrubbed environment for subprocesses."""
    src = os.environ
    env = {k: src[k] for k in ENV_ALLOWLIST if k in src}
    env.setdefault("LANG", "en_US.UTF-8")

    # Drop cl0w's own virtualenv from PATH so `python` never points at it.
    own_bins = {os.path.realpath(os.path.join(sys.prefix, d)) for d in ("bin", "Scripts")}
    path_entries = [
        p for p in src.get("PATH", os.defpath).split(os.pathsep)
        if p and os.path.realpath(p) not in own_bins
    ]
    if venv_dir:
        bin_dir = os.path.join(venv_dir, "Scripts" if os.name == "nt" else "bin")
        path_entries.insert(0, bin_dir)
        env["VIRTUAL_ENV"] = venv_dir
    env["PATH"] = os.pathsep.join(path_entries)

    env["HOME"] = home_dir
    env["XDG_CACHE_HOME"] = os.path.join(home_dir, ".cache")
    env["XDG_CONFIG_HOME"] = os.path.join(home_dir, ".config")
    env["MPLCONFIGDIR"] = os.path.join(home_dir, ".matplotlib")
    env["MPLBACKEND"] = "Agg"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["CL0W_WORKSPACE"] = workspace_root
    if os.name == "nt":
        for k in ("SYSTEMROOT", "COMSPEC", "PATHEXT", "WINDIR", "TEMP", "TMP"):
            if k in src:
                env[k] = src[k]
    return env
