from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

APP_NAME = "PyHerdr"
APP_SLUG = "pyherdr"


def default_runtime_root(
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    env = environ or os.environ
    override = env.get("PYHERDR_RUNTIME_DIR")
    if override:
        return Path(override).expanduser()

    current_platform = platform_name or sys.platform
    user_home = home or Path.home()

    if current_platform.startswith("win"):
        base = env.get("LOCALAPPDATA") or env.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return user_home / "AppData" / "Local" / APP_NAME

    if current_platform == "darwin":
        return user_home / "Library" / "Application Support" / APP_NAME

    xdg_state_home = env.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home) / APP_SLUG
    return user_home / ".local" / "state" / APP_SLUG


def portable_runtime_root(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / ".pyherdr"


def hidden_process_creation_flags(os_name: str | None = None) -> int:
    current_os = os_name or os.name
    if current_os != "nt":
        return 0
    subprocess = __import__("subprocess")
    # CREATE_NO_WINDOW gives the background server its own *hidden* console.
    # We deliberately do NOT use DETACHED_PROCESS: a console-less process that
    # later allocates a ConPTY (for a pane shell) triggers Windows 11's
    # default-terminal handoff, which opens a stray Windows Terminal window.
    # A hidden console avoids that handoff entirely. CREATE_NEW_PROCESS_GROUP
    # isolates the server from the parent console's Ctrl+C.
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
