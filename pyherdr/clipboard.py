"""Clipboard backends used by the TUI.

The TUI still prefers Textual's clipboard integration, but this module keeps
OSC52 generation and platform fallbacks testable outside the app.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ClipboardResult:
    ok: bool
    backend: str
    error: str = ""


class ClipboardBackend(Protocol):
    name: str

    def copy(self, text: str) -> ClipboardResult:
        """Copy text and report whether the backend accepted it."""


class TextualClipboardBackend:
    name = "textual"

    def __init__(self, copier: Callable[[str], object]) -> None:
        self._copier = copier

    def copy(self, text: str) -> ClipboardResult:
        try:
            self._copier(text)
        except Exception as exc:
            return ClipboardResult(False, self.name, str(exc))
        return ClipboardResult(True, self.name)


def osc52_sequence(text: str, *, terminator: str = "\a") -> str:
    """Return an OSC52 clipboard-write sequence using the clipboard selector."""
    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return f"\x1b]52;c;{payload}{terminator}"


class Osc52ClipboardBackend:
    name = "osc52"

    def __init__(self, writer: Callable[[str], object]) -> None:
        self._writer = writer

    def copy(self, text: str) -> ClipboardResult:
        try:
            self._writer(osc52_sequence(text))
        except Exception as exc:
            return ClipboardResult(False, self.name, str(exc))
        return ClipboardResult(True, self.name)


Runner = Callable[..., subprocess.CompletedProcess[str]]


class LocalClipboardBackend:
    name = "local"

    def __init__(
        self,
        *,
        platform: str | None = None,
        which: Callable[[str], str | None] = shutil.which,
        runner: Runner = subprocess.run,
        timeout: float = 2.0,
    ) -> None:
        self._platform = platform or sys.platform
        self._which = which
        self._runner = runner
        self._timeout = timeout

    def copy(self, text: str) -> ClipboardResult:
        command = self._command()
        if command is None:
            return ClipboardResult(False, self.name, "no local clipboard command found")
        try:
            self._runner(command, input=text, text=True, capture_output=True, timeout=self._timeout, check=True)
        except Exception as exc:
            return ClipboardResult(False, self.name, str(exc))
        return ClipboardResult(True, self.name)

    def _command(self) -> Sequence[str] | None:
        if self._platform in {"nt", "win32", "cygwin"}:
            return ["clip.exe"] if self._which("clip.exe") else None
        if self._platform == "darwin":
            return ["pbcopy"] if self._which("pbcopy") else None
        for command in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
            if self._which(command[0]):
                return command
        return None


def copy_text(text: str, backends: Sequence[ClipboardBackend]) -> ClipboardResult:
    last = ClipboardResult(False, "none", "no clipboard backend configured")
    for backend in backends:
        result = backend.copy(text)
        if result.ok:
            return result
        last = result
    return last
