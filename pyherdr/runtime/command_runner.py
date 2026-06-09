"""Legacy pipe-based command runner used by the Tkinter GUI.

This predates the PTY backend and streams a command's combined output through
plain pipes to GUI callbacks. It is retained for the desktop dashboard until the
GUI is migrated onto `TerminalSession`.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable

OutputCallback = Callable[[str], None]
ExitCallback = Callable[[int | None], None]


class CommandRunner:
    """Run one command per pane and stream its output to callbacks."""

    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen[str]] = {}

    def running(self, pane_id: str) -> bool:
        """Return whether the pane's command is still running."""
        process = self._processes.get(pane_id)
        return process is not None and process.poll() is None

    def start(
        self,
        pane_id: str,
        command: str,
        cwd: str,
        on_output: OutputCallback,
        on_exit: ExitCallback,
    ) -> bool:
        """Start a command for the pane; return ``False`` if one is running."""
        if self.running(pane_id):
            return False
        process = subprocess.Popen(
            command,
            cwd=cwd or None,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._processes[pane_id] = process
        thread = threading.Thread(
            target=self._pump_output,
            args=(pane_id, process, on_output, on_exit),
            daemon=True,
        )
        thread.start()
        return True

    def stop(self, pane_id: str) -> None:
        """Terminate the pane's command if it is running."""
        process = self._processes.get(pane_id)
        if process and process.poll() is None:
            process.terminate()

    def stop_all(self) -> None:
        """Terminate every running command."""
        for pane_id in list(self._processes):
            self.stop(pane_id)

    def _pump_output(
        self,
        pane_id: str,
        process: subprocess.Popen[str],
        on_output: OutputCallback,
        on_exit: ExitCallback,
    ) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            on_output(line)
        exit_code = process.wait()
        self._processes.pop(pane_id, None)
        on_exit(exit_code)
