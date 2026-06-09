"""Named session namespaces (ported from herdr session commands).

A session is a persistent server namespace with its own runtime dir, socket
metadata, and persisted state. The default session uses the base runtime dir;
named sessions live under ``<base>/sessions/<name>/``. Select one with the
``PYHERDR_SESSION`` environment variable (mirrors herdr's ``HERDR_SESSION``).
"""

from __future__ import annotations

import os
from pathlib import Path

from .platform_support import default_runtime_root, portable_runtime_root

DEFAULT_SESSION = "default"


def current_session() -> str:
    """Return the active session name from ``PYHERDR_SESSION`` (or default)."""
    return os.environ.get("PYHERDR_SESSION", DEFAULT_SESSION).strip() or DEFAULT_SESSION


def _runtime_base() -> Path:
    if os.environ.get("PYHERDR_PORTABLE", "1") != "0":
        return portable_runtime_root()
    return default_runtime_root()


def sessions_root() -> Path:
    """Return the directory that holds named (non-default) sessions."""
    return _runtime_base() / "sessions"


def session_runtime_dir(name: str | None = None) -> Path:
    """Return the runtime dir for a session (base dir for the default)."""
    resolved = (name or current_session()).strip() or DEFAULT_SESSION
    if resolved == DEFAULT_SESSION:
        return _runtime_base()
    return sessions_root() / resolved


def list_session_names() -> list[str]:
    """List known session names: always ``default`` plus any created sessions."""
    names = [DEFAULT_SESSION]
    root = sessions_root()
    if root.is_dir():
        names.extend(sorted(entry.name for entry in root.iterdir() if entry.is_dir()))
    return names
