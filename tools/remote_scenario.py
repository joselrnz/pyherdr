"""Run a deterministic PyHerdr remote workspace scenario.

Usage:
    python -m tools.remote_scenario --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from pyherdr.api import dispatch
from pyherdr.config import (
    Config,
    ConnectionConfig,
    ProfileConfig,
    ProfilePaneConfig,
    WorkflowConfig,
    WorkflowStepConfig,
)
from pyherdr.models import AppState
from pyherdr.remote import probe_connection
from pyherdr.startup_profiles import plan_profile, validate_startup_config
from pyherdr.store import load_state, save_state

DEFAULT_CONNECTION = "walter"
DEFAULT_HOST = "150"
DEFAULT_REMOTE_CWD = "/srv/pyherdr"


def run_remote_scenario(
    work_dir: Path,
    *,
    connection_name: str = DEFAULT_CONNECTION,
    host: str = DEFAULT_HOST,
    live_probe: bool = False,
) -> dict[str, Any]:
    """Exercise remote probe, profile planning, pane metadata, and restore."""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    steps = ["workspace_created"]

    config = _scenario_config(connection_name, host)
    validation = validate_startup_config(config, profile_name="walter-ops")
    if not validation.ok:
        raise RuntimeError("; ".join(validation.errors))
    steps.append("config_validated")

    plan = plan_profile(config, "walter-ops", workflow_name="health")
    remote_connections = plan["remote_connections"]
    if not remote_connections:
        raise RuntimeError("remote profile did not expose probe metadata")
    steps.append("profile_planned")

    probe = (
        probe_connection(connection_name, config.connections[connection_name])
        if live_probe
        else probe_connection(connection_name, config.connections[connection_name], runner=_fake_probe_runner)
    )
    if not probe["ok"]:
        raise RuntimeError(f"remote probe failed: {probe['message']}")
    steps.append("remote_probed")

    state = AppState.bootstrap(str(work_dir))
    workspace = state.focused_workspace
    if workspace is None or workspace.focused_tab is None:
        raise RuntimeError("failed to bootstrap workspace")
    workspace.label = "walter remote"
    tab = workspace.focused_tab
    tab.label = "remote"
    pane = tab.focused_pane
    if pane is None:
        raise RuntimeError("failed to bootstrap pane")
    remote_pane = plan["panes"][0]
    pane.title = "walter shell"
    pane.command = remote_pane["command"]
    pane.remote_host = host
    pane.remote_cwd = DEFAULT_REMOTE_CWD
    pane.append_output("remote shell ready")
    pane_record = _pane_record(state, pane.id)
    if pane_record["location"] != "remote":
        raise RuntimeError("pane metadata did not mark remote location")
    steps.append("remote_pane_created")

    state_file = save_state(state, work_dir / "remote-session.json")
    restored = load_state(state_file)
    restored_pane = restored.require_pane(pane.id)
    restored_record = _pane_record(restored, restored_pane.id)
    if restored_record["remote_host"] != host:
        raise RuntimeError("remote metadata was not restored")
    steps.append("remote_metadata_restored")

    return {
        "result": "ok",
        "steps": steps,
        "connection": {
            "name": connection_name,
            "host": host,
            "target": probe["target"],
            "remote_cwd": DEFAULT_REMOTE_CWD,
        },
        "validation": validation.to_dict(),
        "profile": {
            "name": plan["profile"],
            "workspace": plan["workspace"],
            "layout": plan["layout"],
            "start_sequence": plan["start_sequence"],
            "remote_connections": remote_connections,
            "workflow": plan["workflow"],
        },
        "probe": {
            "ok": probe["ok"],
            "host": probe["host"],
            "target": probe["target"],
            "message": probe["message"],
            "command": probe["command"],
        },
        "pane": pane_record,
        "restored": restored_record,
        "state_file": str(state_file),
        "live_probe": live_probe,
    }


def default_work_dir() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(".artifacts") / "remote-scenario" / f"{stamp}-{os.getpid()}"


def _scenario_config(connection_name: str, host: str) -> Config:
    connection = ConnectionConfig(
        host=host,
        connect_timeout=8,
        batch_mode=True,
        strict_host_key_checking="accept-new",
        server_alive_interval=30,
        server_alive_count_max=2,
        request_tty=True,
        remote_cwd=DEFAULT_REMOTE_CWD,
    )
    return Config(
        connections={connection_name: connection},
        profiles={
            "walter-ops": ProfileConfig(
                workspace="walter",
                layout="main-left",
                panes=[
                    ProfilePaneConfig(
                        name="walter-shell",
                        connection=connection_name,
                        command="uname -a",
                        position="left",
                        start_order=10,
                    ),
                    ProfilePaneConfig(name="local-control", command="pwsh", position="right-top", start_order=20),
                    ProfilePaneConfig(name="notes", command="python -m pyherdr status", position="right-bottom"),
                ],
            )
        },
        workflows={
            "health": WorkflowConfig(
                profile="walter-ops",
                steps=[WorkflowStepConfig(pane="walter-shell", send="pyherdr --version")],
            )
        },
    )


def _fake_probe_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, "pyherdr 0.0.4", "")


def _pane_record(state: AppState, pane_id: str) -> dict[str, Any]:
    response = dispatch(state, {"id": "pane", "method": "pane.get", "params": {"pane_id": pane_id}})
    error = response.get("error")
    if error:
        raise RuntimeError(str(error.get("message") or error))
    result = response.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("pane"), dict):
        raise RuntimeError(f"unexpected pane response: {response}")
    return result["pane"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PyHerdr remote workspace scenario")
    parser.add_argument("--work-dir", type=Path, default=default_work_dir(), help="directory for scenario artifacts")
    parser.add_argument("--connection", default=DEFAULT_CONNECTION, help="connection alias to model")
    parser.add_argument("--host", default=DEFAULT_HOST, help="remote hostname or SSH config alias")
    parser.add_argument(
        "--live-probe",
        action="store_true",
        help="run a real SSH probe instead of the deterministic fake",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable scenario report")
    args = parser.parse_args(argv)

    report = run_remote_scenario(
        args.work_dir,
        connection_name=args.connection,
        host=args.host,
        live_probe=args.live_probe,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"remote scenario: {report['result']}")
        print(f"connection: {report['connection']['name']} -> {report['connection']['host']}")
        print(f"pane: {report['pane']['display_cwd']}")
        print(f"state: {report['state_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
