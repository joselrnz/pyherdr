from __future__ import annotations

import hmac
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from socketserver import BaseRequestHandler, ThreadingTCPServer
from typing import Any

from .api import dispatch
from .config import load_config
from .cron import cron_matches
from .platform_support import hidden_process_creation_flags
from .runtime import TerminalManager
from .session import session_runtime_dir
from .store import default_state_path, load_state, save_state
from .workflow import append_event, new_event


def _configured_pane_env() -> dict[str, str]:
    """Environment variables to inject into every pane's shell (from config)."""
    try:
        env = load_config().terminal.env
    except Exception:
        return {}
    return {str(key): str(value) for key, value in env.items()}


@dataclass
class ServerInfo:
    host: str
    port: int
    pid: int
    state_path: str
    token: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "pid": self.pid,
            "state_path": self.state_path,
            "token": self.token,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ServerInfo:
        return cls(
            host=str(payload["host"]),
            port=int(payload["port"]),
            pid=int(payload["pid"]),
            state_path=str(payload["state_path"]),
            token=str(payload.get("token", "")),
        )


class PyHerdrServer(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        state_path: Path | None = None,
        token: str = "",
    ) -> None:
        super().__init__(server_address, RequestHandler)
        self.state_path = state_path or default_state_path()
        self.state = load_state(self.state_path)
        self.processes = TerminalManager(env=_configured_pane_env())
        self.lock = threading.RLock()
        self.should_stop = threading.Event()
        self.token = token


