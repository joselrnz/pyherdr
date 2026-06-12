"""Client used by the UIs to talk to the PyHerdr server.

`ServerClient` speaks the real JSON protocol (auto-starting the server). The
`PaneClient` protocol lets tests inject a fake without a running server.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from ..server import ServerInfo, request, start_background


class PaneClient(Protocol):
    """The minimal server surface the UIs need."""

    def state(self) -> dict[str, Any]:
        """Return the full session state tree."""
        ...

    def stats(self) -> dict[str, Any]:
        """Return the latest resource snapshot ``{available, stats: {pane_id: …}}``."""
        ...

    def pane_read(self, pane_id: str, lines: int = 200, styled: bool = False, cursor: bool = False) -> str:
        """Return the rendered screen for a pane (ANSI-styled when ``styled``)."""
        ...

    def pane_wait_output(self, versions: dict[str, int], timeout: float = 1.0) -> dict[str, Any]:
        """Wait until any watched pane has a newer output generation."""
        ...

    def pane_terminal_metadata(self, pane_id: str) -> dict[str, bool]:
        """Return terminal mode metadata from the latest pane read."""
        ...

    def send_text(self, pane_id: str, text: str) -> None:
        """Type text into a pane."""
        ...

    def send_key(self, pane_id: str, key: str) -> None:
        """Send a named key to a pane."""
        ...

    def pane_scroll(self, pane_id: str, direction: str) -> None:
        """Scroll a pane through its scrollback ('up' shows older output)."""
        ...

    def create_tab(self, label: str = "shell") -> dict[str, Any]:
        """Create a new tab (with a pane) in the focused workspace."""
        ...

    def create_pane(self, title: str = "pane") -> dict[str, Any]:
        """Create a new pane in the focused tab."""
        ...

    def split_pane(self, direction: str = "horizontal") -> dict[str, Any]:
        """Split the focused pane ('horizontal' = side-by-side, 'vertical' = stacked)."""
        ...

    def set_layout(self, layout: dict[str, Any]) -> dict[str, Any]:
        """Persist a new split-tree layout for the focused tab."""
        ...

    def start_pane(self, pane_id: str, command: str) -> None:
        """Start a command on the pane's terminal."""
        ...

    def create_workspace(self, label: str = "workspace", cwd: str = ".") -> None:
        """Create a new workspace."""
        ...

    def move_workspace(self, workspace_id: str, direction: str) -> dict[str, Any]:
        """Move a workspace up or down in the sidebar list."""
        ...

    def focus_workspace(self, workspace_id: str) -> dict[str, Any]:
        """Tell the server which workspace is focused (keeps scoped ops correct)."""
        ...

    def focus_tab(self, tab_id: str) -> dict[str, Any]:
        """Tell the server which tab is focused in the focused workspace."""
        ...

    def rename_workspace(self, workspace_id: str, label: str) -> dict[str, Any]:
        """Rename a workspace."""
        ...

    def close_workspace(self, workspace_id: str) -> dict[str, Any]:
        """Close a workspace."""
        ...

    def close_pane(self, pane_id: str) -> None:
        """Close a pane."""
        ...

    def close_tab(self, tab_id: str) -> None:
        """Close a tab."""
        ...

    def rename_tab(self, tab_id: str, label: str) -> dict[str, Any]:
        """Rename a tab."""
        ...

    def move_tab(self, tab_id: str, direction: str) -> dict[str, Any]:
        """Move a tab left or right among its siblings."""
        ...

    def pane_fanout(
        self,
        targets: list[str],
        text: str,
        *,
        enter: bool = True,
        dry_run: bool = True,
        confirm_risky: bool = False,
    ) -> dict[str, Any]:
        """Preview or send text to panes selected by fan-out target selectors."""
        ...


