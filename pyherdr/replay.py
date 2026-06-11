from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_recording(path: Path | str) -> dict[str, Any]:
    """Load a session recording JSON artifact."""
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("type") != "session_recording":
        raise ValueError(f"not a pyherdr session recording: {target}")
    return payload


def summarize_recording(recording: dict[str, Any], *, last_lines: int = 5) -> dict[str, Any]:
    """Return a compact replay/inspection summary for a recording."""
    panes: list[dict[str, Any]] = []
    tab_count = 0
    for workspace in _records(recording.get("workspaces")):
        for tab in _records(workspace.get("tabs")):
            tab_count += 1
            for pane in _records(tab.get("panes")):
                output = pane.get("output") if isinstance(pane.get("output"), dict) else {}
                lines = [str(line) for line in output.get("lines", [])] if isinstance(output, dict) else []
                panes.append(
                    {
                        "workspace_id": str(workspace.get("workspace_id", "")),
                        "workspace_label": str(workspace.get("label", "")),
                        "tab_id": str(tab.get("tab_id", "")),
                        "tab_label": str(tab.get("label", "")),
                        "pane_id": str(pane.get("pane_id", "")),
                        "title": str(pane.get("title", "")),
                        "agent_status": str(pane.get("agent_status", "")),
                        "line_count": (
                            _as_int(output.get("line_count"), len(lines)) if isinstance(output, dict) else 0
                        ),
                        "total_lines": (
                            _as_int(output.get("total_lines"), len(lines)) if isinstance(output, dict) else 0
                        ),
                        "last_lines": lines[-last_lines:] if last_lines > 0 else [],
                    }
                )
    return {
        "type": "recording_summary",
        "version": recording.get("version"),
        "session": str(recording.get("session", "")),
        "created_at": str(recording.get("created_at", "")),
        "workspace_count": len(list(_records(recording.get("workspaces")))),
        "tab_count": tab_count,
        "pane_count": len(panes),
        "timeline_count": len(list(_records(recording.get("timeline")))),
        "panes": panes,
    }


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
