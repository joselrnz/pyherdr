"""Run a deterministic PyHerdr headless automation scenario.

Usage:
    python -m tools.headless_scenario --json
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

DEFAULT_MARKER = "HEADLESS_READY"


def run_headless_scenario(work_dir: Path, *, marker: str = DEFAULT_MARKER) -> dict[str, Any]:
    """Exercise the no-TUI run/wait/capture/save workflow through API dispatch."""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    steps: list[str] = []

    state = AppState.bootstrap(str(work_dir))
    workspace = state.focused_workspace
    if workspace is None or workspace.focused_tab is None:
        raise RuntimeError("failed to bootstrap headless workspace")
    workspace.label = "headless-ci"
    tab = workspace.focused_tab
    tab.label = "ci"
    pane = tab.focused_pane
    if pane is None:
        raise RuntimeError("failed to bootstrap headless pane")
    pane.title = "runner"
    steps.append("workspace_created")

    command = _marker_command(marker)
    run_result = _dispatch_result(
        state,
        "pane.run",
        {"pane_id": pane.id, "command": command},
    )
    if run_result.get("exit_code") != 0:
        raise RuntimeError(f"headless command failed: {run_result}")
    steps.append("command_ran")

    read_result = _dispatch_result(state, "pane.read", {"pane_id": pane.id, "lines": 80})
    output = str(read_result.get("output") or "")
    if marker not in output:
        raise RuntimeError("headless marker was not visible in pane output")
    steps.append("output_waited")

    get_result = _dispatch_result(state, "pane.get", {"pane_id": pane.id})
    pane_record = _result_pane(get_result)
    if pane_record["agent_status"] != "done":
        raise RuntimeError(f"expected pane status done, got {pane_record['agent_status']}")
    steps.append("status_waited")

    capture = _dispatch_result(state, "pane.capture", {"pane_id": pane.id})
    captured_output = str(capture.get("output") or "")
    if marker not in captured_output:
        raise RuntimeError("headless marker was not captured")
    steps.append("output_captured")

    state_file = save_state(state, work_dir / "headless-session.json")
    restored = load_state(state_file)
    restored_pane = restored.require_pane(pane.id)
    if marker not in "\n".join(restored_pane.output):
        raise RuntimeError("headless output was not restored from state")
    restored_record = _result_pane(_dispatch_result(restored, "pane.get", {"pane_id": pane.id}))
    steps.append("state_saved")

    return {
        "result": "ok",
        "steps": steps,
        "workspace": {
            "id": workspace.id,
            "label": workspace.label,
            "cwd": workspace.cwd,
            "tab": {"id": tab.id, "label": tab.label},
        },
        "pane": pane_record,
        "command": command,
        "run": {"exit_code": run_result["exit_code"]},
        "wait": {
            "output_matched": marker in output,
            "status": pane_record["agent_status"],
        },
        "capture": {
            "total_lines": capture["total_lines"],
            "line_count": capture["line_count"],
            "truncated": capture["truncated"],
            "output_contains_marker": marker in captured_output,
        },
        "restored": restored_record,
        "state_file": str(state_file),
    }


def default_work_dir() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(".artifacts") / "headless-scenario" / f"{stamp}-{os.getpid()}"


def _marker_command(marker: str) -> str:
    return f'"{sys.executable}" -c "print({marker!r})"'


def _dispatch_result(state: AppState, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = dispatch(state, {"id": "headless", "method": method, "params": params})
    error = response.get("error")
    if error:
        raise RuntimeError(str(error.get("message") or error))
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"unexpected response for {method}: {response}")
    return result


def _result_pane(result: dict[str, Any]) -> dict[str, Any]:
    pane = result.get("pane")
    if not isinstance(pane, dict):
        raise RuntimeError(f"unexpected pane response: {result}")
    return pane


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PyHerdr headless automation scenario")
    parser.add_argument("--work-dir", type=Path, default=default_work_dir(), help="directory for scenario artifacts")
    parser.add_argument("--marker", default=DEFAULT_MARKER, help="output marker to wait for and capture")
    parser.add_argument("--json", action="store_true", help="print machine-readable scenario report")
    args = parser.parse_args(argv)

    report = run_headless_scenario(args.work_dir, marker=args.marker)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"headless scenario: {report['result']}")
        print(f"pane: {report['pane']['pane_id']} {report['pane']['agent_status']}")
        print(f"capture lines: {report['capture']['line_count']}")
        print(f"state: {report['state_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