class ServerClient:
    """`PaneClient` backed by the PyHerdr server over the local socket."""

    def __init__(self) -> None:
        self._terminal_metadata: dict[str, dict[str, bool]] = {}
        self._server_info: ServerInfo | None = None

    def _request(self, method: str, **params: Any) -> dict[str, Any]:
        payload = {"id": "tui", "method": method, "params": params}
        info = self._server_info
        if info is None:
            info = start_background()
            self._server_info = info
        try:
            return request(info, payload)
        except (OSError, ConnectionError, TimeoutError, json.JSONDecodeError):
            info = start_background()
            self._server_info = info
            return request(info, payload)

    def state(self) -> dict[str, Any]:
        response = self._request("state.get")
        return response.get("result", {}).get("state", {"workspaces": []})

    def stats(self) -> dict[str, Any]:
        response = self._request("stats.get")
        return response.get("result", {"available": False, "stats": {}})

    def pane_read(self, pane_id: str, lines: int = 200, styled: bool = False, cursor: bool = False) -> str:
        response = self._request("pane.read", pane_id=pane_id, lines=lines, styled=styled, cursor=cursor)
        result = response.get("result", {})
        terminal = result.get("terminal", {})
        if isinstance(terminal, dict):
            self._terminal_metadata[pane_id] = {
                "alt_screen": bool(terminal.get("alt_screen")),
                "mouse_reporting": bool(terminal.get("mouse_reporting")),
            }
        return result.get("output", "")

    def pane_terminal_metadata(self, pane_id: str) -> dict[str, bool]:
        return self._terminal_metadata.get(pane_id, {"alt_screen": False, "mouse_reporting": False})

    def pane_wait_output(self, versions: dict[str, int], timeout: float = 1.0) -> dict[str, Any]:
        response = self._request("pane.wait_output", versions=versions, timeout=timeout)
        return response.get("result", {"changed": {}, "versions": {}, "timed_out": True})

    def send_text(self, pane_id: str, text: str) -> None:
        self._request("pane.send_text", pane_id=pane_id, text=text)

    def send_key(self, pane_id: str, key: str) -> None:
        self._request("pane.send_key", pane_id=pane_id, key=key)

    def pane_scroll(self, pane_id: str, direction: str) -> None:
        self._request("pane.scroll", pane_id=pane_id, direction=direction)

    def create_tab(self, label: str = "shell") -> dict[str, Any]:
        return self._request("tab.create", label=label)

    def create_pane(self, title: str = "pane") -> dict[str, Any]:
        return self._request("pane.create", title=title)

    def split_pane(self, direction: str = "horizontal") -> dict[str, Any]:
        return self._request("pane.split", direction=direction)

    def set_layout(self, layout: dict[str, Any]) -> dict[str, Any]:
        return self._request("pane.set_layout", layout=layout)

    def start_pane(self, pane_id: str, command: str) -> None:
        self._request("pane.start", pane_id=pane_id, command=command)

    def create_workspace(self, label: str = "workspace", cwd: str = ".") -> None:
        self._request("workspace.create", label=label, cwd=cwd)

    def move_workspace(self, workspace_id: str, direction: str) -> dict[str, Any]:
        return self._request("workspace.move", workspace_id=workspace_id, direction=direction)

    def focus_workspace(self, workspace_id: str) -> dict[str, Any]:
        return self._request("workspace.focus", workspace_id=workspace_id)

    def focus_tab(self, tab_id: str) -> dict[str, Any]:
        return self._request("tab.focus", tab_id=tab_id)

    def rename_workspace(self, workspace_id: str, label: str) -> dict[str, Any]:
        return self._request("workspace.rename", workspace_id=workspace_id, label=label)

    def close_workspace(self, workspace_id: str) -> dict[str, Any]:
        return self._request("workspace.close", workspace_id=workspace_id)

    def close_pane(self, pane_id: str) -> None:
        self._request("pane.close", pane_id=pane_id)

    def close_tab(self, tab_id: str) -> None:
        self._request("tab.close", tab_id=tab_id)

    def rename_tab(self, tab_id: str, label: str) -> dict[str, Any]:
        return self._request("tab.rename", tab_id=tab_id, label=label)

    def move_tab(self, tab_id: str, direction: str) -> dict[str, Any]:
        return self._request("tab.move", tab_id=tab_id, direction=direction)

    def pane_fanout(
        self,
        targets: list[str],
        text: str,
        *,
        enter: bool = True,
        dry_run: bool = True,
        confirm_risky: bool = False,
    ) -> dict[str, Any]:
        response = self._request(
            "pane.fanout",
            targets=targets,
            text=text,
            enter=enter,
            dry_run=dry_run,
            confirm_risky=confirm_risky,
        )
        return response.get("result", {})
