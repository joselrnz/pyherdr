from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

Runner = Callable[..., subprocess.CompletedProcess[str]]


def probe_remote(host: str, *, timeout: int = 5, runner: Runner = subprocess.run) -> dict[str, Any]:
    """Probe whether a host is reachable enough for future remote panes."""
    normalized = host.strip()
    if not normalized:
        raise ValueError("remote host is required")
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        normalized,
        "pyherdr",
        "--version",
    ]
    try:
        result = runner(command, capture_output=True, text=True, timeout=timeout + 2)
    except subprocess.TimeoutExpired as error:
        return _probe_result(normalized, command, False, f"timed out after {error.timeout}s")
    except OSError as error:
        return _probe_result(normalized, command, False, str(error))
    output = (result.stdout or result.stderr or "").strip()
    ok = result.returncode == 0
    message = output or ("ok" if ok else f"ssh exited with {result.returncode}")
    return _probe_result(normalized, command, ok, message, returncode=result.returncode)


def _probe_result(
    host: str,
    command: list[str],
    ok: bool,
    message: str,
    *,
    returncode: int | None = None,
) -> dict[str, Any]:
    return {
        "type": "remote_probe",
        "host": host,
        "ok": ok,
        "message": message,
        "returncode": returncode,
        "command": command,
    }
