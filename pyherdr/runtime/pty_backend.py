"""Cross-platform pseudo-terminal (PTY) process backend.

POSIX uses the standard library (`os.openpty` + `subprocess`). Windows uses
ConPTY through the `pywinpty` package. Both expose the same `PtyProcess`
interface so the rest of the runtime stays platform-agnostic.

A command may be a single string (run through the platform shell on POSIX) or
an argument list (run directly).
"""

from __future__ import annotations

import os
import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

DEFAULT_ROWS = 24
DEFAULT_COLS = 80

Command = str | Sequence[str]


class PtyUnavailableError(RuntimeError):
    """Raised when no PTY backend is available for the current platform."""


class PtyProcess(ABC):
    """A process attached to a pseudo-terminal."""

    @abstractmethod
    def write(self, data: str) -> None:
        """Write input to the terminal."""

    @abstractmethod
    def read(self, size: int = 4096) -> str | None:
        """Return decoded output, ``""`` if none is ready yet, or ``None`` at EOF."""

    @abstractmethod
    def resize(self, rows: int, cols: int) -> None:
        """Set the terminal window size."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Return whether the child process is still running."""

    @abstractmethod
    def terminate(self, force: bool = False) -> None:
        """Stop the child process."""

    @property
    @abstractmethod
    def exit_status(self) -> int | None:
        """Return the child exit code, or ``None`` while it is still running."""

    @property
    @abstractmethod
    def pid(self) -> int | None:
        """Return the child process id, or ``None`` if it is not running."""


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    """Set the POSIX terminal window size via ioctl."""
    import fcntl
    import struct
    import termios

    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


class _PosixPtyProcess(PtyProcess):
    """PTY process implemented with the standard-library `pty` primitives."""

    def __init__(
        self,
        command: Command,
        cwd: str,
        env: Mapping[str, str] | None,
        rows: int,
        cols: int,
    ) -> None:
        self._master_fd, slave_fd = os.openpty()
        _set_winsize(self._master_fd, rows, cols)
        try:
            self._proc = subprocess.Popen(
                command,
                cwd=cwd or None,
                env=dict(env) if env is not None else None,
                shell=isinstance(command, str),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            os.close(slave_fd)
        self._eof = False

    def write(self, data: str) -> None:
        os.write(self._master_fd, data.encode("utf-8", "replace"))

    def read(self, size: int = 4096) -> str | None:
        if self._eof:
            return None
        try:
            data = os.read(self._master_fd, size)
        except OSError:
            self._eof = True
            return None
        if not data:
            self._eof = True
            return None
        return data.decode("utf-8", "replace")

    def resize(self, rows: int, cols: int) -> None:
        _set_winsize(self._master_fd, rows, cols)

    def is_alive(self) -> bool:
        return self._proc.poll() is None

    def terminate(self, force: bool = False) -> None:
        if self._proc.poll() is None:
            if force:
                self._proc.kill()
            else:
                self._proc.terminate()
        try:
            os.close(self._master_fd)
        except OSError:
            pass

    @property
    def exit_status(self) -> int | None:
        return self._proc.poll()

    @property
    def pid(self) -> int | None:
        return self._proc.pid


class _WindowsPtyProcess(PtyProcess):
    """PTY process implemented with ConPTY via `pywinpty`."""

    def __init__(
        self,
        command: Command,
        cwd: str,
        env: Mapping[str, str] | None,
        rows: int,
        cols: int,
    ) -> None:
        from winpty import PtyProcess as _WinPty

        # Pass a list straight through: pywinpty resolves argv[0] and quotes the
        # rest itself. Collapsing a list to a string would make it re-split with
        # shlex(posix=False), which keeps quote characters and breaks arguments.
        argv = command if isinstance(command, str) else list(command)
        self._proc = _WinPty.spawn(
            argv,
            cwd=cwd or None,
            env=dict(env) if env is not None else None,
            dimensions=(rows, cols),
        )

    def write(self, data: str) -> None:
        self._proc.write(data)

    def read(self, size: int = 4096) -> str | None:
        try:
            return self._proc.read(size)
        except EOFError:
            return None

    def resize(self, rows: int, cols: int) -> None:
        self._proc.setwinsize(rows, cols)

    def is_alive(self) -> bool:
        return bool(self._proc.isalive())

    def terminate(self, force: bool = False) -> None:
        try:
            self._proc.terminate(force=force)
        except Exception:
            pass

    @property
    def exit_status(self) -> int | None:
        return self._proc.exitstatus

    @property
    def pid(self) -> int | None:
        return getattr(self._proc, "pid", None)


def pty_available() -> bool:
    """Return whether a PTY backend can be created on this platform."""
    if os.name == "nt":
        try:
            import winpty  # noqa: F401
        except ImportError:
            return False
        return True
    return hasattr(os, "openpty")


def open_pty(
    command: Command,
    cwd: str = "",
    env: Mapping[str, str] | None = None,
    rows: int = DEFAULT_ROWS,
    cols: int = DEFAULT_COLS,
) -> PtyProcess:
    """Spawn ``command`` attached to a new pseudo-terminal."""
    if os.name == "nt":
        try:
            import winpty  # noqa: F401
        except ImportError as error:
            raise PtyUnavailableError(
                "Windows PTY support requires pywinpty. Install it with: pip install pywinpty"
            ) from error
        return _WindowsPtyProcess(command, cwd, env, rows, cols)
    if hasattr(os, "openpty"):
        return _PosixPtyProcess(command, cwd, env, rows, cols)
    raise PtyUnavailableError(f"no PTY backend available on platform {sys.platform!r}")
