"""Run a deterministic PyHerdr polished agent UX scenario.

Usage:
    python -m tools.agent_ux_scenario --json
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from pyherdr.api import dispatch
from pyherdr.config import ToastDelivery
from pyherdr.launchers import built_in_launcher_presets
from pyherdr.models import AgentStatus, AppState, Pane
from pyherdr.notification import Notification, deliver

AGENT_RUNS = (
    ("claude", "Claude Code", AgentStatus.BLOCKED, "waiting on approval"),
    ("codex", "Codex", AgentStatus.WORKING, "editing next slice"),
    ("aider", "Aider", AgentStatus.DONE, "patch ready"),
)


def run_agent_ux_scenario(
    work_dir: Path,
    *,
    render_screenshot: bool = True,
    width: int = 132,
    height: int = 38,
) -> dict[str, Any]:
    """Exercise launcher, agent status, attention, toast, and screenshot UX."""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    state = AppState.bootstrap(str(work_dir))
    workspace = state.focused_workspace
    if workspace is None or workspace.focused_tab is None:
        raise RuntimeError("failed to bootstrap workspace")
    workspace.label = "agent-ux"
    tab = workspace.focused_tab
    tab.label = "agents"
    steps = ["workspace_created"]

    launchers = built_in_launcher_presets(default_shell="pwsh")
    required_launchers = {"claude", "codex", "aider", "shell"}
    launcher_ids = {preset.id for preset in launchers}
    missing = sorted(required_launchers - launcher_ids)
    if missing:
        raise RuntimeError(f"missing launcher preset(s): {', '.join(missing)}")
    steps.append("launcher_presets_visible")

    panes = _ensure_agent_panes(state, workspace.id, tab.id)
    for pane, (agent, title, status, message) in zip(panes, AGENT_RUNS, strict=True):
        _result(
            dispatch(
                state,
                {"id": f"rename-{agent}", "method": "pane.rename", "params": {"pane_id": pane.id, "title": title}},
            )
        )
        pane.agent = agent
        pane.command = agent
        pane.append_output(f"{title}: {message}")
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
    steps.append("agents_reported")

    agents = _result(dispatch(state, {"id": "agents", "method": "agent.list", "params": {}}))["agents"]
    attention = _result(dispatch(state, {"id": "attention", "method": "agent.focus", "params": {"attention": True}}))[
        "agent"
    ]
    if attention["agent_status"] != AgentStatus.BLOCKED.value:
        raise RuntimeError(f"attention focus should prefer blocked agent, got {attention['agent_status']}")
    steps.append("attention_focused")

    notification = Notification(
        title="Claude Code needs attention",
        body="agent-ux scenario detected a blocked agent",
        sound="request",
    )
    toast_delivery = deliver(notification, ToastDelivery.HERDR)
    steps.append("toast_delivered")

    screenshot_path = work_dir / "agent-ux.svg"
    if render_screenshot:
        from pyherdr.demo_screenshot import render_demo_screenshot as render_tui_screenshot

        render_tui_screenshot(screenshot_path, width=width, height=height, view="agent-ux")
        steps.append("screenshot_exported")
    else:
        steps.append("screenshot_skipped")

    events = _result(dispatch(state, {"id": "events", "method": "events.snapshot", "params": {}}))
    return {
        "result": "ok",
        "steps": steps,
        "workspace": {"id": workspace.id, "label": workspace.label, "cwd": workspace.cwd},
        "tab": {"id": tab.id, "label": tab.label},
        "launchers": [
            {"id": preset.id, "label": preset.label, "agent": preset.agent, "built_in": preset.built_in}
            for preset in launchers
            if preset.id in required_launchers
        ],
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
        "sidebar": _sidebar_summary(agents),
        "attention_focus": {
            "pane_id": attention["pane_id"],
            "agent": attention["agent"],
            "status": attention["agent_status"],
            "custom_status": attention["custom_status"],
        },
        "toast": {"title": notification.title, "delivery": toast_delivery, "sound": notification.sound},
        "screenshot": {"path": str(screenshot_path), "exists": screenshot_path.exists()},
        "event_count": events["event_count"],
    }


def default_work_dir() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(".artifacts") / "agent-ux-scenario" / f"{stamp}-{os.getpid()}"


def _ensure_agent_panes(state: AppState, workspace_id: str, tab_id: str) -> list[Pane]:
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
    return tab.panes[: len(AGENT_RUNS)]


def _sidebar_summary(agents: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status.value: 0 for status in AgentStatus}
    for agent in agents:
        status = str(agent.get("agent_status") or AgentStatus.UNKNOWN.value)
        counts[status] = counts.get(status, 0) + 1
    return {
        "agent_count": len(agents),
        "blocked": counts[AgentStatus.BLOCKED.value],
        "working": counts[AgentStatus.WORKING.value],
        "done": counts[AgentStatus.DONE.value],
        "attention_count": counts[AgentStatus.BLOCKED.value] + counts[AgentStatus.DONE.value],
    }


def _result(response: dict[str, Any]) -> dict[str, Any]:
    error = response.get("error")
    if error:
        raise RuntimeError(str(error.get("message") or error))
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"unexpected API response: {response}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PyHerdr polished agent UX scenario")
    parser.add_argument("--work-dir", type=Path, default=default_work_dir(), help="directory for scenario artifacts")
    parser.add_argument("--json", action="store_true", help="print machine-readable scenario report")
    parser.add_argument("--no-screenshot", action="store_true", help="skip Textual screenshot export")
    parser.add_argument("--width", type=int, default=132, help="screenshot terminal columns")
    parser.add_argument("--height", type=int, default=38, help="screenshot terminal rows")
    args = parser.parse_args(argv)

    report = run_agent_ux_scenario(
        args.work_dir,
        render_screenshot=not args.no_screenshot,
        width=args.width,
        height=args.height,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"agent UX scenario: {report['result']}")
        print(f"agents: {len(report['agents'])}")
        print(f"attention: {report['attention_focus']['agent']} {report['attention_focus']['status']}")
        print(f"screenshot: {report['screenshot']['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
