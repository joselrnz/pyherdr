"""Runtime layer: PTY-backed terminal processes, screen state, and input.

This package replaces Herdr's Rust `pane` / `terminal` / `ghostty` stack with a
Python equivalent: a real pseudo-terminal per pane (stdlib `pty` on POSIX,
ConPTY via `pywinpty` on Windows), a `pyte`-backed screen model with scrollback,
and a key-encoding table for interactive input.
"""

from . import keys
from .command_runner import CommandRunner
from .pty_backend import (
    DEFAULT_COLS,
    DEFAULT_ROWS,
    PtyProcess,
    PtyUnavailableError,
    open_pty,
    pty_available,
)
from .screen import TerminalScreen
from .session import TerminalManager, TerminalSession

__all__ = [
    "DEFAULT_COLS",
    "DEFAULT_ROWS",
    "CommandRunner",
    "PtyProcess",
    "PtyUnavailableError",
    "TerminalManager",
    "TerminalScreen",
    "TerminalSession",
    "keys",
    "open_pty",
    "pty_available",
]
