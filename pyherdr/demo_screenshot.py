from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from textual.widgets import Input

from .presentation.tui import Activated, DirPickerScreen, DirRepoMetadata, FanoutScreen, PyHerdrTui, WorkflowScreen
from .workflow import new_event
from .workspace_search import SearchRoot

DEMO_STATE: dict[str, Any] = {
    "focused_workspace_id": "ws-main",
    "workspaces": [
        {
            "id": "ws-main",
            "label": "pyherdr / main",
            "cwd": ".",
            "focused_tab_id": "tab-agents",
            "tabs": [
                {
                    "id": "tab-agents",
                    "label": "agents",
                    "focused_pane_id": "pane-loop",
                    "panes": [
                        {
                            "id": "pane-loop",
                            "title": "Codex loop",
                            "status": "working",
                            "running": True,
                            "agent": "codex",
                        },
                        {"id": "pane-ci", "title": "CI scope", "status": "done", "running": True},
                        {"id": "pane-tests", "title": "validation", "status": "done", "running": True},
                    ],
                    "layout": {
                        "root": {
                            "kind": "split",
                            "direction": "horizontal",
                            "ratio": 0.58,
                            "first": {"kind": "pane", "pane_id": "pane-loop"},
                            "second": {
                                "kind": "split",
                                "direction": "vertical",
                                "ratio": 0.52,
                                "first": {"kind": "pane", "pane_id": "pane-ci"},
                                "second": {"kind": "pane", "pane_id": "pane-tests"},
                            },
                        },
                        "focus": "pane-loop",
                    },
                },
                {
                    "id": "tab-roadmap",
                    "label": "mega-plan",
                    "focused_pane_id": "pane-plan",
                    "panes": [{"id": "pane-plan", "title": "roadmap", "status": "idle", "running": True}],
                },
                {
                    "id": "tab-logs",
                    "label": "logs",
                    "focused_pane_id": "pane-log",
                    "panes": [{"id": "pane-log", "title": "server log", "status": "idle", "running": True}],
                },
            ],
        },
        {
            "id": "ws-ghostc",
            "label": "ghostc / plugin",
            "cwd": "C:/work/ghostc-plugin",
            "focused_tab_id": "tab-review",
            "tabs": [
                {
                    "id": "tab-review",
                    "label": "review",
                    "focused_pane_id": "pane-review",
                    "panes": [
                        {
                            "id": "pane-review",
                            "title": "approval gate",
                            "status": "blocked",
                            "running": True,
                            "agent": "claude",
                        }
                    ],
                }
            ],
        },
    ],
}

DEMO_OUTPUTS = {
    "pane-loop": """$ codex implement next slice
PyHerdr graduation loop

Rendered by the real PyHerdr Textual TUI.
Pane contents are demo data.

Try the live product with:
  pyherdr tui

Completed demo cycle:
- CI scope matches local rules
- PTY/socket cleanup validated
- roadmap status visible

Next:
WS-006 Slow Task Investigation
or WS-007 Layout Node Model
""",
    "pane-ci": """$ git diff -- .github/workflows/ci.yml

- python -m ruff check pyherdr tests
+ python -m ruff check pyherdr tools tests

CI now matches CLAUDE.md.
""",
    "pane-tests": """$ .\\.venv\\Scripts\\python.exe -m ruff check pyherdr tools tests
All checks passed!

$ .\\.venv\\Scripts\\python.exe -m mypy
Success: no issues found in 41 source files

$ .\\.venv\\Scripts\\python.exe -m unittest discover -s tests
Ran 132 tests

OK
""",
    "pane-plan": """# PyHerdr Mega Plan
Lane A: GUI Parity And Product Surface
Lane D: Zmux-Class Multiplexing
Lane E: GhostC-Class Product Polish

This screenshot is a reproducible demo render.
""",
    "pane-log": """[server] demo client loaded
[tui] Textual screenshot exported
[note] no live agents are started by this command
""",
}

DEMO_WORKFLOW_EVENTS = [
    new_event(
        "api.request",
        message="pane read",
        source="tui",
        target="server",
        worksite="WS-121",
        agent="codex",
        pane_id="pane-loop",
        status="done",
        event_id="demo-workflow-1",
        timestamp=1_786_240_800.0,
    ),
    new_event(
        "api.response",
        message="pane data returned",
        source="server",
        target="tui",
        worksite="WS-121",
        agent="codex",
        pane_id="pane-loop",
        status="done",
        event_id="demo-workflow-1b",
        timestamp=1_786_240_830.0,
    ),
    new_event(
        "agent.status",
        message="approval gate blocked",
        source="claude",
        target="main",
        worksite="WS-121",
        agent="claude",
        pane_id="pane-review",
        status="blocked",
        artifacts=["workflow.mmd"],
        event_id="demo-workflow-2",
        timestamp=1_786_240_860.0,
    ),
    new_event(
        "validation",
        message="ruff mypy unittest passed",
        source="codex",
        target="ci",
        worksite="WS-089",
        agent="codex",
        pane_id="pane-tests",
        status="done",
        artifacts=["validation.log"],
        event_id="demo-workflow-3",
        timestamp=1_786_240_920.0,
    ),
]


