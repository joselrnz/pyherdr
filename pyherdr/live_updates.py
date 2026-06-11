from __future__ import annotations

from typing import Any

from .models import AppState


def build_state_events(
    state: AppState,
    *,
    previous_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build dashboard-friendly state/update events from current session state."""
    events: list[dict[str, Any]] = []
    for workspace in state.workspaces:
        events.append(
            {
                "type": "state_event",
                "kind": "workspace",
                "action": "snapshot",
                "workspace_id": workspace.id,
                "label": workspace.label,
                "status": workspace.status.value,
                "focused": workspace.id == state.focused_workspace_id,
            }
        )
        for tab in workspace.tabs:
            for pane in tab.panes:
                events.append(
                    {
                        "type": "state_event",
                        "kind": "agent_status",
                        "workspace_id": workspace.id,
                        "tab_id": tab.id,
                        "pane_id": pane.id,
                        "title": pane.title,
                        "status": pane.status.value,
                        "custom_status": pane.custom_status,
                    }
                )
    if previous_events is None:
        return events
    previous = {_event_key(event): _event_value(event) for event in previous_events}
    return [event for event in events if previous.get(_event_key(event)) != _event_value(event)]


def _event_key(event: dict[str, Any]) -> tuple[str, str]:
    kind = str(event.get("kind", ""))
    identifier = str(event.get("pane_id") or event.get("workspace_id") or "")
    return kind, identifier


def _event_value(event: dict[str, Any]) -> tuple[Any, ...]:
    if event.get("kind") == "workspace":
        return event.get("label"), event.get("status"), event.get("focused")
    return event.get("status"), event.get("custom_status"), event.get("title")
