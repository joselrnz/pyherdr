from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .models import AppState, Pane
from .session import current_session
from .workflow import redact

PaneCapture = Callable[[Pane], dict[str, Any]]


def build_session_recording(
    state: AppState,
    capture: PaneCapture,
    *,
    session_name: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a redacted snapshot recording for the current session state."""
    timestamp = created_at or _utc_timestamp()
    timeline: list[dict[str, Any]] = []
    workspaces: list[dict[str, Any]] = []

    for workspace in state.workspaces:
        tabs: list[dict[str, Any]] = []
        workspace_record: dict[str, Any] = {
            "workspace_id": workspace.id,
            "label": workspace.label,
            "cwd": workspace.cwd,
            "status": workspace.status.value,
            "focused_tab_id": workspace.focused_tab_id,
            "tabs": tabs,
        }
        for tab in workspace.tabs:
            panes: list[dict[str, Any]] = []
            tab_record: dict[str, Any] = {
                "tab_id": tab.id,
                "label": tab.label,
                "status": tab.status.value,
                "focused_pane_id": tab.focused_pane_id,
                "panes": panes,
            }
            for pane in tab.panes:
                output = _output_record(capture(pane))
                panes.append(_pane_record(pane, workspace.id, tab.id, output))
                timeline.append(
                    {
                        "timestamp": timestamp,
                        "kind": "agent_status",
                        "workspace_id": workspace.id,
                        "tab_id": tab.id,
                        "pane_id": pane.id,
                        "status": pane.status.value,
                        "custom_status": pane.custom_status,
                    }
                )
                timeline.append(
                    {
                        "timestamp": timestamp,
                        "kind": "pane_output",
                        "workspace_id": workspace.id,
                        "tab_id": tab.id,
                        "pane_id": pane.id,
                        "line_count": output["line_count"],
                        "total_lines": output["total_lines"],
                        "truncated": output["truncated"],
                    }
                )
            tabs.append(tab_record)
        workspaces.append(workspace_record)

    recording = {
        "type": "session_recording",
        "version": 1,
        "created_at": timestamp,
        "session": session_name or current_session(),
        "focused_workspace_id": state.focused_workspace_id,
        "workspaces": workspaces,
        "timeline": timeline,
    }
    return cast(dict[str, Any], redact(recording))


def write_session_recording(recording: dict[str, Any], path: Path) -> Path:
    """Write a recording artifact as pretty JSON and return its path."""
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(redact(recording), indent=2), encoding="utf-8")
    return target


def count_recorded_panes(recording: dict[str, Any]) -> int:
    """Return the number of pane snapshots in a recording payload."""
    total = 0
    for workspace in recording.get("workspaces", []):
        if not isinstance(workspace, dict):
            continue
        for tab in workspace.get("tabs", []):
            if isinstance(tab, dict):
                panes = tab.get("panes", [])
                if isinstance(panes, list):
                    total += len(panes)
    return total


def _pane_record(pane: Pane, workspace_id: str, tab_id: str, output: dict[str, Any]) -> dict[str, Any]:
    return {
        "pane_id": pane.id,
        "workspace_id": workspace_id,
        "tab_id": tab_id,
        "title": pane.title,
        "cwd": pane.cwd,
        "command": pane.command,
        "agent": pane.agent,
        "agent_status": pane.status.value,
        "custom_status": pane.custom_status,
        "output": output,
    }


def _output_record(capture_payload: dict[str, Any]) -> dict[str, Any]:
    raw_lines = capture_payload.get("lines")
    if isinstance(raw_lines, list):
        lines = [str(line) for line in raw_lines]
    else:
        output_text = str(capture_payload.get("output") or "")
        lines = output_text.split("\n") if output_text else []
    line_count = _payload_int(capture_payload, "line_count", len(lines))
    total_lines = _payload_int(capture_payload, "total_lines", line_count)
    return {
        "styled": bool(capture_payload.get("styled")),
        "total_lines": total_lines,
        "line_count": line_count,
        "truncated": bool(capture_payload.get("truncated")),
        "lines": lines,
        "output": str(capture_payload.get("output") or "\n".join(lines)),
    }


def _payload_int(payload: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
