"""Run a deterministic PyHerdr daily-driver scenario.

Usage:
    python -m tools.daily_driver_scenario --json
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
from pyherdr.models import AgentStatus, AppState, Pane
from pyherdr.store import load_state, save_state

AGENT_RUNS = (
    ("claude", "python -c \"print('claude ready for review')\"", AgentStatus.WORKING, "reviewing plan"),
    ("codex", "python -c \"print('codex tests passed')\"", AgentStatus.DONE, "tests passed"),
    ("shell", "python -c \"print('shell needs input')\"", AgentStatus.BLOCKED, "needs operator input"),
)


def run_daily_driver_scenario(work_dir: Path) -> dict[str, Any]:
    """Create a worktree, simulate agent panes, persist, and reload state."""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    repo = _create_repo(work_dir / "repo")
    worktree = work_dir / "worktrees" / "repo-daily-driver"
    state_file = work_dir / "session.json"
    state = AppState.bootstrap(str(repo))
    steps: list[str] = ["repo_created"]

    worktree_result = _result(
        dispatch(
            state,
            {
                "id": "worktree",
                "method": "worktree.create",
                "params": {
                    "cwd": str(repo),
                    "branch": "daily-driver",
                    "path": str(worktree),
                    "label": "daily-driver",
                },
            },
        )
    )
    steps.append("worktree_created")
    workspace = worktree_result["workspace"]
    workspace_id = str(workspace["workspace_id"])
    tab_id = str(workspace["focused_tab_id"])
    panes = _ensure_agent_panes(state, workspace_id, tab_id)

    for pane, (agent, command, status, message) in zip(panes, AGENT_RUNS, strict=True):
        _result(
            dispatch(
                state,
                {"id": f"run-{agent}", "method": "pane.run", "params": {"pane_id": pane.id, "command": command}},
            )
        )
        pane.agent = agent
        _result(
            dispatch(
                state,
                {
                    "id": f"status-{agent}",
                    "method": "pane.report_agent",
                    "params": {"pane_id": pane.id, "state": status.value, "message": message},
                },
            )
        )
    steps.append("agents_launched")

    agents = _result(dispatch(state, {"id": "agents", "method": "agent.list", "params": {}}))["agents"]
    events = _result(dispatch(state, {"id": "events", "method": "events.snapshot", "params": {}}))
    steps.append("status_visible")

    saved = save_state(state, state_file)
    steps.append("detached")
    reattached = load_state(saved)
    reattached_state = _result(dispatch(reattached, {"id": "reattach", "method": "state.get", "params": {}}))["state"]
    steps.append("reattached")

    return {
        "result": "ok",
        "steps": steps,
        "repo": str(repo),
        "worktree": str(worktree),
        "state_file": str(saved),
        "workspace": {
            "id": workspace_id,
            "label": workspace["label"],
            "cwd": workspace["cwd"],
        },
        "agents": [
            {
                "pane_id": agent["pane_id"],
                "title": agent["title"],
                "agent": agent["agent"],
                "status": agent["agent_status"],
                "custom_status": agent["custom_status"],
            }
            for agent in agents
        ],
        "event_count": events["event_count"],
        "reattached": _summarize_state(reattached_state),
    }


def default_work_dir() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(".artifacts") / "daily-driver-scenario" / f"{stamp}-{os.getpid()}"


def _ensure_agent_panes(state: AppState, workspace_id: str, tab_id: str) -> list[Pane]:
    workspace = state.require_workspace(workspace_id)
    tab = state.require_tab(workspace_id, tab_id)
    while len(tab.panes) < len(AGENT_RUNS):
        _result(
            dispatch(
                state,
                {
                    "id": f"pane-{len(tab.panes) + 1}",
                    "method": "pane.create",
                    "params": {"workspace_id": workspace_id, "tab_id": tab_id, "title": "agent"},
                },
            )
        )
    for pane, (agent, _command, _status, _message) in zip(tab.panes, AGENT_RUNS, strict=True):
        _result(
            dispatch(
                state,
                {"id": f"rename-{agent}", "method": "pane.rename", "params": {"pane_id": pane.id, "title": agent}},
            )
        )
        pane.cwd = workspace.cwd
    return tab.panes[: len(AGENT_RUNS)]


def _create_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("# Daily Driver\n", encoding="utf-8")
    _git(["init"], path)
    _git(["add", "README.md"], path)
    _git(["-c", "user.email=pyherdr@example.invalid", "-c", "user.name=PyHerdr", "commit", "-m", "init"], path)
    return path


def _git(args: list[str], cwd: Path) -> None:
    completed = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"git {' '.join(args)} failed")


def _result(response: dict[str, Any]) -> dict[str, Any]:
    error = response.get("error")
    if error:
        raise RuntimeError(str(error.get("message") or error))
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"unexpected API response: {response}")
    return result


def _summarize_state(state: dict[str, Any]) -> dict[str, Any]:
    workspaces = state.get("workspaces", [])
    agents: list[dict[str, str]] = []
    for workspace in workspaces:
        for tab in workspace.get("tabs", []):
            for pane in tab.get("panes", []):
                if pane.get("agent"):
                    agents.append(
                        {
                            "pane_id": str(pane.get("id") or ""),
                            "agent": str(pane.get("agent") or ""),
                            "status": str(pane.get("status") or ""),
                            "running": str(bool(pane.get("running"))).lower(),
                        }
                    )
    return {"workspace_count": len(workspaces), "agents": agents}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PyHerdr daily-driver scenario")
    parser.add_argument("--work-dir", type=Path, default=default_work_dir(), help="directory for scenario artifacts")
    parser.add_argument("--json", action="store_true", help="print machine-readable scenario report")
    args = parser.parse_args(argv)

    report = run_daily_driver_scenario(args.work_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"daily-driver scenario: {report['result']}")
        print(f"worktree: {report['worktree']}")
        print(f"agents: {len(report['agents'])}")
        print(f"state: {report['state_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
