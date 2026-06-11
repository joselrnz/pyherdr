"""Persistent PTY-backed terminal sessions and a manager keyed by pane id.

`TerminalManager` exposes the process-manager interface the server's `pane.*`
handlers expect, but each session is backed by a real pseudo-terminal and a
`pyte` screen with scrollback.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

from . import keys
from .procstats import ProcSampler
from .pty_backend import DEFAULT_COLS, DEFAULT_ROWS, Command, PtyProcess, open_pty
from .screen import TerminalScreen


class TerminalSession:
    """One pane's pseudo-terminal: process, screen state, and reader thread."""

    def __init__(
        self,
        pane_id: str,
        command: Command,
        cwd: str = "",
        *,
        rows: int = DEFAULT_ROWS,
        cols: int = DEFAULT_COLS,
        env: dict[str, str] | None = None,
        on_output: Callable[[str, int], None] | None = None,
    ) -> None:
        self.pane_id = pane_id
        self.command = command
        self.cwd = cwd
        self._rows = rows
        self._cols = cols
        self._env = env
        self._screen = TerminalScreen(rows, cols)
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._pty: PtyProcess | None = None
        self._reader: threading.Thread | None = None
        self._generation = 0
        self._on_output = on_output

    def start(self) -> None:
        """Spawn the PTY process and begin reading its output."""
        with self._lock:
            if self._pty is not None:
                raise RuntimeError(f"session already started: {self.pane_id}")
            self._pty = open_pty(self.command, self.cwd, self._env, self._rows, self._cols)
        self._reader = threading.Thread(target=self._pump, name=f"pty-{self.pane_id}", daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        pty = self._pty
        assert pty is not None
        while True:
            chunk = pty.read(4096)
            if chunk is None:
                self._mark_changed()
                break
            if chunk:
                with self._lock:
                    self._screen.feed(chunk)
                    generation = self._mark_changed_locked()
                self._notify_manager(generation)
            else:
                time.sleep(0.01)

    def send_text(self, text: str) -> None:
        """Type text into the terminal.

        Newlines are sent as carriage returns so lines submit like pressing
        Enter on every platform: Windows ConPTY requires ``\\r``, and POSIX
        terminals map ``\\r`` to newline via ``ICRNL``.
        """
        normalized = text.replace("\r\n", "\r").replace("\n", "\r")
        self._require().write(keys.encode_text(normalized))

    def send_key(self, name: str) -> None:
        """Send a named key (e.g. ``"enter"``, ``"up"``)."""
        self._require().write(keys.encode_key(name))

    def send_ctrl(self, letter: str) -> None:
        """Send a control chord (e.g. ``"c"`` for Ctrl+C)."""
        self._require().write(keys.encode_ctrl(letter))

    def resize(self, rows: int, cols: int) -> None:
        """Resize both the PTY and the screen model."""
        with self._lock:
            self._rows = rows
            self._cols = cols
            self._screen.resize(rows, cols)
            generation = self._mark_changed_locked()
            if self._pty is not None:
                self._pty.resize(rows, cols)
        self._notify_manager(generation)

    def read(self, lines: int | None = None) -> str:
        """Return the rendered screen plus scrollback as text."""
        with self._lock:
            return "\n".join(self._screen.snapshot(lines))

    def render_styled(self, cursor: bool = False) -> str:
        """Return the visible screen as ANSI-styled lines (cursor cell reversed)."""
        with self._lock:
            return self._screen.render_styled(cursor=cursor)

    def scroll(self, direction: str) -> None:
        """Scroll this session's screen through scrollback."""
        with self._lock:
            self._screen.scroll(direction)
            generation = self._mark_changed_locked()
        self._notify_manager(generation)

    @property
    def generation(self) -> int:
        """Return the current output generation for event-driven refresh."""
        with self._lock:
            return self._generation

    def wait_for_change(self, after: int, timeout: float) -> int:
        """Block until this session's output generation differs from ``after``."""
        deadline = time.monotonic() + max(0.0, timeout)
        with self._changed:
            while self._generation == after:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._changed.wait(remaining)
            return self._generation

    def is_alive(self) -> bool:
        """Return whether the PTY process is still running."""
        return self._pty is not None and self._pty.is_alive()

    @property
    def pid(self) -> int | None:
        """Return the PTY child's process id, or ``None`` if not started."""
        with self._lock:
            return self._pty.pid if self._pty is not None else None

    def stop(self, timeout: float = 2.0) -> None:
        """Terminate the PTY process and stop the reader thread."""
        with self._lock:
            pty = self._pty
        if pty is None:
            return
        pty.terminate()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and pty.is_alive():
            time.sleep(0.02)
        if pty.is_alive():
            pty.terminate(force=True)
        if self._reader is not None:
            self._reader.join(timeout=1.0)

    def _require(self) -> PtyProcess:
        if self._pty is None:
            raise RuntimeError(f"session not started: {self.pane_id}")
        return self._pty

    def _mark_changed(self) -> None:
        with self._lock:
            generation = self._mark_changed_locked()
        self._notify_manager(generation)

    def _mark_changed_locked(self) -> int:
        self._generation += 1
        self._changed.notify_all()
        return self._generation

    def _notify_manager(self, generation: int) -> None:
        if self._on_output is not None:
            self._on_output(self.pane_id, generation)


class TerminalManager:
    """Owns `TerminalSession` instances keyed by pane id."""

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._versions: dict[str, int] = {}
        # Extra environment variables injected into every pane's shell (config).
        self._env = dict(env) if env else {}
        # CPU/RAM sampler for the per-pane resource monitor.
        self._sampler = ProcSampler()

    def start(
        self,
        pane_id: str,
        command: Command,
        cwd: str = "",
        *,
        rows: int = DEFAULT_ROWS,
        cols: int = DEFAULT_COLS,
    ) -> bool:
        """Start a session for ``pane_id``; return ``False`` if one is already running."""
        with self._lock:
            existing = self._sessions.get(pane_id)
            if existing is not None and existing.is_alive():
                return False
            # Merge configured env over the inherited environment (None = inherit).
            env = {**os.environ, **self._env} if self._env else None
            session = TerminalSession(
                pane_id,
                command,
                cwd,
                rows=rows,
                cols=cols,
                env=env,
                on_output=self._notify_output,
            )
            self._sessions[pane_id] = session
            self._versions[pane_id] = session.generation
        try:
            session.start()
        except Exception:
            with self._lock:
                self._sessions.pop(pane_id, None)
                self._versions.pop(pane_id, None)
            raise
        with self._changed:
            self._versions[pane_id] = session.generation
            self._changed.notify_all()
            return True

    def running(self, pane_id: str) -> bool:
        """Return whether a live session exists for ``pane_id``."""
        session = self._sessions.get(pane_id)
        return session is not None and session.is_alive()

    def send_text(self, pane_id: str, text: str) -> None:
        """Type text into a pane's terminal."""
        self._require(pane_id).send_text(text)

    def send_key(self, pane_id: str, name: str) -> None:
        """Send a named key to a pane's terminal."""
        self._require(pane_id).send_key(name)

    def resize(self, pane_id: str, rows: int, cols: int) -> None:
        """Resize a pane's terminal."""
        self._require(pane_id).resize(rows, cols)

    def read(self, pane_id: str, lines: int | None = None) -> str:
        """Read rendered output (with scrollback) from a pane's terminal."""
        return self._require(pane_id).read(lines)

    def output_versions(self, pane_ids: list[str]) -> dict[str, int]:
        """Return current output generations for live sessions in ``pane_ids``."""
        with self._lock:
            return {
                pane_id: session.generation
                for pane_id in pane_ids
                if (session := self._sessions.get(pane_id)) is not None
            }

    def wait_for_output(self, versions: dict[str, int], timeout: float = 1.0) -> dict[str, Any]:
        """Wait until any watched pane's output generation changes."""
        timeout = max(0.0, min(float(timeout), 30.0))
        pane_ids = list(versions)
        deadline = time.monotonic() + timeout
        with self._changed:
            while True:
                current = {pane_id: self._versions[pane_id] for pane_id in pane_ids if pane_id in self._versions}
                changed = {
                    pane_id: generation
                    for pane_id, generation in current.items()
                    if generation != versions.get(pane_id, -1)
                }
                if changed:
                    return {"changed": changed, "versions": current, "timed_out": False}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"changed": {}, "versions": current, "timed_out": True}
                self._changed.wait(remaining)

    def render_styled(self, pane_id: str, cursor: bool = False) -> str:
        """Return a pane's visible screen as ANSI-styled lines."""
        return self._require(pane_id).render_styled(cursor=cursor)

    def scroll(self, pane_id: str, direction: str) -> None:
        """Scroll a pane's screen through scrollback."""
        self._require(pane_id).scroll(direction)

    def stop(self, pane_id: str) -> bool:
        """Stop a pane's terminal; return ``False`` if there was none."""
        with self._lock:
            session = self._sessions.get(pane_id)
            if session is None:
                return False
        session.stop()
        with self._changed:
            self._versions[pane_id] = session.generation
            self._changed.notify_all()
        return True

    def stop_all(self) -> None:
        """Stop every managed session."""
        for pane_id in list(self._sessions):
            self.stop(pane_id)

    def running_pane_ids(self) -> list[str]:
        """Return the ids of panes with a live session."""
        return [pane_id for pane_id, session in self._sessions.items() if session.is_alive()]

    def pane_pids(self) -> dict[str, int]:
        """Return ``{pane_id: pid}`` for panes with a live process."""
        result: dict[str, int] = {}
        with self._lock:
            for pane_id, session in self._sessions.items():
                if not session.is_alive():
                    continue
                pid = session.pid
                if pid is not None:
                    result[pane_id] = pid
        return result

    def sample_stats(self) -> None:
        """Refresh cached CPU/RAM stats for every live pane (called periodically)."""
        self._sampler.sample(self.pane_pids())

    def stats_snapshot(self) -> dict[str, dict[str, Any]]:
        """Return the most recent per-pane resource snapshot (CPU%/RSS/process list)."""
        return self._sampler.snapshot()

    def broadcast(self, pane_ids: list[str], text: str) -> int:
        """Send text to each given pane with a live session; return how many got it."""
        sent = 0
        for pane_id in pane_ids:
            session = self._sessions.get(pane_id)
            if session is not None and session.is_alive():
                session.send_text(text)
                sent += 1
        return sent

    def _require(self, pane_id: str) -> TerminalSession:
        session = self._sessions.get(pane_id)
        if session is None:
            raise KeyError(f"terminal session not found: {pane_id}")
        return session

    def _notify_output(self, pane_id: str, generation: int) -> None:
        with self._changed:
            self._versions[pane_id] = generation
            self._changed.notify_all()
