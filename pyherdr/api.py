from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .config import load_config
from .contracts.api import ApiError, ApiRequest, ApiResponse
from .cron import parse_cron
from .detect import detect, identify_agent_in_command, parse_agent_label
from .detector import detect_agent_status
from .layout import Direction, PaneNode, TileLayout
from .live_updates import build_state_events
from .models import AgentStatus, AppState, Pane, Tab
from .notification import Notification, deliver
from .recording import build_session_recording, count_recorded_panes, write_session_recording
from .runtime import TerminalManager
from .runtime.procstats import AVAILABLE as STATS_AVAILABLE
from .session import current_session
from .store import to_dict
from .workspace_recents import record_workspace_recent
from .worktree import create_worktree, list_worktrees, remove_worktree


def dispatch(state: AppState, request: dict[str, Any], processes: TerminalManager | None = None) -> dict[str, Any]:
    try:
        parsed = ApiRequest.model_validate(request)
        result = _dispatch_method(state, parsed.method, parsed.params, processes)
        return ApiResponse(id=parsed.id, result=result).model_dump(mode="json", exclude_none=True)
    except ValidationError as error:
        request_id = str(request.get("id") or "request")
        api_error = ApiError(code="invalid_request", message=str(error))
        return ApiResponse(id=request_id, error=api_error).model_dump(mode="json", exclude_none=True)
    except (KeyError, ValueError, TypeError) as error:
        request_id = str(request.get("id") or "request")
        api_error = ApiError(code="invalid_request", message=str(error))
        return ApiResponse(id=request_id, error=api_error).model_dump(mode="json", exclude_none=True)
    except (RuntimeError, OSError) as error:
        # PTY/session I/O failures (e.g. writing to a pane whose process exited)
        # become a structured error instead of crashing the handler thread.
        request_id = str(request.get("id") or "request")
        api_error = ApiError(code="runtime_error", message=str(error))
        return ApiResponse(id=request_id, error=api_error).model_dump(mode="json", exclude_none=True)


def _dispatch_method(
    state: AppState,
    method: str,
    params: dict[str, Any],
    processes: TerminalManager | None,
) -> dict[str, Any]:
    handlers: dict[str, Callable[[AppState, dict[str, Any], TerminalManager | None], dict[str, Any]]] = {
        "ping": _ping,
        "state.get": _state_get,
        "stats.get": _stats_get,
        "events.snapshot": _events_snapshot,
        "notification.show": _notification_show,
        "workspace.create": _workspace_create,
        "workspace.get": _workspace_get,
        "workspace.list": _workspace_list,
        "workspace.focus": _workspace_focus,
        "workspace.rename": _workspace_rename,
        "workspace.move": _workspace_move,
        "workspace.close": _workspace_close,
        "worktree.list": _worktree_list,
        "worktree.create": _worktree_create,
        "worktree.open": _worktree_open,
        "worktree.remove": _worktree_remove,
        "tab.create": _tab_create,
        "tab.get": _tab_get,
        "tab.list": _tab_list,
        "tab.focus": _tab_focus,
        "tab.rename": _tab_rename,
        "tab.move": _tab_move,
        "tab.close": _tab_close,
        "tab.sync": _tab_sync,
        "pane.list": _pane_list,
        "pane.get": _pane_get,
        "pane.create": _pane_create,
        "pane.split": _pane_split,
        "pane.set_layout": _pane_set_layout,
        "pane.rename": _pane_rename,
        "pane.close": _pane_close,
        "pane.read": _pane_read,
        "pane.wait_output": _pane_wait_output,
        "pane.capture": _pane_capture,
        "pane.run": _pane_run,
        "pane.start": _pane_start,
        "pane.send_text": _pane_send_text,
        "pane.send_key": _pane_send_key,
        "pane.resize": _pane_resize,
        "pane.scroll": _pane_scroll,
        "pane.stop": _pane_stop,
        "pane.report_agent": _pane_report_agent,
        "pane.broadcast": _pane_broadcast,
        "pane.fanout": _pane_fanout,
        "agent.list": _agent_list,
        "agent.get": _agent_get,
        "agent.read": _agent_read,
        "agent.send": _agent_send,
        "agent.rename": _agent_rename,
        "agent.focus": _agent_focus,
        "agent.start": _agent_start,
        "session.record": _session_record,
        "schedule.add": _schedule_add,
        "schedule.list": _schedule_list,
        "schedule.remove": _schedule_remove,
        "schedule.run": _schedule_run,
    }
    try:
        handler = handlers[method]
    except KeyError as error:
        raise ValueError(f"unknown method: {method}") from error
    return handler(state, params, processes)