class RequestHandler(BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(10.0)
        with self.request.makefile("r", encoding="utf-8") as reader:
            raw = reader.readline()
        if not raw:
            return
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as error:
            self._write({"id": "request", "error": {"code": "invalid_json", "message": str(error)}})
            return

        if not isinstance(request, dict):
            self._write(
                {"id": "request", "error": {"code": "invalid_request", "message": "request must be a JSON object"}}
            )
            return

        server: PyHerdrServer = self.server  # type: ignore[assignment]
        request_id = str(request.get("id", "request"))

        token = str(request.pop("token", ""))
        if not hmac.compare_digest(token, server.token):
            _record_workflow_event(
                "api.unauthorized",
                message=str(request.get("method") or "request"),
                source="server",
                target=str(request.get("method") or ""),
                status="error",
                details={"id": request_id, "reason": "invalid or missing auth token"},
            )
            self._write(
                {"id": request_id, "error": {"code": "unauthorized", "message": "invalid or missing auth token"}}
            )
            return

        method = str(request.get("method") or "")
        _record_workflow_event(
            "api.request",
            message=method or "request",
            source="client",
            target=method,
            details={"id": request_id, "params": request.get("params", {})},
        )

        if request.get("method") == "server.stop":
            response = {"id": request_id, "result": {"type": "server_stop"}}
            self._write(response)
            _record_workflow_event(
                "api.response",
                message="server.stop",
                source="server",
                target="server.stop",
                status="ok",
                details={"id": request_id},
            )
            server.should_stop.set()
            threading.Thread(target=server.shutdown, daemon=True).start()
            return

        with server.lock:
            response = dispatch(server.state, request, server.processes)
            if "error" not in response and mutates_state(str(request.get("method") or "")):
                save_state(server.state, server.state_path)
        response_details: dict[str, Any] = {"id": request_id, "error": response.get("error")}
        result = response.get("result")
        if method == "pane.fanout" and isinstance(result, dict):
            response_details["result"] = {
                "dry_run": result.get("dry_run"),
                "target_count": result.get("target_count"),
                "sent": result.get("sent"),
            }
        _record_workflow_event(
            "api.response",
            message=method or "response",
            source="server",
            target=method,
            status="error" if "error" in response else "ok",
            details=response_details,
        )
        self._write(response)

    def _write(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8") + b"\n"
        self.request.sendall(encoded)


def runtime_dir() -> Path:
    override = os.environ.get("PYHERDR_RUNTIME_DIR")
    if override:
        return Path(override).expanduser()
    return session_runtime_dir()


def server_info_path() -> Path:
    return runtime_dir() / "server.json"


def server_log_path() -> Path:
    return runtime_dir() / "server.log"


def _record_workflow_event(
    kind: str,
    *,
    message: str = "",
    source: str = "",
    target: str = "",
    status: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    try:
        append_event(
            new_event(
                kind,
                message=message,
                source=source,
                target=target,
                status=status,
                details=details or {},
            ),
            max_events=2000,
        )
    except Exception:
        # Workflow logging must never break the API path.
        pass


def read_server_info(path: Path | None = None) -> ServerInfo | None:
    target = path or server_info_path()
    if not target.exists():
        return None
    try:
        return ServerInfo.from_dict(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return None


def write_server_info(info: ServerInfo, path: Path | None = None) -> Path:
    target = path or server_info_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(info.to_dict(), indent=2), encoding="utf-8")
    if os.name != "nt":
        # The file holds the auth token; restrict it to the owner on POSIX.
        try:
            target.chmod(0o600)
        except OSError:
            pass
    return target


def remove_server_info(path: Path | None = None) -> None:
    target = path or server_info_path()
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def _run_scheduler(server: PyHerdrServer) -> None:
    """Fire cron-scheduled pane commands; one tick per ~20s, deduped per minute."""
    fired: dict[str, str] = {}
    while not server.should_stop.is_set():
        now = datetime.now()
        minute_key = now.strftime("%Y%m%d%H%M")
        with server.lock:
            schedules = list(server.state.schedules)
        for schedule in schedules:
            if not schedule.enabled or fired.get(schedule.id) == minute_key:
                continue
            try:
                due = cron_matches(schedule.cron, now)
            except ValueError:
                continue
            if not due:
                continue
            fired[schedule.id] = minute_key
            text = schedule.command + ("\r" if schedule.send_enter else "")
            try:
                server.processes.send_text(schedule.pane_id, text)
            except (KeyError, OSError, RuntimeError):
                pass
        server.should_stop.wait(20)


def _run_stats_sampler(server: PyHerdrServer) -> None:
    """Sample per-pane CPU/RAM in the background so ``stats.get`` is cheap to serve.

    The slow psutil work happens here (off the request path), so the resource
    monitor stays live without holding the server lock on every poll.
    """
    while not server.should_stop.is_set():
        try:
            server.processes.sample_stats()
        except Exception:
            pass
        server.should_stop.wait(1.5)


def run_foreground(host: str = "127.0.0.1", port: int = 0) -> int:
    token = secrets.token_hex(32)
    with PyHerdrServer((host, port), token=token) as server:
        address = server.server_address
        actual_host, actual_port = address[0], address[1]
        write_server_info(
            ServerInfo(
                host=str(actual_host),
                port=int(actual_port),
                pid=os.getpid(),
                state_path=str(server.state_path),
                token=token,
            )
        )
        threading.Thread(target=_run_scheduler, args=(server,), daemon=True).start()
        threading.Thread(target=_run_stats_sampler, args=(server,), daemon=True).start()
        try:
            server.serve_forever(poll_interval=0.1)
        finally:
            server.processes.stop_all()
            save_state(server.state, server.state_path)
            remove_server_info()
    return 0


def request(info: ServerInfo, payload: dict[str, Any], timeout: float = 2.0) -> dict[str, Any]:
    message = {**payload, "token": info.token}
    with socket.create_connection((info.host, info.port), timeout=timeout) as sock:
        sock.sendall(json.dumps(message).encode("utf-8") + b"\n")
        with sock.makefile("r", encoding="utf-8") as reader:
            response = reader.readline()
    if not response:
        raise ConnectionError("server closed connection without a response")
    return json.loads(response)


def request_running(payload: dict[str, Any]) -> dict[str, Any]:
    info = read_server_info()
    if info is None:
        raise ConnectionError("pyherdr server is not running")
    return request(info, payload)


def ping(info: ServerInfo | None = None) -> bool:
    target = info or read_server_info()
    if target is None:
        return False
    try:
        response = request(target, {"id": "ping", "method": "ping", "params": {}}, timeout=0.5)
    except (OSError, ConnectionError, json.JSONDecodeError):
        return False
    return response.get("result", {}).get("type") == "pong"


def start_background(timeout: float = 5.0) -> ServerInfo:
    existing = read_server_info()
    if existing and ping(existing):
        return existing
    if existing:
        remove_server_info()

    command = [sys.executable, "-m", "pyherdr", "server", "run"]
    log_path = server_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "cwd": str(Path.cwd()),
        "stdout": log,
        "stderr": log,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = hidden_process_creation_flags()
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = read_server_info()
        if info and ping(info):
            return info
        time.sleep(0.05)
    raise TimeoutError("timed out waiting for pyherdr server to start")


def ensure_request(payload: dict[str, Any]) -> dict[str, Any]:
    info = start_background()
    return request(info, payload)


def stop_running() -> bool:
    info = read_server_info()
    if info is None:
        return False
    if not ping(info):
        remove_server_info()
        return False
    try:
        request(info, {"id": "server_stop", "method": "server.stop", "params": {}}, timeout=1.0)
        return True
    except (OSError, ConnectionError, json.JSONDecodeError):
        time.sleep(0.1)
        if not ping(info):
            remove_server_info()
            return True
        remove_server_info()
        return False


def mutates_state(method: str) -> bool:
    # Read-only methods, plus live-terminal I/O that does not change persisted
    # session state (sending input or resizing affects the PTY, not the model).
    # Excluding the latter avoids a session.json write on every forwarded key.
    return method not in {
        "ping",
        "state.get",
        "stats.get",
        "notification.show",
        "workspace.list",
        "tab.list",
        "pane.list",
        "workspace.get",
        "tab.get",
        "pane.get",
        "pane.read",
        "pane.capture",
        "worktree.list",
        "pane.send_text",
        "pane.send_key",
        "pane.resize",
        "pane.scroll",
        "pane.fanout",
        "agent.list",
        "agent.get",
        "agent.read",
        "agent.send",
        "pane.broadcast",
        "schedule.list",
        "schedule.run",
    }
