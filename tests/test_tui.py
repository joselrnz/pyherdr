import json
import threading
import time
import unittest
from unittest.mock import patch

from pyherdr.config import Config, ProfileConfig, UiConfig, WorkflowConfig
from pyherdr.launchers import LauncherPreset
from pyherdr.presentation.tui import (
    CommandPaletteScreen,
    ContextMenuScreen,
    CopyModeScreen,
    DirPickerHelpScreen,
    DirPickerScreen,
    DirSearchMenuScreen,
    FanoutScreen,
    HelpScreen,
    NavigatorScreen,
    PaneView,
    ProfilePickerScreen,
    PyHerdrTui,
    RenameScreen,
    ShellPickerScreen,
    ThemeScreen,
    UrlPickerScreen,
    WorkflowScreen,
    WorktreeScreen,
    _help_text,
)
from pyherdr.workflow import new_event
from pyherdr.workspace_recents import load_workspace_recents, record_workspace_recent
from pyherdr.workspace_search import ExplorerRow, SearchRoot

STATE = {
    "focused_workspace_id": "ws1",
    "workspaces": [
        {
            "id": "ws1",
            "label": "main",
            "cwd": ".",
            "focused_tab_id": "t1",
            "tabs": [
                {
                    "id": "t1",
                    "label": "shell",
                    "focused_pane_id": "1-1",
                    "panes": [
                        {"id": "1-1", "title": "a", "status": "working", "running": True, "agent": "claude"},
                        {"id": "1-2", "title": "b", "status": "idle", "running": True},
                    ],
                    "layout": {
                        "root": {
                            "kind": "split",
                            "direction": "horizontal",
                            "ratio": 0.5,
                            "first": {"kind": "pane", "pane_id": "1-1"},
                            "second": {"kind": "pane", "pane_id": "1-2"},
                        },
                        "focus": "1-1",
                    },
                },
                {
                    "id": "t2",
                    "label": "logs",
                    "focused_pane_id": "2-1",
                    "panes": [{"id": "2-1", "title": "logs", "status": "idle", "running": True}],
                },
            ],
        }
    ],
}


class FakeClient:
    def __init__(self) -> None:
        self.sent_text: list[tuple[str, str]] = []
        self.sent_key: list[tuple[str, str]] = []
        self.tabs = 0
        self.panes = 0
        self.workspaces = 0
        self.started: list[tuple[str, str]] = []
        self.closed_panes: list[str] = []
        self.closed_tabs: list[str] = []
        self.splits: list[str] = []
        self.layouts: list[dict] = []
        self.renamed: list[tuple[str, str]] = []
        self.renamed_panes: list[tuple[str, str]] = []
        self.scrolled: list[tuple[str, str]] = []
        self.moved: list[tuple[str, str]] = []
        self.moved_workspaces: list[tuple[str, str]] = []
        self.split_targets: list[tuple[str, str | None]] = []
        self.created_workspaces: list[tuple[str, str]] = []
        self.focused_workspaces: list[str] = []
        self.focused_tabs: list[str] = []
        self.focused_agents: list[tuple[str | None, bool]] = []
        self.renamed_workspaces: list[tuple[str, str]] = []
        self.closed_workspaces: list[str] = []
        self.fanouts: list[dict] = []
        self.opened_worktrees: list[tuple[str, str | None]] = []
        self.created_worktrees: list[dict] = []
        self.removed_worktrees: list[tuple[str, bool]] = []
        self.reads: list[tuple[str, int, bool, bool]] = []
        self.resizes: list[tuple[str, int, int]] = []
        self.events: list[tuple[str, str]] = []
        self.waits: list[dict[str, int]] = []
        self.terminal_metadata: dict[str, dict[str, bool]] = {}

    def state(self) -> dict:
        return STATE

    def stats(self) -> dict:
        return {"available": True, "stats": {}}

    def pane_read(self, pane_id: str, lines: int = 200, styled: bool = False, cursor: bool = False) -> str:
        self.reads.append((pane_id, lines, styled, cursor))
        self.events.append(("read", pane_id))
        return f"SCREEN:{pane_id}"

    def pane_resize(self, pane_id: str, rows: int, cols: int) -> dict:
        self.resizes.append((pane_id, rows, cols))
        self.events.append(("resize", pane_id))
        return {"result": {"type": "pane_resize", "pane_id": pane_id, "rows": rows, "cols": cols}}

    def pane_terminal_metadata(self, pane_id: str) -> dict[str, bool]:
        return self.terminal_metadata.get(pane_id, {"alt_screen": False, "mouse_reporting": False})

    def pane_wait_output(self, versions: dict[str, int], timeout: float = 1.0) -> dict:
        self.waits.append(dict(versions))
        return {"type": "pane_output_wait", "changed": {}, "versions": versions, "timed_out": True}

    def send_text(self, pane_id: str, text: str) -> None:
        self.sent_text.append((pane_id, text))
        self.events.append(("send_text", pane_id))

    def send_key(self, pane_id: str, key: str) -> None:
        self.sent_key.append((pane_id, key))
        self.events.append(("send_key", pane_id))

    def pane_scroll(self, pane_id: str, direction: str) -> None:
        self.scrolled.append((pane_id, direction))
        self.events.append(("scroll", f"{pane_id}:{direction}"))

    def create_tab(self, label: str = "shell") -> dict:
        self.tabs += 1
        return {"result": {"tab": {"focused_pane_id": "new-pane"}}}

    def create_pane(self, title: str = "pane") -> dict:
        self.panes += 1
        return {"result": {"pane": {"pane_id": "new-pane"}}}

    def split_pane(self, direction: str = "horizontal", pane_id: str | None = None) -> dict:
        self.splits.append(direction)
        self.split_targets.append((direction, pane_id))
        return {"result": {"pane": {"pane_id": "new-pane"}}}

    def set_layout(self, layout: dict) -> dict:
        self.layouts.append(layout)
        return {"result": {"type": "pane_layout_set"}}

    def create_workspace(self, label: str = "workspace", cwd: str = ".") -> None:
        self.workspaces += 1
        self.created_workspaces.append((label, cwd))

    def start_pane(self, pane_id: str, command: str) -> None:
        self.started.append((pane_id, command))

    def close_pane(self, pane_id: str) -> None:
        self.closed_panes.append(pane_id)

    def rename_pane(self, pane_id: str, title: str) -> dict:
        self.renamed_panes.append((pane_id, title))
        return {"result": {"type": "pane_renamed"}}

    def close_tab(self, tab_id: str) -> None:
        self.closed_tabs.append(tab_id)

    def rename_tab(self, tab_id: str, label: str) -> dict:
        self.renamed.append((tab_id, label))
        return {"result": {"type": "tab_renamed"}}

    def move_tab(self, tab_id: str, direction: str) -> dict:
        self.moved.append((tab_id, direction))
        return {"result": {"type": "tab_moved"}}

    def move_workspace(self, workspace_id: str, direction: str) -> dict:
        self.moved_workspaces.append((workspace_id, direction))
        return {"result": {"type": "workspace_moved"}}

    def focus_workspace(self, workspace_id: str) -> dict:
        self.focused_workspaces.append(workspace_id)
        return {"result": {"type": "workspace_focused"}}

    def focus_tab(self, tab_id: str) -> dict:
        self.focused_tabs.append(tab_id)
        return {"result": {"type": "tab_focused"}}

    def focus_agent(self, target: str | None = None, *, attention: bool = False) -> dict:
        self.focused_agents.append((target, attention))
        state = self.state()
        candidates: list[tuple[dict, dict, dict]] = []
        for workspace in state.get("workspaces", []):
            for tab in workspace.get("tabs", []):
                for pane in tab.get("panes", []):
                    if attention and pane.get("status") not in ("blocked", "done"):
                        continue
                    if not attention and pane.get("id") != target and pane.get("title") != target:
                        continue
                    candidates.append((workspace, tab, pane))
        if not candidates:
            raise KeyError("agent not found")
        focused_workspace_id = state.get("focused_workspace_id")
        current = (
            focused_workspace_id,
            next(
                (
                    workspace.get("focused_tab_id")
                    for workspace in state.get("workspaces", [])
                    if workspace.get("id") == focused_workspace_id
                ),
                None,
            ),
            None,
        )
        if current[1]:
            for workspace in state.get("workspaces", []):
                if workspace.get("id") != current[0]:
                    continue
                for tab in workspace.get("tabs", []):
                    if tab.get("id") == current[1]:
                        current = (current[0], current[1], tab.get("focused_pane_id"))
        picked = candidates[0]
        for index, (workspace, tab, pane) in enumerate(candidates):
            if (workspace.get("id"), tab.get("id"), pane.get("id")) == current:
                picked = candidates[(index + 1) % len(candidates)]
                break
        workspace, tab, pane = picked
        state["focused_workspace_id"] = workspace["id"]
        workspace["focused_tab_id"] = tab["id"]
        tab["focused_pane_id"] = pane["id"]
        return {
            "result": {
                "type": "agent_focused",
                "agent": {"workspace_id": workspace["id"], "tab_id": tab["id"], "pane_id": pane["id"]},
            }
        }

    def rename_workspace(self, workspace_id: str, label: str) -> dict:
        self.renamed_workspaces.append((workspace_id, label))
        return {"result": {"type": "workspace_renamed"}}

    def close_workspace(self, workspace_id: str) -> dict:
        self.closed_workspaces.append(workspace_id)
        return {"result": {"type": "workspace_closed"}}

    def pane_fanout(
        self,
        targets: list[str],
        text: str,
        *,
        enter: bool = True,
        dry_run: bool = True,
        confirm_risky: bool = False,
    ) -> dict:
        self.fanouts.append(
            {
                "targets": targets,
                "text": text,
                "enter": enter,
                "dry_run": dry_run,
                "confirm_risky": confirm_risky,
            }
        )
        pane_ids: list[str]
        selector = targets[0] if targets else ""
        if selector == "all":
            pane_ids = ["1-1", "1-2", "2-1"]
        elif selector == "tab:t1":
            pane_ids = ["1-1", "1-2"]
        elif selector == "workspace:ws1":
            pane_ids = ["1-1", "1-2", "2-1"]
        elif selector == "agent:claude":
            pane_ids = ["1-1"]
        elif selector.startswith("pane:"):
            pane_ids = [selector.removeprefix("pane:")]
        else:
            pane_ids = []
        risk = "recursive force remove" if "rm -rf" in text.lower() and len(pane_ids) > 1 else ""
        if risk and not dry_run and not confirm_risky:
            raise ValueError("confirm_risky is required")
        return {
            "type": "pane_fanout",
            "dry_run": dry_run,
            "enter": enter,
            "target_count": len(pane_ids),
            "requires_confirmation": bool(risk),
            "risk": risk,
            "targets": [
                {
                    "pane_id": pane_id,
                    "workspace_label": "main",
                    "tab_label": "shell" if pane_id != "2-1" else "logs",
                    "title": "a" if pane_id == "1-1" else ("b" if pane_id == "1-2" else "logs"),
                    "status": "working" if pane_id == "1-1" else "idle",
                }
                for pane_id in pane_ids
            ],
            "sent": 0 if dry_run else len(pane_ids),
            "bytes": len((text + ("\n" if enter else "")).encode("utf-8")),
        }

    def worktree_list(self, cwd: str | None = None) -> list[dict]:
        return [
            {"path": "C:/repo/pyherdr", "branch": "main", "head": "abc1234"},
            {"path": "C:/repo/pyherdr-sidebar", "branch": "feature/sidebar", "head": "def5678"},
        ]

    def worktree_create(
        self,
        branch: str,
        *,
        base: str | None = None,
        path: str | None = None,
        label: str | None = None,
        cwd: str | None = None,
    ) -> dict:
        payload = {"branch": branch, "base": base, "path": path, "label": label, "cwd": cwd}
        self.created_worktrees.append(payload)
        return {"type": "worktree_created", "path": path or f"C:/repo/{branch.replace('/', '-')}"}

    def worktree_open(self, path: str, label: str | None = None) -> dict:
        self.opened_worktrees.append((path, label))
        return {"type": "worktree_opened", "path": path}

    def worktree_remove(self, path: str, *, force: bool = False) -> dict:
        self.removed_worktrees.append((path, force))
        return {"type": "worktree_removed", "path": path}


class TuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_renders_a_view_per_pane_in_focused_tab(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(len(list(app.query(PaneView))), 2)

    async def test_pane_contents_resize_terminal_to_visible_cells_before_read(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            client.reads.clear()
            client.resizes.clear()
            client.events.clear()
            app._terminal_sizes.clear()

            app._update_pane_contents()
            await pilot.pause()

            resized = {pane_id: (rows, cols) for pane_id, rows, cols in client.resizes}
            self.assertIn("1-1", resized)
            self.assertIn("1-2", resized)
            for rows, cols in resized.values():
                self.assertGreaterEqual(rows, 1)
                self.assertLess(rows, 30)
                self.assertGreaterEqual(cols, 1)
                self.assertLess(cols, 100)
            for pane_id in ("1-1", "1-2"):
                resize_index = client.events.index(("resize", pane_id))
                read_index = client.events.index(("read", pane_id))
                self.assertLess(resize_index, read_index)
            self.assertIn(("1-1", 400, True, True), client.reads)
            self.assertIn(("1-2", 400, True, False), client.reads)

    async def test_prefix_then_c_creates_a_tab(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("c")
            await pilot.pause()
            self.assertEqual(client.tabs, 1)

    async def test_prefix_then_v_splits_side_by_side(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("v")
            await pilot.pause()
            self.assertEqual(client.splits, ["horizontal"])

    async def test_prefix_then_dash_splits_stacked(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("minus")
            await pilot.pause()
            self.assertEqual(client.splits, ["vertical"])

    async def test_prefix_then_l_moves_focus_right(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertEqual(app._pane_id, "1-1")
            await pilot.press("ctrl+b")
            await pilot.press("l")
            await pilot.pause()
            self.assertEqual(app._pane_id, "1-2")
            await pilot.press("ctrl+b")
            await pilot.press("h")
            await pilot.pause()
            self.assertEqual(app._pane_id, "1-1")

    async def test_resize_mode_widens_focused_pane(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("r")  # enter resize mode
            self.assertTrue(app._resize)
            await pilot.press("l")  # grow focused (1-1) width
            await pilot.pause()
            self.assertTrue(client.layouts)
            self.assertGreater(client.layouts[-1]["root"]["ratio"], 0.5)
            await pilot.press("escape")  # exit resize mode
            self.assertFalse(app._resize)

    async def test_prefix_then_question_opens_help_and_esc_closes(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("question_mark")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, HelpScreen)

    async def test_theme_picker_applies_live_and_accent(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("s")
            await pilot.pause()
            self.assertIsInstance(app.screen, ThemeScreen)
            await pilot.click("#theme-nord")
            await pilot.pause()
            self.assertEqual(app._theme_name, "nord")
            self.assertIsInstance(app.screen, ThemeScreen)  # stays open for live preview
            await pilot.click("#accent-a6e3a1")  # pick a green accent
            await pilot.pause()
            self.assertEqual(app._palette.accent, "#a6e3a1")
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, ThemeScreen)

    @staticmethod
    def _submit_event(value: str) -> object:
        return type("Submitted", (), {"value": value, "stop": lambda self: None})()

    @staticmethod
    def _activated(action: str, arg: str | None) -> object:
        return type("Activated", (), {"action": action, "arg": arg, "stop": lambda self: None})()

    @staticmethod
    def _changed_event(value: str) -> object:
        return type("Changed", (), {"value": value})()

    @staticmethod
    def _key_event(key: str) -> object:
        return type("Key", (), {"key": key, "stop": lambda self: None, "prevent_default": lambda self: None})()

    @staticmethod
    def _screen_text(screen: object, selector: str) -> str:
        widget = screen.query_one(selector)
        lines: list[str] = []
        for child in widget.children:
            renderable = child.render()
            lines.append(renderable.plain if hasattr(renderable, "plain") else str(renderable))
        return "\n".join(lines)

    @staticmethod
    def _widget_text(screen: object, selector: str) -> str:
        renderable = screen.query_one(selector).render()
        return renderable.plain if hasattr(renderable, "plain") else str(renderable)

    async def _wait_for_dir_list_text(self, pilot, app: PyHerdrTui, expected: str) -> str:
        text = ""
        for _ in range(20):
            await pilot.pause(0.1)
            text = self._screen_text(app.screen, "#dir-list")
            if expected in text:
                break
        return text

    async def test_dir_picker_navigates_and_selects(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        child = os.path.join(base, "child")
        os.makedirs(child)
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, selected.append))
            await pilot.pause()
            self.assertIsInstance(app.screen, DirPickerScreen)
            app.screen.on_activated(self._activated("dir_enter", child))  # enter child/
            await pilot.pause()
            app.screen.on_activated(self._activated("dir_open", None))  # open it
            await pilot.pause()
            self.assertEqual(selected, [child])

    async def test_dir_picker_quick_path_jumps_to_known_folder(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        quick = tempfile.mkdtemp()
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, selected.append, quick_paths=[("repo root", quick)]))
            await pilot.pause()
            self.assertIsInstance(app.screen, DirPickerScreen)
            app.screen.on_activated(self._activated("dir_quick", quick))
            await pilot.pause()
            app.screen.on_activated(self._activated("dir_open", None))
            await pilot.pause()
            self.assertEqual(selected, [os.path.abspath(quick)])

    async def test_dir_picker_input_filters_folders_and_quick_paths(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        os.makedirs(os.path.join(base, "alpha"))
        os.makedirs(os.path.join(base, "beta"))
        recent = tempfile.mkdtemp()
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, selected.append, quick_paths=[("recent project", recent)]))
            await pilot.pause()

            app.copy_to_clipboard("alp")
            app.screen.on_key(self._key_event("ctrl+shift+v"))
            await pilot.pause()
            jump = app.screen.query_one("#dir-jump")
            self.assertEqual(jump.value, "alp")
            text = self._screen_text(app.screen, "#dir-list")
            self.assertIn("alpha/", text)
            self.assertNotIn("beta/", text)
            self.assertNotIn("recent project", text)

            await app.screen.on_input_changed(self._changed_event("alp"))
            await pilot.pause()
            text = self._screen_text(app.screen, "#dir-list")
            self.assertIn("alpha/", text)
            self.assertNotIn("beta/", text)
            self.assertNotIn("recent project", text)

            await app.screen.on_input_changed(self._changed_event("recent"))
            await pilot.pause()
            text = self._screen_text(app.screen, "#dir-list")
            self.assertIn("recent project", text)
            self.assertNotIn("alpha/", text)

    async def test_dir_picker_metadata_shows_repo_context_and_caches_git(self):
        import os
        import tempfile
        from unittest.mock import patch

        base = tempfile.mkdtemp()
        os.makedirs(os.path.join(base, "src"))
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        with (
            patch("pyherdr.presentation.tui._git_root", return_value=os.path.abspath(base)) as git_root,
            patch("pyherdr.presentation.tui._git_branch", return_value="main") as git_branch,
            patch("pyherdr.presentation.tui._git_dirty", return_value=True) as git_dirty,
        ):
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                app.push_screen(DirPickerScreen(base, lambda path: None))
                await pilot.pause()
                metadata = self._widget_text(app.screen, "#dir-path")
                self.assertIn(os.path.abspath(base).replace("\\", "/"), metadata)
                self.assertIn("1 folder", metadata)
                self.assertIn("repo root", metadata)
                self.assertIn("branch main", metadata)
                self.assertIn("dirty", metadata)

                root_calls = git_root.call_count
                branch_calls = git_branch.call_count
                dirty_calls = git_dirty.call_count
                await app.screen.on_input_changed(self._changed_event("src"))
                await pilot.pause()
                self.assertEqual(git_root.call_count, root_calls)
                self.assertEqual(git_branch.call_count, branch_calls)
                self.assertEqual(git_dirty.call_count, dirty_calls)

    async def test_dir_picker_current_path_action_bar_opens_current_folder(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, selected.append))
            await pilot.pause()
            app.screen.query_one("#dir-current-card")
            current_text = self._widget_text(app.screen, "#dir-path")
            self.assertIn("CURRENT FOLDER:", current_text)
            self.assertIn(os.path.abspath(base).replace("\\", "/"), current_text)
            self.assertIn("Open Folder", self._widget_text(app.screen, "#dir-open-current"))
            self.assertNotIn("open this folder", self._screen_text(app.screen, "#dir-list").lower())
            css = DirPickerScreen.DEFAULT_CSS
            self.assertIn("width: 13;", css)
            self.assertIn("height: 1;", css)
            self.assertIn("background: $ph-surface0;", css)
            self.assertNotIn("min-height: 3;", css)

            app.screen.on_activated(self._activated("dir_open", None))
            await pilot.pause()

        self.assertEqual(selected, [os.path.abspath(base)])

    async def test_dir_picker_pins_footer_when_folder_list_is_long(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        for index in range(24):
            os.makedirs(os.path.join(base, f"folder-{index:02d}"))
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, lambda path: None))
            await pilot.pause()

            app.screen.query_one("#dir-list-panel")
            self.assertIn("Help", self._widget_text(app.screen, "#dir-help"))
            self.assertIn("Enter open", self._widget_text(app.screen, "#dir-foot"))
            self.assertIn("─", self._widget_text(app.screen, "#dir-separator"))
            self.assertIn("> .. parent folder", self._screen_text(app.screen, "#dir-list"))

    async def test_dir_picker_arrows_scroll_active_row_into_view(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        for index in range(30):
            os.makedirs(os.path.join(base, f"folder-{index:02d}"))
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, lambda path: None))
            await pilot.pause()
            listing = app.screen.query_one("#dir-list")
            self.assertEqual(listing.scroll_y, 0)

            for _ in range(14):
                app.screen.on_key(self._key_event("down"))
                await pilot.pause()

            for _ in range(10):
                await pilot.pause(0.1)
                if listing.scroll_y > 0:
                    break
            self.assertGreater(listing.scroll_y, 0)
            self.assertIn("> folder-13/", self._screen_text(app.screen, "#dir-list"))

    async def test_dir_picker_arrows_scroll_active_row_back_up_into_view(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        for index in range(30):
            os.makedirs(os.path.join(base, f"folder-{index:02d}"))
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, lambda path: None))
            await pilot.pause()
            listing = app.screen.query_one("#dir-list")

            for _ in range(24):
                app.screen.on_key(self._key_event("down"))
                await pilot.pause()
            for _ in range(10):
                await pilot.pause(0.1)
                if listing.scroll_y > 0:
                    break
            scrolled_down_y = listing.scroll_y
            self.assertGreater(scrolled_down_y, 0)

            for _ in range(18):
                app.screen.on_key(self._key_event("up"))
                await pilot.pause()
            for _ in range(10):
                await pilot.pause(0.1)
                if listing.scroll_y < scrolled_down_y:
                    break

            self.assertLess(listing.scroll_y, scrolled_down_y)
            self.assertIn("> folder-05/", self._screen_text(app.screen, "#dir-list"))

    async def test_dir_picker_browse_mode_arrows_move_and_enter_opens_active_row(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        alpha = os.path.join(base, "alpha")
        beta = os.path.join(base, "beta")
        nested = os.path.join(alpha, "nested")
        os.makedirs(nested)
        os.makedirs(beta)
        selected: list[str] = []
        copied: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        app.copy_to_clipboard = lambda text: copied.append(text)  # type: ignore[method-assign]
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, selected.append))
            await pilot.pause()
            listing = self._screen_text(app.screen, "#dir-list")
            self.assertIn("> .. parent folder", listing)

            app.screen.on_key(self._key_event("down"))
            await pilot.pause()
            listing = self._screen_text(app.screen, "#dir-list")
            self.assertIn("> alpha/", listing)
            self.assertIn("  beta/", listing)

            app.screen.on_key(self._key_event("y"))
            await pilot.pause()
            self.assertEqual(copied[-1], os.path.abspath(alpha))
            self.assertIn("copied path:", self._widget_text(app.screen, "#dir-foot"))

            copied.clear()
            app.screen.on_key(self._key_event("ctrl+shift+c"))
            await pilot.pause()
            self.assertEqual(copied[-1], os.path.abspath(alpha))
            self.assertIn("copied path:", self._widget_text(app.screen, "#dir-foot"))

            app.screen.on_input_submitted(self._submit_event(""))
            await pilot.pause()
            self.assertIn(os.path.abspath(alpha).replace("\\", "/"), self._widget_text(app.screen, "#dir-path"))
            self.assertIn("nested/", self._screen_text(app.screen, "#dir-list"))

            app.screen.on_key(self._key_event("up"))
            await pilot.pause()
            self.assertIn("> ..", self._screen_text(app.screen, "#dir-list"))
            app.screen.on_input_submitted(self._submit_event(""))
            await pilot.pause()
            self.assertIn(os.path.abspath(base).replace("\\", "/"), self._widget_text(app.screen, "#dir-path"))

        self.assertEqual(selected, [])

    async def test_dir_picker_browse_mode_enter_opens_active_quick_path(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        quick = tempfile.mkdtemp()
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, selected.append, quick_paths=[("repo root", quick)]))
            await pilot.pause()
            app.screen.on_key(self._key_event("down"))
            await pilot.pause()
            listing = self._screen_text(app.screen, "#dir-list")
            self.assertIn("> repo root ·", listing)
            self.assertNotIn(f"repo root: {os.path.abspath(quick)}", listing)

            app.screen.on_input_submitted(self._submit_event(""))
            await pilot.pause()
            self.assertIn(os.path.abspath(quick).replace("\\", "/"), self._widget_text(app.screen, "#dir-path"))

        self.assertEqual(selected, [])

    async def test_dir_picker_browse_shortcuts_jump_to_parent_home_current_workspace_and_repo(self):
        import os
        import tempfile
        from unittest.mock import patch

        root = tempfile.mkdtemp()
        workspace = os.path.join(root, "workspace")
        child = os.path.join(workspace, "child")
        home = os.path.join(root, "home")
        repo = os.path.join(root, "repo")
        os.makedirs(child)
        os.makedirs(home)
        os.makedirs(repo)
        selected: list[str] = []

        def fake_expanduser(value: str) -> str:
            return home if value == "~" else value

        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        with (
            patch("pyherdr.presentation.tui.os.path.expanduser", side_effect=fake_expanduser),
            patch("pyherdr.presentation.tui._git_root", return_value=os.path.abspath(repo)),
        ):
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                app.push_screen(
                    DirPickerScreen(child, selected.append, quick_paths=[("current workspace", workspace)])
                )
                await pilot.pause()
                self.assertIn("filter here", self._widget_text(app.screen, "#dir-input-hint"))
                self.assertIn("Enter open", self._widget_text(app.screen, "#dir-foot"))
                self.assertNotIn("type to filter", self._widget_text(app.screen, "#dir-foot"))
                self.assertNotIn("^W ws", self._widget_text(app.screen, "#dir-foot"))

                app.screen.on_key(self._key_event("backspace"))
                await pilot.pause()
                self.assertEqual(app.screen._cwd, os.path.abspath(workspace))

                app.screen.on_key(self._key_event("ctrl+h"))
                await pilot.pause()
                self.assertEqual(app.screen._cwd, os.path.abspath(home))

                app.screen.on_key(self._key_event("ctrl+w"))
                await pilot.pause()
                self.assertEqual(app.screen._cwd, os.path.abspath(workspace))

                app.screen.on_key(self._key_event("ctrl+r"))
                await pilot.pause()
                self.assertEqual(app.screen._cwd, os.path.abspath(repo))

        self.assertEqual(selected, [])

    async def test_dir_picker_help_button_opens_shortcut_help(self):
        import tempfile

        base = tempfile.mkdtemp()
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, lambda path: None))
            await pilot.pause()
            self.assertIn("Help", self._widget_text(app.screen, "#dir-help"))

            app.screen.on_activated(self._activated("dir_help", None))
            await pilot.pause()

            self.assertIsInstance(app.screen, DirPickerHelpScreen)
            help_text = self._widget_text(app.screen, "#dir-help-box")
            self.assertIn("Ctrl+W", help_text)
            self.assertIn("ls text", help_text)
            self.assertIn("copy highlighted path", help_text)
            self.assertIn("Ctrl+Shift+C", help_text)
            self.assertIn("Ctrl+Shift+V", help_text)
            self.assertIn("copy path", help_text)
            self.assertIn("search mode", help_text)

    async def test_dir_picker_input_accepts_safe_navigation_commands(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        alpha = os.path.join(base, "alpha")
        beta = os.path.join(base, "beta")
        nested = os.path.join(alpha, "nested")
        os.makedirs(nested)
        os.makedirs(beta)
        selected: list[str] = []
        copied: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        app.copy_to_clipboard = lambda text: copied.append(text)  # type: ignore[method-assign]
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, selected.append))
            await pilot.pause()

            app.screen.on_input_submitted(self._submit_event("ls alp"))
            await pilot.pause()
            listing = self._screen_text(app.screen, "#dir-list")
            self.assertIn("alpha/", listing)
            self.assertNotIn("beta/", listing)

            app.screen.on_input_submitted(self._submit_event("cd alpha"))
            await pilot.pause()
            self.assertIn(os.path.abspath(alpha).replace("\\", "/"), self._widget_text(app.screen, "#dir-path"))
            self.assertIn("nested/", self._screen_text(app.screen, "#dir-list"))

            app.screen.on_input_submitted(self._submit_event("pwd"))
            await pilot.pause()
            self.assertIn(os.path.abspath(alpha).replace("\\", "/"), self._widget_text(app.screen, "#dir-foot"))

            app.screen.on_input_submitted(self._submit_event("copy"))
            await pilot.pause()
            self.assertEqual(copied[-1], os.path.abspath(alpha))
            self.assertIn("copied:", self._widget_text(app.screen, "#dir-foot"))

            app.screen.on_input_submitted(self._submit_event("cd .."))
            await pilot.pause()
            self.assertIn(os.path.abspath(base).replace("\\", "/"), self._widget_text(app.screen, "#dir-path"))

            app.screen.on_input_submitted(self._submit_event("copy alpha"))
            await pilot.pause()
            self.assertEqual(copied[-1], os.path.abspath(alpha))

            app.screen.on_input_submitted(self._submit_event("open alpha"))
            await pilot.pause()

        self.assertEqual(selected, [os.path.abspath(alpha)])

    async def test_dir_picker_file_paths_navigate_or_open_containing_folder(self):
        import os
        import tempfile

        base = tempfile.mkdtemp()
        alpha = os.path.join(base, "alpha")
        os.makedirs(alpha)
        file_path = os.path.join(alpha, "README.md")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("# demo\n")
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(DirPickerScreen(base, selected.append))
            await pilot.pause()

            app.screen.on_input_submitted(self._submit_event(f"cd {file_path}"))
            await pilot.pause()
            self.assertIn(os.path.abspath(alpha).replace("\\", "/"), self._widget_text(app.screen, "#dir-path"))

            app.screen.on_input_submitted(self._submit_event(f"open {file_path}"))
            await pilot.pause()

        self.assertEqual(selected, [os.path.abspath(alpha)])

    async def test_dir_picker_search_mode_selects_and_opens_result(self):
        import os
        import tempfile

        root = tempfile.mkdtemp()
        alpha = os.path.join(root, "alpha-app")
        beta = os.path.join(root, "beta-tool")
        os.makedirs(os.path.join(alpha, ".git"))
        os.makedirs(beta)
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(
                DirPickerScreen(
                    root,
                    selected.append,
                    search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                    search_debounce=0,
                )
            )
            await pilot.pause()
            app.screen.on_key(self._key_event("ctrl+f"))
            await app.screen.on_input_changed(self._changed_event("alpha"))
            text = await self._wait_for_dir_list_text(pilot, app, "alpha-app")
            self.assertIn("alpha-app", text)
            self.assertNotIn("beta-tool", text)

            app.screen.on_key(self._key_event("space"))
            await pilot.pause()
            text = self._screen_text(app.screen, "#dir-list")
            self.assertIn("[x]", text)

            app.screen.on_input_submitted(self._submit_event("alpha"))
            await pilot.pause()
            self.assertEqual(selected, [os.path.abspath(alpha)])

    async def test_dir_picker_search_row_double_click_opens_result(self):
        import os
        import tempfile

        root = tempfile.mkdtemp()
        alpha = os.path.join(root, "alpha-app")
        os.makedirs(alpha)
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(
                DirPickerScreen(
                    root,
                    selected.append,
                    search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                    search_debounce=0,
                )
            )
            await pilot.pause()
            app.screen.on_key(self._key_event("ctrl+f"))
            await app.screen.on_input_changed(self._changed_event("alpha"))
            await pilot.pause()
            app.screen.on_activated(self._activated("dir_search_open", os.path.abspath(alpha)))
            await pilot.pause()

        self.assertEqual(selected, [os.path.abspath(alpha)])

    async def test_dir_picker_search_mode_loads_results_from_worker(self):
        import os
        import tempfile

        root = tempfile.mkdtemp()
        alpha = os.path.join(root, "alpha-app")
        os.makedirs(os.path.join(alpha, ".git"))
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(
                DirPickerScreen(
                    root,
                    selected.append,
                    search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                    search_debounce=0.05,
                )
            )
            await pilot.pause()
            app.screen.on_key(self._key_event("ctrl+f"))
            await app.screen.on_input_changed(self._changed_event("alpha"))
            self.assertIn("searching roots for alpha", self._screen_text(app.screen, "#dir-list"))

            text = await self._wait_for_dir_list_text(pilot, app, "alpha-app")
            self.assertIn("alpha-app", text)
            self.assertNotIn("searching roots", text)

        self.assertEqual(selected, [])

    async def test_dir_picker_search_mode_reuses_cached_query_results(self):
        import os
        import tempfile
        from unittest.mock import patch

        root = tempfile.mkdtemp()
        row = ExplorerRow(
            row_id=f"repo:{root}",
            kind="repo",
            label="alpha-app",
            path=os.path.abspath(root),
            score=1000,
            source="workspace",
            repo_root=os.path.abspath(root),
        )
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        with patch("pyherdr.presentation.tui.search_workspace_rows", return_value=[row]) as search:
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                app.push_screen(
                    DirPickerScreen(
                        root,
                        selected.append,
                        search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                        search_debounce=0,
                    )
                )
                await pilot.pause()
                app.screen.on_key(self._key_event("ctrl+f"))
                await app.screen.on_input_changed(self._changed_event("alpha"))
                await pilot.pause(0.2)
                self.assertIn("alpha-app", self._screen_text(app.screen, "#dir-list"))

                await app.screen.on_input_changed(self._changed_event("alpha"))
                await pilot.pause(0.2)
                self.assertIn("alpha-app", self._screen_text(app.screen, "#dir-list"))

        self.assertEqual(search.call_count, 1)
        self.assertEqual(selected, [])

    async def test_dir_picker_search_mode_ignores_stale_worker_results(self):
        import os
        import tempfile
        import time
        from unittest.mock import patch

        root = tempfile.mkdtemp()
        alpha_row = ExplorerRow(
            row_id=f"repo:{root}:alpha",
            kind="repo",
            label="alpha-app",
            path=os.path.join(root, "alpha-app"),
            score=1000,
            source="workspace",
        )
        beta_row = ExplorerRow(
            row_id=f"repo:{root}:beta",
            kind="repo",
            label="beta-tool",
            path=os.path.join(root, "beta-tool"),
            score=1000,
            source="workspace",
        )

        def fake_search(query: str, _roots: object, **_kwargs: object) -> list[ExplorerRow]:
            time.sleep(0.2 if query == "alpha" else 0.01)
            return [alpha_row] if query == "alpha" else [beta_row]

        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        with patch("pyherdr.presentation.tui.search_workspace_rows", side_effect=fake_search):
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                app.push_screen(
                    DirPickerScreen(
                        root,
                        lambda path: None,
                        search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                        search_debounce=0,
                    )
                )
                await pilot.pause()
                app.screen.on_key(self._key_event("ctrl+f"))
                await app.screen.on_input_changed(self._changed_event("alpha"))
                await pilot.pause(0.05)
                await app.screen.on_input_changed(self._changed_event("beta"))
                await pilot.pause(0.4)

                text = self._screen_text(app.screen, "#dir-list")
                self.assertIn("beta-tool", text)
                self.assertNotIn("alpha-app", text)

    def test_dir_picker_search_row_text_includes_metadata(self):
        import os
        import tempfile

        root = tempfile.mkdtemp()
        child = os.path.join(root, "src")
        os.makedirs(child)
        row = ExplorerRow(
            row_id=f"repo:{root}",
            kind="repo",
            label="alpha-app",
            path=os.path.abspath(root),
            score=1000,
            source="recent",
            repo_root=os.path.abspath(root),
            child_count=1,
            branch="main",
            dirty=True,
        )
        screen = DirPickerScreen(root, lambda path: None)
        plain = screen._search_row_text(row, 0).plain

        self.assertIn("repo", plain)
        self.assertIn("alpha-app", plain)
        self.assertIn("recent", plain)
        self.assertIn("repo root", plain)
        self.assertIn("1 folder", plain)
        self.assertIn("branch main", plain)
        self.assertIn("dirty", plain)
        self.assertIn(os.path.abspath(root).replace("\\", "/"), plain)

    def test_dir_picker_search_menu_items_reflect_stale_state(self):
        live = ExplorerRow(
            row_id="repo:C:/repo",
            kind="repo",
            label="repo",
            path="C:/repo",
            score=1000,
            source="workspace",
        )
        stale = ExplorerRow(
            row_id="stale:C:/missing",
            kind="stale",
            label="missing",
            path="C:/missing",
            score=1000,
            source="recent",
            stale=True,
        )

        live_labels = [label for label, _action, _arg in DirSearchMenuScreen(live, lambda *_: None)._items()]
        stale_labels = [label for label, _action, _arg in DirSearchMenuScreen(stale, lambda *_: None)._items()]

        self.assertIn("open result", live_labels)
        self.assertNotIn("remove stale", live_labels)
        self.assertNotIn("open result", stale_labels)
        self.assertIn("remove stale", stale_labels)

    async def test_dir_picker_search_parent_key_enters_result_parent(self):
        import os
        import tempfile

        root = tempfile.mkdtemp()
        outer = os.path.join(root, "outer")
        alpha = os.path.join(outer, "alpha-app")
        other = os.path.join(root, "other")
        os.makedirs(alpha)
        os.makedirs(other)
        selected: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(
                DirPickerScreen(
                    other,
                    selected.append,
                    search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                    search_debounce=0,
                )
            )
            await pilot.pause()
            app.screen.on_key(self._key_event("ctrl+f"))
            await app.screen.on_input_changed(self._changed_event("alpha"))
            text = await self._wait_for_dir_list_text(pilot, app, "alpha-app")
            self.assertIn("alpha-app", text)

            app.screen.on_key(self._key_event("p"))
            path_text = ""
            footer = ""
            expected_parent = os.path.abspath(outer).replace("\\", "/")
            for _ in range(10):
                await pilot.pause(0.1)
                path_text = self._widget_text(app.screen, "#dir-path")
                footer = self._widget_text(app.screen, "#dir-foot")
                if expected_parent in path_text and "parent:" in footer:
                    break

            self.assertIn(expected_parent, path_text)
            self.assertIn("parent:", footer)

        self.assertEqual(selected, [])

    async def test_dir_picker_search_delete_hides_active_stale_row(self):
        import os
        import tempfile

        root = tempfile.mkdtemp()
        missing = os.path.join(root, "ghostc-plugin")
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(
                DirPickerScreen(
                    root,
                    lambda path: None,
                    search_roots=[SearchRoot(missing, label="ghostc-plugin", source="recent")],
                    search_debounce=0,
                )
            )
            await pilot.pause()
            app.screen.on_key(self._key_event("ctrl+f"))
            await app.screen.on_input_changed(self._changed_event("ghost"))
            await pilot.pause(0.2)
            self.assertIn("ghostc-plugin", self._screen_text(app.screen, "#dir-list"))

            app.screen.on_key(self._key_event("delete"))
            footer = ""
            text = ""
            for _ in range(10):
                await pilot.pause(0.1)
                text = self._screen_text(app.screen, "#dir-list")
                footer = self._widget_text(app.screen, "#dir-foot")
                if "ghostc-plugin" not in text and "hidden stale root" in footer:
                    break

            self.assertNotIn("ghostc-plugin", text)
            self.assertIn("hidden stale root", footer)

    async def test_dir_picker_search_delete_removes_stale_recent_from_recents_file(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            missing = root / "ghostc-plugin"
            recents_path = runtime / "workspace_recents.json"
            recents_path.parent.mkdir(parents=True)
            recents_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "roots": [
                            {"path": str(missing), "label": "ghostc-plugin", "last_opened": 1.0, "repo_root": ""},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {"PYHERDR_PORTABLE": "0", "PYHERDR_RUNTIME_DIR": str(runtime)},
                clear=False,
            ):
                app = PyHerdrTui(client=FakeClient(), poll_interval=100)
                async with app.run_test(size=(100, 30)) as pilot:
                    await pilot.pause()
                    app.push_screen(
                        DirPickerScreen(
                            str(root),
                            lambda path: None,
                            search_roots=[SearchRoot(str(missing), label="ghostc-plugin", source="recent")],
                            search_debounce=0,
                        )
                    )
                    await pilot.pause()
                    app.screen.on_key(self._key_event("ctrl+f"))
                    await app.screen.on_input_changed(self._changed_event("ghost"))
                    await pilot.pause(0.2)
                    self.assertIn("ghostc-plugin", self._screen_text(app.screen, "#dir-list"))

                    app.screen.on_key(self._key_event("delete"))
                    footer = ""
                    listing = ""
                    for _ in range(10):
                        await pilot.pause(0.1)
                        listing = self._screen_text(app.screen, "#dir-list")
                        footer = self._widget_text(app.screen, "#dir-foot")
                        if "ghostc-plugin" not in listing and "removed stale recent root" in footer:
                            break

                    self.assertNotIn("ghostc-plugin", listing)
                    self.assertIn("removed stale recent root", footer)
                    recents = load_workspace_recents(include_stale=True)

        self.assertEqual(recents, [])

    async def test_dir_picker_search_page_keys_jump_results(self):
        import os
        import tempfile

        root = tempfile.mkdtemp()
        for index in range(12):
            os.makedirs(os.path.join(root, f"alpha-{index:02d}"))
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(
                DirPickerScreen(
                    root,
                    lambda path: None,
                    search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                    search_debounce=0,
                )
            )
            await pilot.pause()
            app.screen.on_key(self._key_event("ctrl+f"))
            await app.screen.on_input_changed(self._changed_event("alpha"))
            text = ""
            for _ in range(30):
                await pilot.pause(0.1)
                text = self._screen_text(app.screen, "#dir-list")
                if "alpha-00" in text:
                    break
            self.assertIn("alpha-00", text)

            app.screen.on_key(self._key_event("pagedown"))
            await pilot.pause()
            self.assertIn("> [ ] dir   alpha-08", self._screen_text(app.screen, "#dir-list"))

            app.screen.on_key(self._key_event("pageup"))
            await pilot.pause()
            self.assertIn("> [ ] dir   alpha-00", self._screen_text(app.screen, "#dir-list"))

    async def test_dir_picker_search_y_copies_active_path(self):
        import os
        import tempfile

        root = tempfile.mkdtemp()
        alpha = os.path.join(root, "alpha-app")
        os.makedirs(alpha)
        copied: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        app.copy_to_clipboard = lambda text: copied.append(text)  # type: ignore[method-assign]
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(
                DirPickerScreen(
                    root,
                    lambda path: None,
                    search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                    search_debounce=0,
                )
            )
            await pilot.pause()
            app.screen.on_key(self._key_event("ctrl+f"))
            await app.screen.on_input_changed(self._changed_event("alpha"))
            await pilot.pause()

            app.screen.on_key(self._key_event("y"))
            await pilot.pause(0.2)

            self.assertEqual(copied, [os.path.abspath(alpha)])
            self.assertIn("copied path", self._widget_text(app.screen, "#dir-foot"))

            copied.clear()
            app.screen.on_key(self._key_event("ctrl+shift+c"))
            await pilot.pause(0.2)

            self.assertEqual(copied, [os.path.abspath(alpha)])
            self.assertIn("copied path", self._widget_text(app.screen, "#dir-foot"))

    async def test_dir_picker_search_right_click_menu_copies_path(self):
        import os
        import tempfile

        root = tempfile.mkdtemp()
        alpha = os.path.join(root, "alpha-app")
        os.makedirs(alpha)
        copied: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        app.copy_to_clipboard = lambda text: copied.append(text)  # type: ignore[method-assign]
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(
                DirPickerScreen(
                    root,
                    lambda path: None,
                    search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                    search_debounce=0,
                )
            )
            await pilot.pause()
            app.screen.on_key(self._key_event("ctrl+f"))
            await app.screen.on_input_changed(self._changed_event("alpha"))
            await pilot.pause()
            app.screen.on_activated(self._activated("dir_search_menu", os.path.abspath(alpha)))
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "DirSearchMenuScreen")

            app.screen.on_activated(self._activated("dir_search_copy_path", os.path.abspath(alpha)))
            await pilot.pause()

            self.assertEqual(copied, [os.path.abspath(alpha)])

    async def test_rename_screen_submits_value(self):
        captured: list[str] = []
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(RenameScreen("rename tab", "old", captured.append))
            await pilot.pause()
            self.assertIsInstance(app.screen, RenameScreen)
            app.screen.on_input_submitted(self._submit_event("newname"))
            await pilot.pause()
            self.assertEqual(captured, ["newname"])

    async def test_rename_tab_via_keys(self):
        """The real path: ctrl+b T, edit the input, press enter (regression guard)."""
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("T")
            await pilot.pause()
            self.assertIsInstance(app.screen, RenameScreen)
            from textual.widgets import Input

            app.screen.query_one("#rename-input", Input).focus()
            await pilot.pause()
            for _ in range(8):
                await pilot.press("backspace")
            for char in "renamed":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIn(("t1", "renamed"), client.renamed)
            self.assertNotIsInstance(app.screen, RenameScreen)

    async def test_rename_pane_via_keys(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("P")
            await pilot.pause()
            self.assertIsInstance(app.screen, RenameScreen)
            from textual.widgets import Input

            app.screen.query_one("#rename-input", Input).focus()
            await pilot.pause()
            for _ in range(1):
                await pilot.press("backspace")
            for char in "worker":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIn(("1-1", "worker"), client.renamed_panes)
            self.assertNotIsInstance(app.screen, RenameScreen)

    async def test_working_agent_shows_in_panel_with_spinner(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertTrue(app._has_working_agent())
            text = app._agents_text().plain
            self.assertIn("main · a", text)
            self.assertIn("working · claude", text)
            # the working agent's glyph is a braille spinner frame, not a static dot
            self.assertTrue(any(frame in text for frame in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"))

    async def test_sidebar_agent_scope_filters_to_current_workspace(self):
        client = FakeClient()
        client_state = json.loads(json.dumps(STATE))
        client_state["workspaces"].append(
            {
                "id": "ws2",
                "label": "docs",
                "cwd": "C:/docs",
                "focused_tab_id": "t9",
                "tabs": [
                    {
                        "id": "t9",
                        "label": "review",
                        "focused_pane_id": "9-1",
                        "panes": [
                            {
                                "id": "9-1",
                                "title": "release-notes",
                                "status": "blocked",
                                "running": True,
                                "agent": "codex",
                            }
                        ],
                    }
                ],
            }
        )
        client.state = lambda: client_state  # type: ignore[method-assign]

        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            text = app._agents_text().plain
            self.assertIn("agents", text)
            self.assertIn("current", text)
            self.assertIn("main · a", text)
            self.assertIn("working · claude", text)
            self.assertNotIn("docs · release-notes", text)

            app._dispatch_activated("toggle_agent_scope", None)
            await pilot.pause()

            text = app._agents_text().plain
            self.assertIn("all", text)
            self.assertIn("main · a", text)
            self.assertIn("docs · release-notes", text)
            self.assertIn("blocked · codex", text)

    async def test_sidebar_shows_attention_workspace_and_workflow_summaries(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            attention = app._attention_text().plain
            self.assertIn("working 1", attention)
            self.assertNotIn("⠋", attention)
            row = app._workspace_row_text(1, STATE["workspaces"][0], True).plain
            self.assertIn("1  ● main", row)
            self.assertIn("2 tabs", row)
            self.assertIn("working 1", row)
            footer = app._sidebar_footer_text().plain
            self.assertIn("+ workspace", footer)
            self.assertIn("+ terminal", footer)
            self.assertIn("menu", footer)

    async def test_compact_sidebar_preserves_attention_and_workspace_status(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            attention = app._compact_attention_text().plain
            self.assertIn("●", attention)
            self.assertIn("1", attention)

            row = app._compact_workspace_row_text(1, STATE["workspaces"][0], True).plain
            self.assertIn("▌", row)
            self.assertIn("1", row)
            self.assertIn("●", row)

    async def test_prefix_b_toggles_compact_sidebar(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            nav = app.query_one("#nav")
            self.assertFalse(nav.has_class("compact"))

            await pilot.press("ctrl+b")
            await pilot.press("b")
            await pilot.pause()

            self.assertTrue(app._sidebar_compact)
            self.assertTrue(nav.has_class("compact"))
            self.assertIn("►", self._widget_text(app, "#sidebar-toggle"))
            compact_nav = self._screen_text(app, "#nav")
            self.assertNotIn("attention", compact_nav)
            self.assertNotIn("agents", compact_nav)
            self.assertNotIn("spaces", compact_nav)

            app._tick()
            await pilot.pause()
            compact_nav = self._screen_text(app, "#nav")
            self.assertNotIn("agents", compact_nav)
            self.assertIn(self._widget_text(app, "#compact-agents"), compact_nav)

            await pilot.press("ctrl+b")
            await pilot.press("b")
            await pilot.pause()

            self.assertFalse(app._sidebar_compact)
            self.assertFalse(nav.has_class("compact"))
            self.assertIn("◄", self._widget_text(app, "#sidebar-toggle"))
            self.assertIn("spaces", self._screen_text(app, "#nav"))

    def test_sidebar_width_css_variable_uses_clamped_config(self):
        config = Config(ui=UiConfig(sidebar_width=80, sidebar_min_width=20, sidebar_max_width=46))
        with patch("pyherdr.presentation.tui.load_config", return_value=config):
            app = PyHerdrTui(client=FakeClient(), poll_interval=100)

        self.assertEqual(app.get_css_variables()["ph-sidebar-width"], "46")

    def test_pane_appearance_css_variables_follow_config(self):
        config = Config(ui=UiConfig(pane_separator="accent", pane_border="visible"))
        with patch("pyherdr.presentation.tui.load_config", return_value=config):
            app = PyHerdrTui(client=FakeClient(), poll_interval=100)

        variables = app.get_css_variables()
        self.assertEqual(variables["ph-pane-separator"], app._palette.accent)
        self.assertEqual(variables["ph-pane-border"], app._palette.overlay0)
        self.assertEqual(variables["ph-pane-active-border"], app._palette.accent)

    def test_help_and_palette_surface_appearance_settings(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)

        self.assertIn("appearance settings", _help_text(app._palette).plain)
        labels = [label for label, _action, _custom in app._palette_entries()]
        self.assertIn("Theme and appearance settings...", labels)

    async def test_workflow_view_opens_graph_and_log_screen(self):
        event = new_event(
            "api.request",
            message="pane read",
            source="tui",
            target="server",
            worksite="WS-121",
            agent="codex",
            pane_id="1-1",
            status="done",
            timestamp=1,
        )
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        app._workflow_events = lambda: [event]  # type: ignore[method-assign]
        async with app.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            app._dispatch_activated("workflow_view", None)
            await pilot.pause()
            self.assertIsInstance(app.screen, WorkflowScreen)
            body = app.screen._render_body().plain
            self.assertIn("terminal call graph", body)
            self.assertIn("┌", body)
            self.assertIn("──→", body)
            self.assertIn("api.request", body)
            self.assertIn("server", body)
            self.assertIn("pane read", body)
            self.assertIn("Mermaid source", body)
            self.assertIn("flowchart TD", body)
            self.assertIn("WS-121", body)

    async def test_worktree_screen_opens_removes_and_creates_worktrees(self):
        client = FakeClient()
        refreshed: list[bool] = []
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test() as pilot:
            app.push_screen(WorktreeScreen(client, refreshed.append))
            await pilot.pause()

            self.assertIsInstance(app.screen, WorktreeScreen)
            await pilot.click("#wt-open-1")
            await pilot.pause()
            self.assertEqual(client.opened_worktrees, [("C:/repo/pyherdr-sidebar", "feature/sidebar")])
            self.assertTrue(refreshed)

            app.push_screen(WorktreeScreen(client, refreshed.append))
            await pilot.pause()
            await pilot.click("#wt-remove-1")
            await pilot.pause()
            self.assertEqual(client.removed_worktrees, [("C:/repo/pyherdr-sidebar", False)])

            app.push_screen(WorktreeScreen(client, refreshed.append))
            await pilot.pause()
            await pilot.click("#wt-branch")
            await pilot.press(*"feature/new")
            await pilot.click("#wt-create")
            await pilot.pause()

        self.assertEqual(client.created_worktrees[-1]["branch"], "feature/new")

    async def test_worktree_action_opens_worktree_manager(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._run_named_action("worktrees")
            await pilot.pause()

            self.assertIsInstance(app.screen, WorktreeScreen)

    async def test_profile_action_opens_profile_picker(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        app._config = Config(profiles={"ops": ProfileConfig()})
        async with app.run_test() as pilot:
            await pilot.pause()
            app._run_named_action("profiles")
            await pilot.pause()

            self.assertIsInstance(app.screen, ProfilePickerScreen)

    async def test_profile_picker_launches_profile_workflow_command(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        app._config = Config(
            profiles={"ops": ProfileConfig()},
            workflows={"health": WorkflowConfig(profile="ops")},
        )
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._run_named_action("profiles")
            await pilot.pause()
            await pilot.click("#profile-1")
            await pilot.pause()
            await pilot.pause()

        self.assertEqual(client.tabs, 1)
        self.assertIn(("new-pane", "pyherdr profile start ops --workflow health"), client.started)

    async def test_prefix_then_a_cycles_attention_panes(self):
        client = FakeClient()
        client_state = json.loads(json.dumps(STATE))
        client_state["workspaces"][0]["tabs"][0]["panes"][1]["status"] = "done"
        client_state["workspaces"][0]["tabs"][1]["panes"][0]["status"] = "blocked"
        client.state = lambda: client_state  # type: ignore[method-assign]
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            await pilot.press("ctrl+b")
            await pilot.press("a")
            await pilot.pause()

            self.assertEqual(app._tab_id, "t1")
            self.assertEqual(app._pane_id, "1-2")
            self.assertEqual(client.focused_agents[-1], (None, True))

            await pilot.press("ctrl+b")
            await pilot.press("a")
            await pilot.pause()

            self.assertEqual(app._tab_id, "t2")
            self.assertEqual(app._pane_id, "2-1")

    def test_workflow_terminal_graph_centers_arrows_and_marks_cycles(self):
        request = new_event(
            "api.request",
            message="pane read",
            source="tui",
            target="server",
            status="done",
        )
        response = new_event(
            "api.response",
            message="pane data returned",
            source="server",
            target="tui",
            status="done",
        )

        request_rows = WorkflowScreen._call_graph_event_rows(request)
        response_rows = WorkflowScreen._call_graph_event_rows(response)

        self.assertNotIn("──→", request_rows[1])
        self.assertIn("──→", request_rows[2])
        self.assertIn("response/cycle back", "\n".join(response_rows))
        self.assertIn("←", "\n".join(response_rows))

    async def test_prefix_then_g_navigator_jumps(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("g")
            await pilot.pause()
            self.assertIsInstance(app.screen, NavigatorScreen)
            await pilot.click("#nav-2")  # ws1 · t2 · 2-1 (third pane overall)
            await pilot.pause()
            self.assertEqual(app._tab_id, "t2")
            self.assertEqual(app._pane_id, "2-1")
            self.assertNotIsInstance(app.screen, NavigatorScreen)

    async def test_tab_context_menu_close(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._dispatch_activated("ctx_tab", "t1")
            await pilot.pause()
            self.assertIsInstance(app.screen, ContextMenuScreen)
            await pilot.click("#ctx-1")  # "close"
            await pilot.pause()
            await pilot.pause()
            self.assertIn("t1", client.closed_tabs)

    async def test_pane_context_menu_split(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._dispatch_activated("ctx_pane", "1-2")
            await pilot.pause()
            self.assertIsInstance(app.screen, ContextMenuScreen)
            await pilot.click("#ctx-0")  # "split right"
            await pilot.pause()
            await pilot.pause()
            self.assertEqual(client.splits, ["horizontal"])
            self.assertEqual(client.split_targets, [("horizontal", "1-2")])

    async def test_drag_resize_persists_layout(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            app._remember_ratio((), 0.7)  # simulate dragging the root split divider
            app.persist_layout()
            await pilot.pause()
            self.assertTrue(client.layouts)
            self.assertAlmostEqual(client.layouts[-1]["root"]["ratio"], 0.7, places=2)

    async def test_navigator_search_filters_and_jumps(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.press("g")
            await pilot.pause()
            self.assertIsInstance(app.screen, NavigatorScreen)
            from textual.widgets import Input

            app.screen.query_one("#nav-search", Input).focus()
            await pilot.pause()
            for char in "logs":
                await pilot.press(char)
            await pilot.pause()
            await pilot.press("enter")  # jump to the only match (t2 'logs')
            await pilot.pause()
            self.assertEqual(app._tab_id, "t2")
            self.assertEqual(app._pane_id, "2-1")

    async def test_pageup_scrolls_focused_pane(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("pageup")
            await pilot.pause()
            self.assertIn(("1-1", "up"), client.scrolled)
            await pilot.press("pagedown")
            await pilot.pause()
            self.assertIn(("1-1", "down"), client.scrolled)

    async def test_mouse_wheel_host_scrolls_plain_terminal(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._terminal_metadata["1-1"] = {"alt_screen": False, "mouse_reporting": False}

            app._handle_pane_wheel("1-1", "up", 7, 3)

            self.assertEqual(client.scrolled, [("1-1", "up")])
            self.assertEqual(client.sent_text, [])

    async def test_mouse_wheel_forwards_when_pane_owns_mouse(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._terminal_metadata["1-1"] = {"alt_screen": False, "mouse_reporting": True}

            app._handle_pane_wheel("1-1", "down", 7, 3)

            self.assertEqual(client.scrolled, [])
            self.assertEqual(client.sent_text, [("1-1", "\x1b[<65;7;3M")])

    async def test_mouse_wheel_forwards_in_alt_screen(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._terminal_metadata["1-1"] = {"alt_screen": True, "mouse_reporting": False}

            app._handle_pane_wheel("1-1", "up", 2, 4)

            self.assertEqual(client.scrolled, [])
            self.assertEqual(client.sent_text, [("1-1", "\x1b[<64;2;4M")])

    async def test_tick_does_not_poll_pane_output(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            client.reads.clear()
            app._tick()
            await pilot.pause()
            self.assertEqual(client.reads, [])

    async def test_output_wait_updates_changed_pane_only(self):
        class EventClient(FakeClient):
            def pane_wait_output(self, versions: dict[str, int], timeout: float = 1.0) -> dict:
                self.waits.append(dict(versions))
                return {
                    "type": "pane_output_wait",
                    "changed": {"1-2": 1},
                    "versions": {"1-1": 0, "1-2": 1},
                    "timed_out": False,
                }

        client = EventClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            client.reads.clear()
            await app._terminal_refresh_loop_step()
            self.assertIn(("1-2", 400, True, False), client.reads)
            self.assertNotIn(("1-1", 400, True, True), client.reads)

    async def test_new_workspace_opens_dir_picker_and_creates(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._open_new_workspace()
            await pilot.pause()
            self.assertIsInstance(app.screen, DirPickerScreen)
            app.screen.on_activated(self._activated("dir_open", None))  # open the starting folder
            await pilot.pause()
            self.assertTrue(client.created_workspaces)

    async def test_new_workspace_picker_starts_from_focused_workspace_cwd(self):
        import os
        import tempfile

        workspace_cwd = tempfile.mkdtemp()
        state = {
            "focused_workspace_id": "wsx",
            "workspaces": [
                {
                    "id": "wsx",
                    "label": "project",
                    "cwd": workspace_cwd,
                    "focused_tab_id": "tx",
                    "tabs": [{"id": "tx", "focused_pane_id": "px", "panes": [{"id": "px", "running": True}]}],
                }
            ],
        }
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        app._state = state
        app._workspace_id = "wsx"

        self.assertEqual(app._workspace_picker_start(), os.path.abspath(workspace_cwd))

    async def test_new_workspace_picker_includes_recent_roots(self):
        import os
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.abspath(tmp)
            runtime = os.path.join(root, "runtime")
            current = os.path.join(root, "current")
            recent = os.path.join(root, "recent")
            os.makedirs(current)
            os.makedirs(recent)
            with patch.dict(
                "os.environ",
                {"PYHERDR_PORTABLE": "0", "PYHERDR_RUNTIME_DIR": runtime},
                clear=False,
            ):
                record_workspace_recent(recent, label="recent project", now=1.0)
                app = PyHerdrTui(client=FakeClient(), poll_interval=100)
                app._state = {
                    "focused_workspace_id": "wsx",
                    "workspaces": [
                        {
                            "id": "wsx",
                            "label": "current",
                            "cwd": current,
                            "tabs": [],
                        }
                    ],
                }
                app._workspace_id = "wsx"
                quick_paths = app._workspace_picker_quick_paths()

        self.assertIn(("recent: recent project", os.path.abspath(recent)), quick_paths)

    async def test_new_workspace_picker_search_roots_include_stale_recents(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            current = root / "current"
            missing = root / "ghostc-plugin"
            current.mkdir()
            recents_path = runtime / "workspace_recents.json"
            recents_path.parent.mkdir(parents=True)
            recents_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "roots": [
                            {"path": str(missing), "label": "ghostc-plugin", "last_opened": 1.0, "repo_root": ""},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {"PYHERDR_PORTABLE": "0", "PYHERDR_RUNTIME_DIR": str(runtime)},
                clear=False,
            ):
                app = PyHerdrTui(client=FakeClient(), poll_interval=100)
                app._state = {
                    "focused_workspace_id": "wsx",
                    "workspaces": [
                        {
                            "id": "wsx",
                            "label": "current",
                            "cwd": str(current),
                            "tabs": [],
                        }
                    ],
                }
                app._workspace_id = "wsx"
                quick_paths = app._workspace_picker_quick_paths()
                roots = app._workspace_picker_search_roots()

        self.assertNotIn(("recent: ghostc-plugin", os.path.abspath(missing)), quick_paths)
        self.assertIn(SearchRoot(os.path.abspath(missing), label="ghostc-plugin", source="recent"), roots)

    async def test_new_workspace_picker_uses_configured_search_roots(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configured = root / "configured-projects"
            configured.mkdir()
            current = root / "current"
            current.mkdir()
            config_path = root / "config.toml"
            config_path.write_text(
                f"""
[workspace]
search_roots = ["{configured.as_posix()}"]
""".strip(),
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"PYHERDR_CONFIG_PATH": str(config_path)}, clear=False):
                app = PyHerdrTui(client=FakeClient(), poll_interval=100)
                app._state = {
                    "focused_workspace_id": "wsx",
                    "workspaces": [
                        {
                            "id": "wsx",
                            "label": "current",
                            "cwd": str(current),
                            "tabs": [],
                        }
                    ],
                }
                app._workspace_id = "wsx"
                roots = app._workspace_picker_search_roots()

        self.assertIn(SearchRoot(os.path.abspath(configured), label="configured-projects", source="configured"), roots)

    async def test_dir_picker_search_uses_configured_scan_options(self):
        import tempfile
        from unittest.mock import patch

        root = tempfile.mkdtemp()
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        with patch("pyherdr.presentation.tui.search_workspace_rows", return_value=[]) as search:
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                app.push_screen(
                    DirPickerScreen(
                        root,
                        lambda path: None,
                        search_roots=[SearchRoot(root, label="tmp", source="workspace")],
                        search_debounce=0,
                        search_max_depth=2,
                        search_max_results=7,
                        search_ignore_names=["vendor", "node_modules"],
                        search_include_hidden=True,
                    )
                )
                await pilot.pause()
                app.screen.on_key(self._key_event("ctrl+f"))
                await app.screen.on_input_changed(self._changed_event("alpha"))
                await pilot.pause(0.2)

        self.assertEqual(search.call_count, 1)
        _args, kwargs = search.call_args
        self.assertEqual(kwargs["max_depth"], 2)
        self.assertEqual(kwargs["max_results"], 7)
        self.assertEqual(kwargs["ignore_names"], ("vendor", "node_modules"))
        self.assertTrue(kwargs["include_hidden"])

    async def test_move_workspace_up_down(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._run_prefix_action("}", "}")  # prefix + } = move workspace down
            await pilot.pause()
            self.assertIn(("ws1", "down"), client.moved_workspaces)

    async def test_move_tab_left_right(self):
        from unittest.mock import patch

        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            def close_worker(coro, *_args, **_kwargs):
                coro.close()
                return None

            with patch.object(app, "run_worker", side_effect=close_worker):
                app._run_prefix_action(">", ">")  # prefix + > = move tab right
                self.assertIn(("t1", "right"), client.moved)
                app._run_prefix_action("<", "<")  # prefix + < = move tab left
                self.assertIn(("t1", "left"), client.moved)

    async def test_custom_command_runs_in_new_tab(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        app._commands = {"g": "lazygit"}  # as if [[keys.commands]] key="prefix+g" command="lazygit"
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._run_prefix_action("g", "g")  # prefix + g
            await pilot.pause()
            self.assertEqual(client.tabs, 1)
            self.assertIn(("new-pane", "lazygit"), client.started)

    async def test_remapped_key_triggers_action(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        app._prefix_actions["t"] = "new_tab"  # as if [keys.bindings] new_tab = "t"
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._run_prefix_action("t", "t")
            await pilot.pause()
            self.assertEqual(client.tabs, 1)

    async def test_background_agent_blocked_emits_toast(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._state = {
                "workspaces": [
                    {"id": "w", "tabs": [{"id": "t", "panes": [{"id": "p1", "agent": "claude", "status": "working"}]}]}
                ]
            }
            app._pane_id = "other"  # p1 is a background pane
            app._emit_agent_toasts()  # seed: working
            calls: list = []
            app.notify = lambda *a, **k: calls.append((a, k))  # type: ignore[method-assign]
            app._state["workspaces"][0]["tabs"][0]["panes"][0]["status"] = "blocked"
            app._emit_agent_toasts()
            self.assertTrue(calls)
            self.assertIn("needs attention", calls[0][0][0])

    async def test_command_palette_runs_action(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._open_command_palette()
            await pilot.pause()
            self.assertIsInstance(app.screen, CommandPaletteScreen)
            entries = app._palette_entries()
            index = next(i for i, (_l, value, _c) in enumerate(entries) if value == "new_tab")
            app.screen.on_activated(self._activated("palette_pick", str(index)))
            await pilot.pause()
            await pilot.pause()
            self.assertEqual(client.tabs, 1)

    async def test_fanout_picker_previews_selected_target_then_executes(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            app._run_named_action("fanout")
            await pilot.pause()
            self.assertIsInstance(app.screen, FanoutScreen)
            await pilot.click("#fanout-target-1")  # current tab
            await pilot.pause()

            from textual.widgets import Input

            app.screen.query_one("#fanout-command", Input).value = "pytest -q"
            app.screen.on_input_submitted(self._submit_event("pytest -q"))
            await pilot.pause()
            self.assertEqual(client.fanouts[-1]["targets"], ["tab:t1"])
            self.assertTrue(client.fanouts[-1]["dry_run"])
            preview = app.screen.query_one("#fanout-preview").render()
            self.assertIn("2 panes", preview.plain if hasattr(preview, "plain") else str(preview))

            await pilot.click("#fanout-send")
            await pilot.pause()
            self.assertEqual(client.fanouts[-1]["targets"], ["tab:t1"])
            self.assertFalse(client.fanouts[-1]["dry_run"])
            self.assertTrue(client.fanouts[-1]["confirm_risky"])
            self.assertEqual(client.fanouts[-1]["text"], "pytest -q")

    async def test_fanout_picker_warns_on_risky_preview(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            app._run_named_action("fanout")
            await pilot.pause()
            await pilot.click("#fanout-target-1")  # current tab, two panes
            await pilot.pause()

            from textual.widgets import Input

            app.screen.query_one("#fanout-command", Input).value = "rm -rf build"
            app.screen.on_input_submitted(self._submit_event("rm -rf build"))
            await pilot.pause()
            preview = app.screen.query_one("#fanout-preview").render()
            text = preview.plain if hasattr(preview, "plain") else str(preview)
            self.assertIn("risk", text.lower())
            self.assertIn("recursive force remove", text)

    async def test_pane_menu_close(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._pane_id = "1-1"
            app._open_pane_menu()
            await pilot.pause()
            self.assertIsInstance(app.screen, ContextMenuScreen)
            await pilot.click("#ctx-9")
            await pilot.pause()
            await pilot.pause()
            self.assertIn("1-1", client.closed_panes)

    async def test_pane_menu_rename(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._pane_id = "1-1"
            app._open_pane_menu()
            await pilot.pause()
            self.assertIsInstance(app.screen, ContextMenuScreen)
            await pilot.click("#ctx-10")
            await pilot.pause()
            await pilot.pause()
            self.assertIsInstance(app.screen, RenameScreen)
            app.screen.on_input_submitted(self._submit_event("menu-pane"))
            await pilot.pause()
            self.assertIn(("1-1", "menu-pane"), client.renamed_panes)

    async def test_copy_mode_selects_and_copies_scrollback_lines(self):
        class ScrollbackClient(FakeClient):
            def pane_read(self, pane_id: str, lines: int = 200, styled: bool = False, cursor: bool = False) -> str:
                self.reads.append((pane_id, lines, styled, cursor))
                return "alpha\nbeta\ngamma"

        client = ScrollbackClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            copied: list[str] = []
            app.copy_to_clipboard = lambda text: copied.append(text)  # type: ignore[method-assign]
            app._pane_id = "1-1"

            app._run_named_action("copy_mode")
            await pilot.pause()
            self.assertIsInstance(app.screen, CopyModeScreen)
            self.assertEqual(client.reads[-1], ("1-1", 2000, False, False))

            app.screen.on_key(self._key_event("g"))
            app.screen.on_key(self._key_event("space"))
            app.screen.on_key(self._key_event("down"))
            app.screen.on_key(self._key_event("y"))
            await pilot.pause()

            self.assertEqual(copied, ["alpha\nbeta"])
            self.assertNotIsInstance(app.screen, CopyModeScreen)

    async def test_copy_pane_output_to_clipboard(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            copied: list[str] = []
            app.copy_to_clipboard = lambda text: copied.append(text)  # type: ignore[method-assign]
            app._pane_id = "1-1"
            app._run_named_action("copy_output")
            await pilot.pause()
            self.assertTrue(copied)
            self.assertIn("SCREEN:1-1", copied[0])

    async def test_open_url_picker_extracts_and_opens_urls(self):
        class UrlClient(FakeClient):
            def pane_read(self, pane_id: str, lines: int = 200, styled: bool = False, cursor: bool = False) -> str:
                self.reads.append((pane_id, lines, styled, cursor))
                return "dev server at https://localhost:3000/app\nlogs http://127.0.0.1:8000/logs."

        client = UrlClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        opened: list[str] = []
        app._url_opener = lambda url: opened.append(url) or True
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._pane_id = "1-1"
            app._run_named_action("open_url")
            await pilot.pause()

            self.assertIsInstance(app.screen, UrlPickerScreen)
            self.assertEqual(client.reads[-1], ("1-1", 2000, False, False))
            await pilot.click("#url-1")
            await pilot.pause()

        self.assertEqual(opened, ["http://127.0.0.1:8000/logs"])

    async def test_agent_pane_resumes_its_command(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._state = {
                "workspaces": [
                    {
                        "id": "w",
                        "tabs": [
                            {
                                "id": "t",
                                "focused_pane_id": "p",
                                "panes": [
                                    {
                                        "id": "p",
                                        "agent": "claude",
                                        "command": "claude",
                                        "status": "working",
                                        "running": False,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
            app._workspace_id, app._tab_id = "w", "t"
            client.started.clear()
            app._ensure_shells()
            self.assertIn(("p", "claude"), client.started)  # resumed the agent, not a blank shell

    async def test_keys_forward_to_active_pane(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            for _ in range(20):
                await pilot.pause(0.05)
                if ("1-1", "a") in client.sent_text:
                    break
            self.assertIn(("1-1", "a"), client.sent_text)

    async def test_typing_pins_active_pane_to_bottom_before_forwarding_text(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test() as pilot:
            await pilot.pause()
            client.events.clear()
            await pilot.press("a")
            for _ in range(20):
                await pilot.pause(0.05)
                if ("1-1", "a") in client.sent_text:
                    break

            self.assertIn(("1-1", "bottom"), client.scrolled)
            self.assertIn(("send_text", "1-1"), client.events)
            self.assertLess(client.events.index(("scroll", "1-1:bottom")), client.events.index(("send_text", "1-1")))

    async def test_terminal_input_does_not_block_key_handler(self):
        started = threading.Event()
        release = threading.Event()

        class BlockingInputClient(FakeClient):
            def send_text(self, pane_id: str, text: str) -> None:
                started.set()
                release.wait(5)
                super().send_text(pane_id, text)

        client = BlockingInputClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            self.assertTrue(started.wait(1))

            before = time.perf_counter()
            await pilot.press("b")
            self.assertLess(time.perf_counter() - before, 0.5)

            release.set()
            for _ in range(30):
                await pilot.pause(0.05)
                if ("1-1", "b") in client.sent_text:
                    break
            self.assertIn(("1-1", "a"), client.sent_text)
            self.assertIn(("1-1", "b"), client.sent_text)

    async def test_clicking_plus_creates_a_tab(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#tabplus")
            await pilot.pause()
            self.assertEqual(client.tabs, 1)

    async def test_switching_workspace_focuses_it_on_server(self):
        # regression: closing tabs on another workspace failed because the server
        # was never told the UI switched workspaces.
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._dispatch_activated("switch_workspace", "ws9")
            await pilot.pause()
            self.assertIn("ws9", client.focused_workspaces)

    async def test_workspace_context_menu_close(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._dispatch_activated("ctx_workspace", "ws1")
            await pilot.pause()
            self.assertIsInstance(app.screen, ContextMenuScreen)
            await pilot.click("#ctx-5")  # "close" (switch/rename/up/down/resource-usage/close)
            await pilot.pause()
            await pilot.pause()
            self.assertIn("ws1", client.closed_workspaces)

    async def test_clicking_tab_close_closes_tab(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#tabclose-t1")
            await pilot.pause()
            self.assertIn("t1", client.closed_tabs)

    async def test_tab_bar_overflow_controls_scroll_inner_strip(self):
        state = json.loads(json.dumps(STATE))
        tabs = []
        for index in range(12):
            tab_id = f"tab-{index}"
            pane_id = f"pane-{index}"
            tabs.append(
                {
                    "id": tab_id,
                    "label": f"long-tab-name-{index:02d}",
                    "focused_pane_id": pane_id,
                    "panes": [{"id": pane_id, "title": f"p{index}", "status": "idle", "running": True}],
                }
            )
        workspace = state["workspaces"][0]
        workspace["tabs"] = tabs
        workspace["focused_tab_id"] = "tab-0"
        client = FakeClient()
        client.state = lambda: state  # type: ignore[method-assign]
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(60, 24)) as pilot:
            await pilot.pause()
            strip = app.query_one("#tabstrip")
            self.assertIsNotNone(app.query_one("#tabscroll-left"))
            self.assertIsNotNone(app.query_one("#tabscroll-right"))
            self.assertIsNotNone(app.query_one("#tabplus"))

            before = strip.scroll_x
            await pilot.click("#tabscroll-right")
            await pilot.pause()
            self.assertGreater(strip.scroll_x, before)

            await pilot.click("#tabscroll-left")
            await pilot.pause()
            self.assertLessEqual(strip.scroll_x, before + 1)

    async def test_shell_dropdown_creates_tab_with_chosen_shell(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#newterm")  # open the dropdown
            await pilot.pause()
            self.assertIsInstance(app.screen, ShellPickerScreen)
            _label, command = app._shells[0]
            await pilot.click("#shellpick-0")
            await pilot.pause()
            await pilot.pause()
            self.assertEqual(client.tabs, 1)
            self.assertIn(("new-pane", command), client.started)

    async def test_shell_dropdown_launches_agent_preset(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        app._launcher_presets = [LauncherPreset("codex", "Codex", "codex", "Launch Codex", "codex", True)]
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#newterm")
            await pilot.pause()
            self.assertIsInstance(app.screen, ShellPickerScreen)
            await pilot.click("#launchpick-0")
            await pilot.pause()
            await pilot.pause()

        self.assertEqual(client.tabs, 1)
        self.assertIn(("new-pane", "codex"), client.started)

    async def test_command_palette_includes_launcher_presets(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        app._launcher_presets = [LauncherPreset("claude", "Claude Code", "claude", "Launch Claude", "claude", True)]
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            entries = app._palette_entries()
            index = next(i for i, (label, _value, _is_command) in enumerate(entries) if label == "Launch: Claude Code")
            app.run_palette_entry(entries[index][1], entries[index][2])
            await pilot.pause()
            await pilot.pause()

        self.assertEqual(client.tabs, 1)
        self.assertIn(("new-pane", "claude"), client.started)

    async def test_shell_dropdown_allows_shell_labels_with_spaces(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        command = "cmd.exe"
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.push_screen(ShellPickerScreen([("Command Prompt", command)]))
            await pilot.pause()
            self.assertIsInstance(app.screen, ShellPickerScreen)
            await pilot.click("#shellpick-0")
            await pilot.pause()
            await pilot.pause()
            self.assertEqual(client.tabs, 1)
            self.assertIn(("new-pane", command), client.started)

    async def test_clicking_pane_focuses_it(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#pane-1-2")
            await pilot.pause()
            self.assertEqual(app._pane_id, "1-2")


if __name__ == "__main__":
    unittest.main()