DEMO_PICKER_ROOT = "C:/Users/josel/github/pyherdr"
DEMO_SCREENSHOT_VIEWS = (
    "main",
    "workflow",
    "fanout",
    "workspace-picker",
    "workspace-search",
    "workspace-search-selected",
    "workspace-search-stale",
    "workspace-search-long-path",
)


class DemoDirPickerScreen(DirPickerScreen):
    """Deterministic workspace picker data for screenshot exports."""

    def __init__(self) -> None:
        super().__init__(".", lambda path: None)
        self._cwd = DEMO_PICKER_ROOT
        self._quick_paths = [
            ("current workspace", DEMO_PICKER_ROOT),
            ("repo root", DEMO_PICKER_ROOT),
            ("recent: ghostc-plugin", "C:/work/ghostc-plugin"),
            ("process cwd", DEMO_PICKER_ROOT),
            ("home", "C:/Users/josel"),
        ]

    def _subdirs(self) -> list[str]:
        return ["assets", "dist", "pyherdr", "tests", "tools"]

    def _repo_metadata(self) -> DirRepoMetadata:
        return DirRepoMetadata(repo_root=DEMO_PICKER_ROOT, branch="main", dirty=True)


class DemoScreenshotClient:
    """PaneClient implementation that feeds the TUI a deterministic demo state."""

    def state(self) -> dict[str, Any]:
        return DEMO_STATE

    def stats(self) -> dict[str, Any]:
        return {
            "available": True,
            "stats": {
                "pane-loop": {"cpu_percent": 3.2, "memory_mb": 210.0},
                "pane-ci": {"cpu_percent": 0.0, "memory_mb": 32.0},
                "pane-tests": {"cpu_percent": 0.0, "memory_mb": 48.0},
            },
        }

    def pane_read(self, pane_id: str, lines: int = 200, styled: bool = False, cursor: bool = False) -> str:
        return DEMO_OUTPUTS.get(pane_id, "")

    def pane_wait_output(self, versions: dict[str, int], timeout: float = 1.0) -> dict[str, Any]:
        return {"type": "pane_output_wait", "changed": {}, "versions": versions, "timed_out": True}

    def send_text(self, pane_id: str, text: str) -> None:
        return None

    def send_key(self, pane_id: str, key: str) -> None:
        return None

    def pane_scroll(self, pane_id: str, direction: str) -> None:
        return None

    def create_tab(self, label: str = "shell") -> dict[str, Any]:
        return {"result": {"tab": {"focused_pane_id": "new-pane"}}}

    def create_pane(self, title: str = "pane") -> dict[str, Any]:
        return {"result": {"pane": {"pane_id": "new-pane"}}}

    def split_pane(self, direction: str = "horizontal") -> dict[str, Any]:
        return {"result": {"pane": {"pane_id": "new-pane"}}}

    def set_layout(self, layout: dict[str, Any]) -> dict[str, Any]:
        return {"result": {"type": "pane_layout_set"}}

    def start_pane(self, pane_id: str, command: str) -> None:
        return None

    def create_workspace(self, label: str = "workspace", cwd: str = ".") -> None:
        return None

    def move_workspace(self, workspace_id: str, direction: str) -> dict[str, Any]:
        return {"result": {"type": "workspace_moved"}}

    def focus_workspace(self, workspace_id: str) -> dict[str, Any]:
        return {"result": {"type": "workspace_focused"}}

    def focus_tab(self, tab_id: str) -> dict[str, Any]:
        return {"result": {"type": "tab_focused"}}

    def rename_workspace(self, workspace_id: str, label: str) -> dict[str, Any]:
        return {"result": {"type": "workspace_renamed"}}

    def close_workspace(self, workspace_id: str) -> dict[str, Any]:
        return {"result": {"type": "workspace_closed"}}

    def close_pane(self, pane_id: str) -> None:
        return None

    def close_tab(self, tab_id: str) -> None:
        return None

    def rename_tab(self, tab_id: str, label: str) -> dict[str, Any]:
        return {"result": {"type": "tab_renamed"}}

    def move_tab(self, tab_id: str, direction: str) -> dict[str, Any]:
        return {"result": {"type": "tab_moved"}}

    def pane_fanout(
        self,
        targets: list[str],
        text: str,
        *,
        enter: bool = True,
        dry_run: bool = True,
        confirm_risky: bool = False,
    ) -> dict[str, Any]:
        selector = targets[0] if targets else ""
        records = []
        for workspace in DEMO_STATE["workspaces"]:
            for tab in workspace.get("tabs", []):
                for pane in tab.get("panes", []):
                    matches = (
                        "all",
                        f"workspace:{workspace.get('id')}",
                        f"tab:{tab.get('id')}",
                        f"pane:{pane.get('id')}",
                        f"agent:{pane.get('agent')}",
                    )
                    if selector in matches:
                        records.append(
                            {
                                "pane_id": pane.get("id"),
                                "workspace_label": workspace.get("label"),
                                "tab_label": tab.get("label"),
                                "title": pane.get("title"),
                                "status": pane.get("status"),
                            }
                        )
        return {
            "type": "pane_fanout",
            "dry_run": dry_run,
            "enter": enter,
            "target_count": len(records),
            "requires_confirmation": False,
            "risk": "",
            "targets": records,
            "sent": 0 if dry_run else len(records),
            "bytes": len((text + ("\n" if enter else "")).encode("utf-8")),
        }


