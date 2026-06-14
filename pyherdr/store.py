from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import AppState
from .session import session_runtime_dir

STATE_SCHEMA_VERSION = 1
STATE_KEYS = {"workspaces", "focused_workspace_id", "next_pane_number", "schedules"}
WORKSPACE_KEYS = {"id", "label", "cwd", "tabs", "focused_tab_id"}
TAB_KEYS = {"id", "label", "panes", "focused_pane_id", "synchronized", "layout"}
PANE_KEYS = {
    "id",
    "title",
    "cwd",
    "command",
    "agent",
    "remote_host",
    "remote_cwd",
    "output",
    "status",
    "custom_status",
}


def default_state_path() -> Path:
    override = os.environ.get("PYHERDR_STATE_PATH")
    if override:
        return Path(override).expanduser()
    return session_runtime_dir() / "session.json"


def save_state(state: AppState, path: Path | None = None) -> Path:
    target = path or default_state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(to_saved_dict(state), indent=2), encoding="utf-8")
    return target


def load_state(path: Path | None = None) -> AppState:
    target = path or default_state_path()
    if not target.exists():
        return AppState.bootstrap()
    state = from_dict(json.loads(target.read_text(encoding="utf-8")))
    if not state.workspaces:
        # A saved-but-empty session (e.g. last workspace closed) bootstraps a
        # default so the server never serves an unusable empty state.
        return AppState.bootstrap()
    return state


def to_dict(state: AppState) -> dict:
    return state.model_dump(mode="json")


def to_saved_dict(state: AppState) -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "state": to_dict(state),
    }


def from_dict(payload: dict[str, Any]) -> AppState:
    return AppState.model_validate(migrate_state_payload(payload))


def migrate_state_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the current raw AppState payload from any supported save format."""
    if "schema_version" in payload:
        version = int(payload.get("schema_version") or 0)
        if version > STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported PyHerdr state schema version: {version}")
        state = payload.get("state")
        if not isinstance(state, dict):
            raise ValueError("versioned PyHerdr state file is missing a state object")
        return _migrate_legacy_state(state)
    return _migrate_legacy_state(payload)


def _migrate_legacy_state(payload: dict[str, Any]) -> dict[str, Any]:
    state = dict(payload)
    state.setdefault("workspaces", [])
    state.setdefault("focused_workspace_id", state.pop("current_workspace_id", None))
    state.setdefault("next_pane_number", 1)
    state.setdefault("schedules", [])

    workspaces = state.get("workspaces")
    if isinstance(workspaces, list):
        state["workspaces"] = [_migrate_workspace(workspace) for workspace in workspaces if isinstance(workspace, dict)]
    else:
        state["workspaces"] = []
    return {key: state[key] for key in STATE_KEYS if key in state}


def _migrate_workspace(payload: dict[str, Any]) -> dict[str, Any]:
    workspace = dict(payload)
    workspace.setdefault("id", str(workspace.get("name") or workspace.get("label") or "ws_legacy"))
    workspace.setdefault("label", str(workspace.get("name") or workspace.get("title") or workspace["id"]))
    workspace.setdefault("cwd", str(workspace.get("path") or "."))
    workspace.setdefault("focused_tab_id", workspace.pop("current_tab_id", None))
    tabs = workspace.get("tabs")
    workspace["tabs"] = [
        _migrate_tab(tab, str(workspace["cwd"])) for tab in tabs if isinstance(tab, dict)
    ] if isinstance(tabs, list) else []
    return {key: workspace[key] for key in WORKSPACE_KEYS if key in workspace}


def _migrate_tab(payload: dict[str, Any], cwd: str) -> dict[str, Any]:
    tab = dict(payload)
    tab.setdefault("id", str(tab.get("name") or tab.get("label") or "tab_legacy"))
    tab.setdefault("label", str(tab.get("name") or tab.get("title") or tab["id"]))
    tab.setdefault("focused_pane_id", tab.pop("current_pane_id", None))
    tab.setdefault("synchronized", False)
    tab.setdefault("layout", {})
    panes = tab.get("panes")
    tab["panes"] = (
        [_migrate_pane(pane, cwd) for pane in panes if isinstance(pane, dict)] if isinstance(panes, list) else []
    )
    return {key: tab[key] for key in TAB_KEYS if key in tab}


def _migrate_pane(payload: dict[str, Any], cwd: str) -> dict[str, Any]:
    pane = dict(payload)
    pane.setdefault("id", str(pane.get("name") or pane.get("title") or "pane_legacy"))
    pane.setdefault("title", str(pane.get("label") or pane.get("name") or pane["id"]))
    pane.setdefault("cwd", cwd)
    pane.setdefault("command", "")
    pane.setdefault("agent", "")
    pane.setdefault("remote_host", "")
    pane.setdefault("remote_cwd", "")
    pane.setdefault("output", [])
    pane.setdefault("status", "idle")
    pane.setdefault("custom_status", "")
    return {key: pane[key] for key in PANE_KEYS if key in pane}
