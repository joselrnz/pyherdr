"""Run a deterministic PyHerdr recovery scenario.

Usage:
    python -m tools.recovery_scenario --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from pyherdr.api import dispatch
from pyherdr.models import AppState
from pyherdr.store import load_state, save_state

CRASH_MARKER = "PYHERDR_RECOVERY_CRASH"
RECOVERY_MARKER = "PYHERDR_RECOVERY_OK"


def run_recovery_scenario(work_dir: Path) -> dict[str, Any]:
    """Exercise pane failure, state reload, attach-style read, and recovery."""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    state_file = work_dir / "recovery-session.json"
    steps: list[str] = []

    state = AppState.bootstrap(str(work_dir))
    workspace = state.focused_workspace
    if workspace is None or workspace.focused_tab is None:
        raise RuntimeError("failed to bootstrap recovery workspace")
    workspace.label = "recovery-lab"
    tab = workspace.focused_tab
    tab.label = "restart"
    pane = tab.focused_pane
    if pane is None:
        raise RuntimeError("failed to bootstrap recovery pane")
    pane.title = "crashy-agent"
    steps.append("workspace_created")

    crash_command = _python_command(f"import sys; print('{CRASH_MARKER}'); sys.exit(7)")
    crash_result = _result(
        dispatch(state, {"id": "crash", "method": "pane.run", "params": {"pane_id": pane.id, "command": crash_command}})
    )
    crash_pane = _pane_record(state, pane.id)
    crash_capture = _capture(state, pane.id)
    if crash_result.get("exit_code") != 7 or crash_pane["agent_status"] != "blocked":
        raise RuntimeError(f"pane crash was not captured as blocked: {crash_result} {crash_pane}")
    if CRASH_MARKER not in crash_capture["output"]:
        raise RuntimeError("crash marker was not captured")
    steps.append("pane_crash_captured")

    saved = save_state(state, state_file)
    steps.append("state_saved")

    restarted = load_state(saved)
    restarted_pane = restarted.require_pane(pane.id)
    restarted_record = _pane_record(restarted, restarted_pane.id)
    if restarted_record["agent_status"] != "blocked":
        raise RuntimeError("server restart did not preserve blocked pane status")
    steps.append("server_restarted")

    attached_state = _result(dispatch(restarted, {"id": "attach", "method": "state.get", "params": {}}))["state"]
    attached_capture = _capture(restarted, restarted_pane.id)
    if CRASH_MARKER not in attached_capture["output"]:
        raise RuntimeError("attached client could not read crash output")
    steps.append("attach_recovered")

    recovery_command = _python_command(f"print('{RECOVERY_MARKER}')")
    recovery_result = _result(
        dispatch(
            restarted,
            {
                "id": "recover",
                "method": "pane.run",
                "params": {"pane_id": restarted_pane.id, "command": recovery_command},
            },
        )
    )
    recovery_record = _pane_record(restarted, restarted_pane.id)
    recovery_capture = _capture(restarted, restarted_pane.id)
    if recovery_result.get("exit_code") != 0 or recovery_record["agent_status"] != "done":
        raise RuntimeError(f"recovered pane did not return to done: {recovery_result} {recovery_record}")
    if RECOVERY_MARKER not in recovery_capture["output"]:
        raise RuntimeError("recovery marker was not captured")
    steps.append("pane_recovered")

    saved_after_recovery = save_state(restarted, state_file)
    restored_after_recovery = load_state(saved_after_recovery)
    restored_pane = restored_after_recovery.require_pane(pane.id)
    restored_record = _pane_record(restored_after_recovery, restored_pane.id)
    restored_capture = _capture(restored_after_recovery, restored_pane.id)
    steps.append("state_resaved")

    return {
        "result": "ok",
        "steps": steps,
        "state_file": str(saved_after_recovery),
        "workspace": {
            "id": workspace.id,
            "label": workspace.label,
            "tab": {"id": tab.id, "label": tab.label},
        },
        "pane": {
            "id": pane.id,
            "title": pane.title,
        },
        "crash": {
            "marker": CRASH_MARKER,
            "command": crash_command,
            "exit_code": crash_result["exit_code"],
            "status": crash_pane["agent_status"],
            "output_contains_marker": CRASH_MARKER in crash_capture["output"],
            "line_count": crash_capture["line_count"],
        },
        "reattached": {
            "workspace_count": len(attached_state.get("workspaces", [])),
            "status": restarted_record["agent_status"],
            "output_lines": restarted_record["output_lines"],
            "capture_contains_crash": CRASH_MARKER in attached_capture["output"],
        },
        "recovery": {
            "marker": RECOVERY_MARKER,
            "command": recovery_command,
            "exit_code": recovery_result["exit_code"],
            "status": recovery_record["agent_status"],
            "output_contains_marker": RECOVERY_MARKER in recovery_capture["output"],
            "line_count": recovery_capture["line_count"],
        },
        "restored_after_recovery": {
            "status": restored_record["agent_status"],
            "output_lines": restored_record["output_lines"],
            "capture_contains_recovery": RECOVERY_MARKER in restored_capture["output"],
        },
    }


def default_work_dir() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(".artifacts") / "recovery-scenario" / f"{stamp}-{os.getpid()}"


def _python_command(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def _result(response: dict[str, Any]) -> dict[str, Any]:
    error = response.get("error")
    if error:
        raise RuntimeError(str(error.get("message") or error))
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"unexpected API response: {response}")
    return result


def _pane_record(state: AppState, pane_id: str) -> dict[str, Any]:
    return _result(dispatch(state, {"id": "pane", "method": "pane.get", "params": {"pane_id": pane_id}}))["pane"]


def _capture(state: AppState, pane_id: str) -> dict[str, Any]:
    return _result(dispatch(state, {"id": "capture", "method": "pane.capture", "params": {"pane_id": pane_id}}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PyHerdr recovery scenario")
    parser.add_argument("--work-dir", type=Path, default=default_work_dir(), help="directory for scenario artifacts")
    parser.add_argument("--json", action="store_true", help="print machine-readable scenario report")
    args = parser.parse_args(argv)

    report = run_recovery_scenario(args.work_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"recovery scenario: {report['result']}")
        print(f"crash: {report['crash']['status']} exit {report['crash']['exit_code']}")
        print(f"recovery: {report['recovery']['status']} exit {report['recovery']['exit_code']}")
        print(f"state: {report['state_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