async def _open_workspace_search_demo(app: PyHerdrTui, pilot: Any, view: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        search_roots = _prepare_workspace_search_fixture(root, view)
        app.push_screen(
            DirPickerScreen(
                str(root),
                lambda selected: None,
                search_roots=search_roots,
                search_debounce=0,
                search_max_depth=6,
            )
        )
        await pilot.pause(0.5)
        if isinstance(app.screen, DirPickerScreen):
            key_event = type(
                "Key",
                (),
                {"key": "ctrl+f", "stop": lambda self: None, "prevent_default": lambda self: None},
            )()
            app.screen.on_key(key_event)
            app.screen.query_one("#dir-jump", Input).value = "pyherdr"
            await app.screen.on_input_changed(type("Changed", (), {"value": "pyherdr"})())
            for _ in range(10):
                await asyncio.sleep(0.1)
                if app.screen._search_rows:
                    break
            if view == "workspace-search-selected" and app.screen._search_rows:
                app.screen._toggle_active_search_row()
                await app.screen._populate()
                await pilot.pause(0.2)
        await pilot.pause(0.2)


def _prepare_workspace_search_fixture(root: Path, view: str) -> list[SearchRoot]:
    if view == "workspace-search-stale":
        missing = root / "pyherdr-missing"
        return [SearchRoot(str(missing), label="pyherdr-missing", source="recent")]
    if view == "workspace-search-long-path":
        repo = (
            root
            / "enterprise-platform-with-a-very-long-name"
            / "customers"
            / "regional-command-center"
            / "pyherdr-operations-console"
        )
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()
        return [SearchRoot(str(root), label="long path roots", source="workspace")]
    repo = root / "pyherdr-demo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (root / "pyherdr-docs").mkdir()
    (root / "node_modules" / "pyherdr-hidden").mkdir(parents=True)
    return [SearchRoot(str(root), label="demo roots", source="workspace")]


async def _render(path: Path, width: int, height: int, view: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    app = PyHerdrTui(client=DemoScreenshotClient(), poll_interval=100)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause(0.5)
        if view == "workflow":
            app.push_screen(WorkflowScreen(DEMO_WORKFLOW_EVENTS, app._palette))
            await pilot.pause(0.5)
        elif view == "fanout":
            app._open_fanout_picker()
            await pilot.pause(0.5)
            if isinstance(app.screen, FanoutScreen):
                app.screen.query_one("#fanout-command", Input).value = "pytest -q"
                app.screen.on_activated(Activated("fanout_target", "1"))
                await pilot.pause(0.5)
        elif view == "workspace-picker":
            app.push_screen(DemoDirPickerScreen())
            await pilot.pause(0.5)
        elif view.startswith("workspace-search"):
            await _open_workspace_search_demo(app, pilot, view)
            await pilot.pause(0.5)
        path.write_text(app.export_screenshot(title="PyHerdr demo TUI", simplify=False), encoding="utf-8")
    return path


def render_demo_screenshot(path: Path, *, width: int = 132, height: int = 38, view: str = "main") -> Path:
    """Render the real Textual TUI with deterministic demo data to an SVG file."""

    normalized = view.strip().lower()
    if normalized not in DEMO_SCREENSHOT_VIEWS:
        raise ValueError(f"unknown demo screenshot view: {view}")
    return asyncio.run(_render(path, width, height, normalized))