def _ping(_state: AppState, _params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    return {"type": "pong", "server": "pyherdr"}


def _stats_get(_state: AppState, _params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    """Return the latest per-pane CPU/RAM snapshot gathered by the server sampler."""
    snapshot = processes.stats_snapshot() if processes else {}
    return {"type": "stats", "available": STATS_AVAILABLE, "stats": snapshot}


def _events_snapshot(state: AppState, _params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    """Return dashboard-friendly state/status events."""
    events = build_state_events(state)
    return {"type": "events_snapshot", "events": events, "event_count": len(events)}


def _ensure_layout(tab: Tab) -> TileLayout:
    """Repair/build the tab's BSP layout so its panes match ``tab.panes``.

    Panes added/removed outside of ``pane.split`` (CLI ``pane.create``, bootstrap,
    ``pane.close``) leave the layout out of sync; this reconciles it (new panes are
    appended as side-by-side splits; gone panes are closed and the tree reflows).
    """
    ids = [pane.id for pane in tab.panes]
    if not ids:
        tab.layout = {}
        return TileLayout(PaneNode(""), "")
    layout: TileLayout | None = None
    if tab.layout:
        try:
            layout = TileLayout.from_dict(tab.layout)
        except (KeyError, ValueError, TypeError):
            layout = None
    if layout is None:
        layout = TileLayout.single(ids[0])
        for pane_id in ids[1:]:
            layout.split_focused(pane_id, Direction.HORIZONTAL)
    else:
        for gone in set(layout.pane_ids()) - set(ids):
            layout.close_pane(gone)
        for pane_id in ids:
            if pane_id not in layout.pane_ids():
                layout.split_focused(pane_id, Direction.HORIZONTAL)
    if tab.focused_pane_id and layout.contains(tab.focused_pane_id):
        layout.focus = tab.focused_pane_id
    else:
        tab.focused_pane_id = layout.focus or ids[0]
    tab.layout = layout.to_dict()
    return layout


def _state_get(state: AppState, _params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    # Keep each tab's split-tree layout in sync with its pane list before serializing.
    for workspace in state.workspaces:
        for tab in workspace.tabs:
            _ensure_layout(tab)
    data = to_dict(state)
    # Annotate each pane with whether it has a live PTY session right now, so the
    # UI can tell a persisted-but-dead pane (after a restart) from a live one.
    running = set(processes.running_pane_ids()) if processes else set()
    for workspace in data.get("workspaces", []):
        for tab in workspace.get("tabs", []):
            for pane in tab.get("panes", []):
                pane["running"] = pane.get("id") in running
    return {"type": "state", "state": data}


def _notification_show(_state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    notification = Notification(
        title=_required(params, "title"),
        body=str(params.get("body") or ""),
        position=str(params.get("position") or "bottom-right"),
        sound=str(params.get("sound") or "none"),
    )
    delivered = deliver(notification, load_config().ui.toast.delivery)
    return {"type": "notification_shown", "title": notification.title, "delivered": delivered}


def _workspace_create(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace = state.create_workspace(
        label=str(params.get("label") or "workspace"),
        cwd=str(params.get("cwd") or "."),
    )
    state.create_tab(workspace.id, "shell")
    try:
        record_workspace_recent(workspace.cwd, label=workspace.label)
    except (OSError, ValueError):
        pass
    return {"type": "workspace_created", "workspace": _workspace_record(workspace)}


def _workspace_list(state: AppState, _params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    return {
        "type": "workspace_list",
        "workspaces": [_workspace_record(workspace) for workspace in state.workspaces],
        "focused_workspace_id": state.focused_workspace_id,
    }


def _workspace_get(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace = state.require_workspace(_required(params, "workspace_id"))
    return {"type": "workspace_info", "workspace": _workspace_record(workspace)}


def _workspace_focus(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = _required(params, "workspace_id")
    workspace = state.require_workspace(workspace_id)
    state.focused_workspace_id = workspace.id
    return {"type": "workspace_focused", "workspace": _workspace_record(workspace)}


def _workspace_rename(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace = state.require_workspace(_required(params, "workspace_id"))
    workspace.label = str(params.get("label") or workspace.label)
    return {"type": "workspace_renamed", "workspace": _workspace_record(workspace)}


def _workspace_close(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = _required(params, "workspace_id")
    before = len(state.workspaces)
    state.workspaces = [workspace for workspace in state.workspaces if workspace.id != workspace_id]
    closed = len(state.workspaces) != before
    if state.focused_workspace_id == workspace_id:
        state.focused_workspace_id = state.workspaces[0].id if state.workspaces else None
    return {"type": "workspace_closed", "workspace_id": workspace_id, "closed": closed}


def _focused_cwd(state: AppState) -> str:
    workspace = state.focused_workspace
    return workspace.cwd if workspace else "."


def _worktree_list(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    cwd = str(params.get("cwd") or _focused_cwd(state))
    worktrees = list_worktrees(cwd)
    return {
        "type": "worktree_list",
        "worktrees": [{"path": wt.path, "branch": wt.branch, "head": wt.head} for wt in worktrees],
    }


def _worktree_create(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    cwd = str(params.get("cwd") or _focused_cwd(state))
    branch = _required(params, "branch")
    base = params.get("base")
    path = params.get("path")
    directory = load_config().worktrees.directory
    created = create_worktree(cwd, branch, str(base) if base else None, str(path) if path else None, directory)
    workspace = state.create_workspace(str(params.get("label") or branch), created)
    state.create_tab(workspace.id, "shell")
    return {"type": "worktree_created", "path": created, "workspace": _workspace_record(workspace)}


def _worktree_open(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    path = _required(params, "path")
    workspace = state.create_workspace(str(params.get("label") or Path(path).name), path)
    state.create_tab(workspace.id, "shell")
    return {"type": "worktree_opened", "path": path, "workspace": _workspace_record(workspace)}


def _worktree_remove(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    path = _required(params, "path")
    force = bool(params.get("force"))
    remove_worktree(_focused_cwd(state), path, force)
    return {"type": "worktree_removed", "path": path}


def _tab_create(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id)
    workspace = state.require_workspace(workspace_id)
    tab = state.create_tab(workspace_id, str(params.get("label") or "shell"))
    if tab.focused_pane:
        tab.focused_pane.cwd = _resolve_new_cwd(workspace.cwd)
    return {"type": "tab_created", "tab": _tab_record(tab)}


def _tab_list(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id)
    workspace = state.require_workspace(workspace_id)
    return {
        "type": "tab_list",
        "tabs": [_tab_record(tab) for tab in workspace.tabs],
        "focused_tab_id": workspace.focused_tab_id,
    }


def _tab_get(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id)
    tab = state.require_tab(workspace_id, _required(params, "tab_id"))
    return {"type": "tab_info", "tab": _tab_record(tab)}


def _tab_focus(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id)
    workspace = state.require_workspace(workspace_id)
    tab = state.require_tab(workspace.id, _required(params, "tab_id"))
    workspace.focused_tab_id = tab.id
    return {"type": "tab_focused", "tab": _tab_record(tab)}


def _tab_rename(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id)
    tab = state.require_tab(workspace_id, _required(params, "tab_id"))
    tab.label = str(params.get("label") or tab.label)
    return {"type": "tab_renamed", "tab": _tab_record(tab)}


def _workspace_move(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = _required(params, "workspace_id")
    direction = "down" if str(params.get("direction") or "up").lower() == "down" else "up"
    ids = [workspace.id for workspace in state.workspaces]
    if workspace_id not in ids:
        raise KeyError(f"workspace not found: {workspace_id}")
    index = ids.index(workspace_id)
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(state.workspaces):
        state.workspaces[index], state.workspaces[target] = state.workspaces[target], state.workspaces[index]
    return {"type": "workspace_moved", "workspace_id": workspace_id, "direction": direction}


def _tab_move(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id)
    workspace = state.require_workspace(workspace_id)
    tab_id = _required(params, "tab_id")
    direction = "right" if str(params.get("direction") or "left").lower() == "right" else "left"
    ids = [tab.id for tab in workspace.tabs]
    if tab_id not in ids:
        raise KeyError(f"tab not found: {tab_id}")
    index = ids.index(tab_id)
    target = index - 1 if direction == "left" else index + 1
    if 0 <= target < len(workspace.tabs):
        workspace.tabs[index], workspace.tabs[target] = workspace.tabs[target], workspace.tabs[index]
    return {"type": "tab_moved", "tab_id": tab_id, "direction": direction}


def _tab_close(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id)
    workspace = state.require_workspace(workspace_id)
    tab_id = _required(params, "tab_id")
    before = len(workspace.tabs)
    workspace.tabs = [tab for tab in workspace.tabs if tab.id != tab_id]
    closed = len(workspace.tabs) != before
    if workspace.focused_tab_id == tab_id:
        workspace.focused_tab_id = workspace.tabs[0].id if workspace.tabs else None
    return {"type": "tab_closed", "workspace_id": workspace.id, "tab_id": tab_id, "closed": closed}


def _pane_list(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = params.get("workspace_id")
    tab_id = params.get("tab_id")
    panes: list[dict[str, Any]] = []
    for workspace in state.workspaces:
        if workspace_id and workspace.id != workspace_id:
            continue
        for tab in workspace.tabs:
            if tab_id and tab.id != tab_id:
                continue
            panes.extend(_pane_record(pane, workspace.id, tab.id) for pane in tab.panes)
    return {"type": "pane_list", "panes": panes}


def _pane_get(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    pane = state.require_pane(_required(params, "pane_id"))
    workspace_id, tab_id = _pane_context(state, pane.id)
    return {"type": "pane_info", "pane": _pane_record(pane, workspace_id, tab_id)}


def _resolve_new_cwd(follow_cwd: str) -> str:
    """Resolve the cwd for a new pane/tab from the ``terminal.new_cwd`` policy.

    ``follow`` (default) inherits ``follow_cwd``; ``home``/``current`` use those;
    ``path:<dir>`` or a bare path is used literally (``~`` expanded).
    """
    try:
        policy = (load_config().terminal.new_cwd or "follow").strip()
    except Exception:
        return follow_cwd
    low = policy.lower()
    if low in ("follow", ""):
        return follow_cwd
    if low in ("home", "~"):
        return os.path.expanduser("~")
    if low in ("current", "."):
        return os.getcwd()
    if low.startswith("path:"):
        return os.path.expanduser(policy[5:].strip()) or follow_cwd
    return os.path.expanduser(policy) or follow_cwd


def _pane_create(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id or "")
    workspace = state.require_workspace(workspace_id)
    tab_id = params.get("tab_id")
    if tab_id:
        tab = state.require_tab(workspace.id, str(tab_id))
    else:
        focused = workspace.focused_tab
        if focused is None:
            raise ValueError("workspace has no tab for the new pane")
        tab = focused
    follow = tab.focused_pane.cwd if tab.focused_pane else workspace.cwd
    pane = state.create_pane(workspace.id, tab.id, title=str(params.get("title") or "pane"))
    pane.cwd = _resolve_new_cwd(follow)
    return {"type": "pane_created", "pane": _pane_record(pane, workspace.id, tab.id)}


def _pane_split(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id or "")
    workspace = state.require_workspace(workspace_id)
    tab_id = params.get("tab_id")
    tab = state.require_tab(workspace.id, str(tab_id)) if tab_id else workspace.focused_tab
    if tab is None:
        raise ValueError("workspace has no tab to split")
    try:
        direction = Direction(str(params.get("direction") or "horizontal").lower())
    except ValueError:
        direction = Direction.HORIZONTAL
    ratio = float(params.get("ratio") or 0.5)
    target = tab.focused_pane_id
    follow = next((pane.cwd for pane in tab.panes if pane.id == target), workspace.cwd)
    layout = _ensure_layout(tab)
    pane = state.create_pane(workspace.id, tab.id, title=str(params.get("title") or "pane"))
    pane.cwd = _resolve_new_cwd(follow)
    if target and layout.contains(target):
        layout.focus = target
    layout.split_focused(pane.id, direction, ratio)
    tab.focused_pane_id = pane.id
    tab.layout = layout.to_dict()
    return {"type": "pane_split", "direction": direction.value, "pane": _pane_record(pane, workspace.id, tab.id)}


def _pane_set_layout(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id or "")
    workspace = state.require_workspace(workspace_id)
    tab_id = params.get("tab_id")
    tab = state.require_tab(workspace.id, str(tab_id)) if tab_id else workspace.focused_tab
    if tab is None:
        raise ValueError("workspace has no tab")
    layout_data = params.get("layout")
    if not isinstance(layout_data, dict):
        raise ValueError("layout must be an object")
    try:
        layout = TileLayout.from_dict(layout_data)
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(f"invalid layout: {exc}") from exc
    # Only accept a layout whose panes exactly match the tab's panes.
    if set(layout.pane_ids()) != {pane.id for pane in tab.panes}:
        raise ValueError("layout panes do not match tab panes")
    tab.layout = layout.to_dict()
    return {"type": "pane_layout_set", "tab_id": tab.id}


def _pane_rename(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    pane = state.require_pane(_required(params, "pane_id"))
    pane.title = str(params.get("title") or pane.title)
    workspace_id, tab_id = _pane_context(state, pane.id)
    return {"type": "pane_renamed", "pane": _pane_record(pane, workspace_id, tab_id)}


def _pane_close(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    pane_id = _required(params, "pane_id")
    if processes is not None:
        processes.stop(pane_id)
    for workspace in state.workspaces:
        for tab in workspace.tabs:
            before = len(tab.panes)
            tab.panes = [pane for pane in tab.panes if pane.id != pane_id]
            if len(tab.panes) != before:
                if tab.focused_pane_id == pane_id:
                    tab.focused_pane_id = tab.panes[0].id if tab.panes else None
                return {"type": "pane_closed", "pane_id": pane_id, "closed": True}
    return {"type": "pane_closed", "pane_id": pane_id, "closed": False}


def _pane_scroll(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("pane.scroll requires a server process manager")
    pane = state.require_pane(_required(params, "pane_id"))
    direction = _scroll_direction(params.get("direction"))
    viewport: dict[str, int | bool] | None = None
    try:
        processes.scroll(pane.id, direction)
        viewport = processes.viewport(pane.id)
    except KeyError:
        pass
    return {"type": "pane_scroll", "pane_id": pane.id, "direction": direction, "viewport": viewport}


def _scroll_direction(value: Any) -> str:
    direction = str(value or "up").lower().replace("-", "_")
    aliases = {
        "pageup": "page_up",
        "pagedown": "page_down",
    }
    direction = aliases.get(direction, direction)
    return direction if direction in {"up", "down", "page_up", "page_down", "top", "bottom"} else "up"


def _pane_read(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    pane = state.require_pane(_required(params, "pane_id"))
    lines = int(params.get("lines") or 80)
    styled = bool(params.get("styled"))
    terminal = {"alt_screen": False, "mouse_reporting": False}
    if processes is not None:
        try:
            # A terminal session, once started, is the source of truth for the
            # pane's screen; don't mix in stale one-shot `pane.run` output.
            if styled:
                # Styled reads return the ANSI-rendered visible screen for the live
                # terminal view; the plain snapshot still drives agent detection.
                output = processes.render_styled(pane.id, cursor=bool(params.get("cursor")))
                _update_status_from_screen(pane, processes.read(pane.id, lines))
            else:
                output = processes.read(pane.id, lines)
                _update_status_from_screen(pane, output)
            metadata = getattr(processes, "metadata", None)
            if callable(metadata):
                terminal.update({key: bool(value) for key, value in metadata(pane.id).items()})
        except KeyError:
            output = "\n".join(pane.output[-lines:])
    else:
        output = "\n".join(pane.output[-lines:])
    return {
        "type": "pane_read",
        "pane_id": pane.id,
        "output": output,
        "terminal": terminal,
    }


def _pane_wait_output(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    """Long-poll until one watched live pane has new terminal output."""
    if processes is None:
        raise ValueError("pane.wait_output requires a server process manager")
    raw_versions = params.get("versions", {})
    if not isinstance(raw_versions, dict):
        raise ValueError("pane.wait_output versions must be an object")
    versions: dict[str, int] = {}
    for pane_id, generation in raw_versions.items():
        pane = state.require_pane(str(pane_id))
        try:
            versions[pane.id] = int(generation)
        except (TypeError, ValueError):
            versions[pane.id] = -1
    timeout = float(params.get("timeout", 1.0))
    result = processes.wait_for_output(versions, timeout=timeout)
    return {
        "type": "pane_output_wait",
        "changed": result["changed"],
        "versions": result["versions"],
        "timed_out": result["timed_out"],
    }


def _update_status_from_screen(pane: Pane, output: str) -> None:
    """Refresh a pane's agent status from its live screen via per-agent detection."""
    if not pane.agent:
        return
    agent = parse_agent_label(pane.agent)
    if agent is None:
        return
    detection = detect(agent, output)
    if not detection.skip_state_update:
        pane.status = detection.state


def _pane_capture(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    """Capture a pane's output for scripts and AI loops (tmux ``capture-pane`` style).

    Unlike ``pane.read`` (which returns the last ~80 visible rows for the live UI),
    capture defaults to the *entire* scrollback buffer and reports line counts plus a
    structured ``lines`` array, so automation can consume pane output without
    screenshots. ``lines`` tails the last N rows; ``styled`` returns the ANSI-styled
    visible screen (scrollback history carries no styling).
    """
    pane = state.require_pane(_required(params, "pane_id"))
    styled = bool(params.get("styled"))
    cursor = bool(params.get("cursor"))
    limit = _capture_limit(params.get("lines"))
    captured = _capture_lines(pane, processes, styled=styled, cursor=cursor)
    total = len(captured)
    if limit is None:
        selected = captured
    elif limit == 0:
        selected = []
    else:
        selected = captured[-limit:]
    return {
        "type": "pane_capture",
        "pane_id": pane.id,
        "styled": styled,
        "total_lines": total,
        "line_count": len(selected),
        "truncated": len(selected) < total,
        "lines": selected,
        "output": "\n".join(selected),
    }


def _capture_lines(
    pane: Pane,
    processes: TerminalManager | None,
    *,
    styled: bool,
    cursor: bool,
) -> list[str]:
    """Return a pane's captured rows, preferring the live terminal over stored output.

    The plain screen always drives agent-status detection; ``styled`` additionally
    swaps the returned rows for the ANSI-rendered visible screen.
    """
    if processes is None:
        return list(pane.output)
    try:
        plain = processes.read(pane.id, None)
    except KeyError:
        return list(pane.output)
    _update_status_from_screen(pane, plain)
    if styled:
        try:
            rendered = processes.render_styled(pane.id, cursor=cursor)
        except KeyError:
            rendered = plain
        return rendered.split("\n") if rendered else []
    return plain.split("\n") if plain else []


def _capture_limit(value: Any) -> int | None:
    """Coerce a ``lines`` param into a tail size; ``None``/blank/negative means all."""
    if value is None or value == "":
        return None
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    return limit if limit >= 0 else None


def _pane_run(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    pane = state.require_pane(_required(params, "pane_id"))
    command = _required(params, "command")
    pane.command = command
    pane.status = AgentStatus.WORKING
    pane.append_output(f"$ {command}")
    process = subprocess.run(
        command,
        cwd=pane.cwd or None,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    pane.append_output(process.stdout or "")
    joined = "\n".join(pane.output)
    run_agent = identify_agent_in_command(command)
    pane.status = detect(run_agent, joined).state if run_agent else detect_agent_status(joined)
    if process.returncode != 0:
        pane.status = AgentStatus.BLOCKED
    elif pane.status not in (AgentStatus.BLOCKED, AgentStatus.WORKING):
        pane.status = AgentStatus.DONE
    pane.append_output(f"[exit {process.returncode}]")
    workspace_id, tab_id = _pane_context(state, pane.id)
    return {
        "type": "pane_run",
        "pane": _pane_record(pane, workspace_id, tab_id),
        "exit_code": process.returncode,
    }


def _pane_start(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("pane.start requires a server process manager")
    pane = state.require_pane(_required(params, "pane_id"))
    command = _required(params, "command")
    started = processes.start(pane.id, command, pane.cwd)
    # Only relabel the pane if a session was actually started; a False return
    # means one was already running and we must not clobber its metadata.
    if started:
        pane.command = command
        detected_agent = identify_agent_in_command(command)
        pane.agent = detected_agent.value if detected_agent else ""
        pane.status = AgentStatus.WORKING
    workspace_id, tab_id = _pane_context(state, pane.id)
    return {
        "type": "pane_start",
        "started": started,
        "pane": _pane_record(pane, workspace_id, tab_id),
    }


def _pane_send_text(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("pane.send_text requires a server process manager")
    pane = state.require_pane(_required(params, "pane_id"))
    text = str(params.get("text") or "")
    processes.send_text(pane.id, text)
    tab = _tab_for_pane(state, pane.id)
    if tab is not None and tab.synchronized:
        processes.broadcast([sibling.id for sibling in tab.panes if sibling.id != pane.id], text)
    return {"type": "pane_send_text", "pane_id": pane.id, "bytes": len(text.encode("utf-8"))}


def _pane_send_key(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("pane.send_key requires a server process manager")
    pane = state.require_pane(_required(params, "pane_id"))
    key = _required(params, "key")
    processes.send_key(pane.id, key)
    return {"type": "pane_send_key", "pane_id": pane.id, "key": key}


def _pane_resize(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("pane.resize requires a server process manager")
    pane = state.require_pane(_required(params, "pane_id"))
    rows = int(params.get("rows") or 24)
    cols = int(params.get("cols") or 80)
    if rows <= 0 or cols <= 0:
        raise ValueError("pane.resize requires positive rows and cols")
    processes.resize(pane.id, rows, cols)
    return {"type": "pane_resize", "pane_id": pane.id, "rows": rows, "cols": cols}


def _pane_stop(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("pane.stop requires a server process manager")
    pane = state.require_pane(_required(params, "pane_id"))
    stopped = processes.stop(pane.id)
    if stopped:
        pane.status = AgentStatus.IDLE
    return {"type": "pane_stop", "pane_id": pane.id, "stopped": stopped}


def _pane_report_agent(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    pane = state.require_pane(_required(params, "pane_id"))
    pane.status = AgentStatus(str(params.get("state") or AgentStatus.UNKNOWN.value))
    pane.custom_status = str(params.get("custom_status") or params.get("message") or "")
    workspace_id, tab_id = _pane_context(state, pane.id)
    return {"type": "pane_agent_reported", "pane": _pane_record(pane, workspace_id, tab_id)}


def _resolve_agent(state: AppState, target: str) -> tuple[Pane, str, str]:
    """Resolve an agent target (pane id, agent label, or pane title) to a pane."""
    for workspace in state.workspaces:
        for tab in workspace.tabs:
            for pane in tab.panes:
                if pane.id == target:
                    return pane, workspace.id, tab.id
    lowered = target.strip().lower()
    for workspace in state.workspaces:
        for tab in workspace.tabs:
            for pane in tab.panes:
                if pane.agent.lower() == lowered or pane.title.lower() == lowered:
                    return pane, workspace.id, tab.id
    raise KeyError(f"agent not found: {target}")


def _agent_list(state: AppState, _params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    agents = [
        _pane_record(pane, workspace.id, tab.id)
        for workspace in state.workspaces
        for tab in workspace.tabs
        for pane in tab.panes
        if pane.agent
    ]
    return {"type": "agent_list", "agents": agents}


def _agent_get(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    pane, workspace_id, tab_id = _resolve_agent(state, _required(params, "target"))
    return {"type": "agent_info", "agent": _pane_record(pane, workspace_id, tab_id)}


def _agent_read(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    pane, _workspace_id, _tab_id = _resolve_agent(state, _required(params, "target"))
    lines = int(params.get("lines") or 80)
    if processes is not None:
        try:
            output = processes.read(pane.id, lines)
        except KeyError:
            output = "\n".join(pane.output[-lines:])
        else:
            _update_status_from_screen(pane, output)
    else:
        output = "\n".join(pane.output[-lines:])
    return {"type": "agent_read", "pane_id": pane.id, "output": output}


def _agent_send(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("agent.send requires a server process manager")
    pane, _workspace_id, _tab_id = _resolve_agent(state, _required(params, "target"))
    text = str(params.get("text") or "")
    processes.send_text(pane.id, text)
    return {"type": "agent_send", "pane_id": pane.id, "bytes": len(text.encode("utf-8"))}


def _agent_rename(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    pane, workspace_id, tab_id = _resolve_agent(state, _required(params, "target"))
    pane.title = str(params.get("name") or pane.title)
    return {"type": "agent_renamed", "agent": _pane_record(pane, workspace_id, tab_id)}


def _agent_focus(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    pane, workspace_id, tab_id = _resolve_agent(state, _required(params, "target"))
    state.focused_workspace_id = workspace_id
    workspace = state.require_workspace(workspace_id)
    workspace.focused_tab_id = tab_id
    state.require_tab(workspace_id, tab_id).focused_pane_id = pane.id
    return {"type": "agent_focused", "agent": _pane_record(pane, workspace_id, tab_id)}


def _agent_start(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("agent.start requires a server process manager")
    name = _required(params, "name")
    command = str(params.get("command") or name)
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id or "")
    workspace = state.require_workspace(workspace_id)
    tab_id = params.get("tab_id")
    if tab_id:
        tab = state.require_tab(workspace.id, str(tab_id))
    else:
        focused = workspace.focused_tab
        if focused is None:
            raise ValueError("workspace has no tab for the new agent")
        tab = focused
    pane = state.create_pane(workspace.id, tab.id, title=name)
    if params.get("cwd"):
        pane.cwd = str(params["cwd"])
    started = processes.start(pane.id, command, pane.cwd)
    detected = identify_agent_in_command(command)
    pane.agent = detected.value if detected else name
    pane.command = command
    pane.status = AgentStatus.WORKING
    record_workspace_id, record_tab_id = _pane_context(state, pane.id)
    return {
        "type": "agent_started",
        "started": started,
        "agent": _pane_record(pane, record_workspace_id, record_tab_id),
    }


def _session_record(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    """Record a point-in-time session artifact for replay/debug workflows."""
    line_limit = _capture_limit(params.get("lines"))
    styled = bool(params.get("styled"))

    def capture(pane: Pane) -> dict[str, Any]:
        capture_params = {"pane_id": pane.id, "lines": line_limit, "styled": styled}
        return _pane_capture(state, capture_params, processes)

    recording = build_session_recording(state, capture)
    output = str(params.get("output") or params.get("path") or "")
    written: Path | None = None
    if output:
        written = write_session_recording(recording, Path(output))
    return {
        "type": "session_recording",
        "version": recording["version"],
        "session": recording["session"],
        "path": str(written) if written else "",
        "pane_count": count_recorded_panes(recording),
        "timeline_count": len(recording.get("timeline", [])),
        "recording": recording,
    }


def _panes_in_scope(state: AppState, scope: str) -> list[str]:
    focused = state.focused_workspace
    ids: list[str] = []
    for workspace in state.workspaces:
        if scope == "workspace" and (focused is None or workspace.id != focused.id):
            continue
        for tab in workspace.tabs:
            if scope == "tab":
                focused_tab = focused.focused_tab if focused else None
                if focused_tab is None or tab.id != focused_tab.id:
                    continue
            ids.extend(pane.id for pane in tab.panes)
    return ids


def _tab_for_pane(state: AppState, pane_id: str) -> Tab | None:
    for workspace in state.workspaces:
        for tab in workspace.tabs:
            if any(pane.id == pane_id for pane in tab.panes):
                return tab
    return None


def _pane_broadcast(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("pane.broadcast requires a server process manager")
    text = _required(params, "text")
    if params.get("enter", True):
        text = text + "\n"
    scope = str(params.get("scope") or "all")
    pane_ids = _panes_in_scope(state, scope)
    sent = processes.broadcast(pane_ids, text)
    return {"type": "pane_broadcast", "scope": scope, "targets": len(pane_ids), "sent": sent}


def _pane_fanout(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    text = _required(params, "text")
    targets = _param_list(params.get("targets"))
    if not targets:
        raise ValueError("pane.fanout requires at least one target")
    enter = _param_bool(params.get("enter"), default=True)
    dry_run = _param_bool(params.get("dry_run"), default=True)
    target_records = _resolve_fanout_targets(state, targets)
    if not target_records:
        raise ValueError("fanout targets matched no panes")
    pane_ids = [record["pane_id"] for record in target_records]
    payload = text + ("\n" if enter else "")
    risk = _fanout_risk(text) if len(target_records) > 1 else ""
    requires_confirmation = bool(risk)
    confirmed = _param_bool(params.get("confirm_risky") or params.get("require_confirm"), default=False)
    sent = 0
    if not dry_run:
        if requires_confirmation and not confirmed:
            raise ValueError(f"pane.fanout risky command requires confirm_risky: {risk}")
        if processes is None:
            raise ValueError("pane.fanout execute requires a server process manager")
        sent = processes.broadcast(pane_ids, payload)
    return {
        "type": "pane_fanout",
        "dry_run": dry_run,
        "enter": enter,
        "target_count": len(target_records),
        "requires_confirmation": requires_confirmation,
        "risk": risk,
        "targets": target_records,
        "sent": sent,
        "bytes": len(payload.encode("utf-8")),
    }


def _resolve_fanout_targets(state: AppState, selectors: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for selector in selectors:
        for pane, workspace, tab in _iter_fanout_matches(state, selector):
            if pane.id in seen:
                continue
            seen.add(pane.id)
            record = _pane_record(pane, workspace.id, tab.id)
            record["workspace_label"] = workspace.label
            record["tab_label"] = tab.label
            records.append(record)
    return records


def _iter_fanout_matches(state: AppState, selector: str):
    normalized = selector.strip()
    if not normalized:
        return []
    if normalized.lower() == "all":
        kind, value = "all", ""
    elif ":" in normalized:
        kind, value = normalized.split(":", 1)
        kind = kind.strip().lower()
        value = value.strip()
    else:
        kind, value = "pane", normalized
    if kind == "all":
        return list(_iter_pane_contexts(state))
    if kind == "session":
        current = current_session().lower()
        if value.lower() in ("", "*", "current", current):
            return list(_iter_pane_contexts(state))
        return []
    if kind == "workspace":
        return [
            item
            for item in _iter_pane_contexts(state)
            if _matches_identity(item[1].id, item[1].label, value)
        ]
    if kind == "tab":
        return [
            item
            for item in _iter_pane_contexts(state)
            if _matches_identity(item[2].id, item[2].label, value)
        ]
    if kind == "pane":
        return [item for item in _iter_pane_contexts(state) if item[0].id == value]
    if kind == "agent":
        return [
            item
            for item in _iter_pane_contexts(state)
            if item[0].agent.lower() == value.lower() or item[0].title.lower() == value.lower()
        ]
    raise ValueError(f"unknown fanout target selector: {kind}")


_RISKY_FANOUT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brm\s+-[^\n;&|]*[rf][^\n;&|]*[rf]\b", re.IGNORECASE), "recursive force remove"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE), "hard git reset"),
    (re.compile(r"\bgit\s+clean\s+-[^\n;&|]*[fd][^\n;&|]*[fd]\b", re.IGNORECASE), "force git clean"),
    (re.compile(r"\bremove-item\b[^\n;&|]*\b-recurse\b", re.IGNORECASE), "recursive remove-item"),
    (re.compile(r"\bdel(?:ete)?\b[^\n;&|]*/[sq]\b", re.IGNORECASE), "recursive/silent delete"),
    (re.compile(r"\brmdir\b[^\n;&|]*/s\b", re.IGNORECASE), "recursive directory delete"),
    (re.compile(r"\bdocker\s+system\s+prune\b", re.IGNORECASE), "docker system prune"),
    (re.compile(r"\bterraform\s+destroy\b", re.IGNORECASE), "terraform destroy"),
    (re.compile(r"\bkubectl\s+delete\b", re.IGNORECASE), "kubectl delete"),
)


def _fanout_risk(text: str) -> str:
    for pattern, reason in _RISKY_FANOUT_PATTERNS:
        if pattern.search(text):
            return reason
    return ""


def _iter_pane_contexts(state: AppState):
    for workspace in state.workspaces:
        for tab in workspace.tabs:
            for pane in tab.panes:
                yield pane, workspace, tab


def _matches_identity(identifier: str, label: str, value: str) -> bool:
    return identifier == value or label.lower() == value.lower()


def _param_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    raise ValueError("targets must be a string or list of strings")


def _param_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    return bool(value)


def _tab_sync(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    workspace_id = str(params.get("workspace_id") or state.focused_workspace_id)
    workspace = state.require_workspace(workspace_id)
    tab_id = params.get("tab_id")
    if tab_id:
        tab = state.require_tab(workspace.id, str(tab_id))
    else:
        focused = workspace.focused_tab
        if focused is None:
            raise ValueError("workspace has no tab to synchronize")
        tab = focused
    tab.synchronized = bool(params.get("enabled", True))
    return {"type": "tab_sync", "tab_id": tab.id, "synchronized": tab.synchronized}


def _schedule_record(schedule) -> dict[str, Any]:
    return {
        "id": schedule.id,
        "cron": schedule.cron,
        "pane_id": schedule.pane_id,
        "command": schedule.command,
        "enabled": schedule.enabled,
    }


def _schedule_add(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    cron = _required(params, "cron")
    pane_id = _required(params, "pane_id")
    command = _required(params, "command")
    parse_cron(cron)  # validate; raises ValueError on a bad expression
    schedule = state.add_schedule(cron, pane_id, command)
    return {"type": "schedule_added", "schedule": _schedule_record(schedule)}


def _schedule_list(state: AppState, _params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    return {"type": "schedule_list", "schedules": [_schedule_record(item) for item in state.schedules]}


def _schedule_remove(state: AppState, params: dict[str, Any], _processes: TerminalManager | None) -> dict[str, Any]:
    schedule_id = _required(params, "id")
    return {"type": "schedule_removed", "id": schedule_id, "removed": state.remove_schedule(schedule_id)}


def _schedule_run(state: AppState, params: dict[str, Any], processes: TerminalManager | None) -> dict[str, Any]:
    if processes is None:
        raise ValueError("schedule.run requires a server process manager")
    schedule_id = _required(params, "id")
    schedule = next((item for item in state.schedules if item.id == schedule_id), None)
    if schedule is None:
        raise KeyError(f"schedule not found: {schedule_id}")
    processes.send_text(schedule.pane_id, schedule.command + ("\r" if schedule.send_enter else ""))
    return {"type": "schedule_run", "id": schedule.id}


def _workspace_record(workspace) -> dict[str, Any]:
    return {
        "workspace_id": workspace.id,
        "label": workspace.label,
        "cwd": workspace.cwd,
        "status": workspace.status.value,
        "focused_tab_id": workspace.focused_tab_id,
    }


def _tab_record(tab) -> dict[str, Any]:
    return {
        "tab_id": tab.id,
        "label": tab.label,
        "status": tab.status.value,
        "focused_pane_id": tab.focused_pane_id,
        "pane_count": len(tab.panes),
    }


def _pane_record(pane, workspace_id: str, tab_id: str) -> dict[str, Any]:
    location = "remote" if pane.remote_host else "local"
    display_cwd = f"{pane.remote_host}:{pane.remote_cwd or pane.cwd}" if pane.remote_host else pane.cwd
    return {
        "pane_id": pane.id,
        "workspace_id": workspace_id,
        "tab_id": tab_id,
        "title": pane.title,
        "cwd": pane.cwd,
        "location": location,
        "remote_host": pane.remote_host,
        "remote_cwd": pane.remote_cwd,
        "display_cwd": display_cwd,
        "command": pane.command,
        "agent": pane.agent,
        "agent_status": pane.status.value,
        "custom_status": pane.custom_status,
        "output_lines": len(pane.output),
    }


def _pane_context(state: AppState, pane_id: str) -> tuple[str, str]:
    for workspace in state.workspaces:
        for tab in workspace.tabs:
            for pane in tab.panes:
                if pane.id == pane_id:
                    return workspace.id, tab.id
    raise KeyError(f"pane not found: {pane_id}")


def _required(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if value is None or value == "":
        raise ValueError(f"missing required param: {key}")
    return str(value)
