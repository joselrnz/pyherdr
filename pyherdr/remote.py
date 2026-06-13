from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

from .config import ConnectionConfig

Runner = Callable[..., subprocess.CompletedProcess[str]]


def ssh_target(connection: ConnectionConfig) -> str:
    """Return user@host for an SSH connection."""
    return f"{connection.user}@{connection.host}" if connection.user else connection.host


def ssh_base_command(connection: ConnectionConfig, *, probe: bool = False) -> list[str]:
    """Build the SSH executable/options shared by profile startup and probes."""
    parts = ["ssh"]
    if connection.request_tty and not probe:
        parts.append("-t")
    if connection.port and connection.port != 22:
        parts.extend(["-p", str(connection.port)])
    if connection.key:
        parts.extend(["-i", connection.key])
    if connection.proxy_jump:
        parts.extend(["-J", connection.proxy_jump])
    if connection.batch_mode or probe:
        parts.extend(["-o", "BatchMode=yes"])
    if connection.connect_timeout:
        parts.extend(["-o", f"ConnectTimeout={connection.connect_timeout}"])
    if connection.strict_host_key_checking:
        parts.extend(["-o", f"StrictHostKeyChecking={connection.strict_host_key_checking}"])
    if connection.server_alive_interval:
        parts.extend(["-o", f"ServerAliveInterval={connection.server_alive_interval}"])
    if connection.server_alive_count_max:
        parts.extend(["-o", f"ServerAliveCountMax={connection.server_alive_count_max}"])
    parts.extend(connection.extra_args)
    return parts


def probe_connection(
    name: str,
    connection: ConnectionConfig,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Probe a configured SSH connection with its connection-level options."""
    if not connection.host:
        raise ValueError("remote host is required")
    target = ssh_target(connection)
    command = [*ssh_base_command(connection, probe=True), target, "pyherdr", "--version"]
    return _run_probe(
        connection.host,
        command,
        timeout=connection.connect_timeout,
        runner=runner,
        connection=name,
        target=target,
    )


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
    return _run_probe(normalized, command, timeout=timeout, runner=runner)


def _run_probe(
    host: str,
    command: list[str],
    *,
    timeout: int,
    runner: Runner,
    connection: str = "",
    target: str = "",
) -> dict[str, Any]:
    try:
        result = runner(command, capture_output=True, text=True, timeout=timeout + 2)
    except subprocess.TimeoutExpired as error:
        return _probe_result(
            host,
            command,
            False,
            f"timed out after {error.timeout}s",
            connection=connection,
            target=target,
        )
    except OSError as error:
        return _probe_result(host, command, False, str(error), connection=connection, target=target)
    output = (result.stdout or result.stderr or "").strip()
    ok = result.returncode == 0
    message = output or ("ok" if ok else f"ssh exited with {result.returncode}")
    return _probe_result(
        host,
        command,
        ok,
        message,
        returncode=result.returncode,
        connection=connection,
        target=target,
    )


def _probe_result(
    host: str,
    command: list[str],
    ok: bool,
    message: str,
    *,
    returncode: int | None = None,
    connection: str = "",
    target: str = "",
) -> dict[str, Any]:
    return {
        "type": "remote_probe",
        "host": host,
        "connection": connection,
        "target": target or host,
        "ok": ok,
        "message": message,
        "returncode": returncode,
        "command": command,
    }
