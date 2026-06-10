import unittest

from pyherdr.presentation.tui import (
    CommandPaletteScreen,
    ContextMenuScreen,
    DirPickerScreen,
    FanoutScreen,
    HelpScreen,
    NavigatorScreen,
    PaneView,
    PyHerdrTui,
    RenameScreen,
    ShellPickerScreen,
    ThemeScreen,
    WorkflowScreen,
)
from pyherdr.workflow import new_event
from pyherdr.workspace_recents import record_workspace_recent

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
        self.scrolled: list[tuple[str, str]] = []
        self.moved: list[tuple[str, str]] = []
        self.moved_workspaces: list[tuple[str, str]] = []
        self.created_workspaces: list[tuple[str, str]] = []
        self.focused_workspaces: list[str] = []
        self.focused_tabs: list[str] = []
        self.renamed_workspaces: list[tuple[str, str]] = []
        self.closed_workspaces: list[str] = []
        self.fanouts: list[dict] = []

    def state(self) -> dict:
        return STATE

    def stats(self) -> dict:
        return {"available": True, "stats": {}}

    def pane_read(self, pane_id: str, lines: int = 200, styled: bool = False, cursor: bool = False) -> str:
        return f"SCREEN:{pane_id}"

    def send_text(self, pane_id: str, text: str) -> None:
        self.sent_text.append((pane_id, text))

    def send_key(self, pane_id: str, key: str) -> None:
        self.sent_key.append((pane_id, key))

    def pane_scroll(self, pane_id: str, direction: str) -> None:
        self.scrolled.append((pane_id, direction))

    def create_tab(self, label: str = "shell") -> dict:
        self.tabs += 1
        return {"result": {"tab": {"focused_pane_id": "new-pane"}}}

    def create_pane(self, title: str = "pane") -> dict:
        self.panes += 1
        return {"result": {"pane": {"pane_id": "new-pane"}}}

    def split_pane(self, direction: str = "horizontal") -> dict:
        self.splits.append(direction)
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


class TuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_renders_a_view_per_pane_in_focused_tab(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(len(list(app.query(PaneView))), 2)

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
    def _screen_text(screen: object, selector: str) -> str:
        widget = screen.query_one(selector)
        lines: list[str] = []
        for child in widget.children:
            renderable = child.render()
            lines.append(renderable.plain if hasattr(renderable, "plain") else str(renderable))
        return "\n".join(lines)

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

    async def test_working_agent_shows_in_panel_with_spinner(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertTrue(app._has_working_agent())
            text = app._agents_text().plain
            self.assertIn("claude · a", text)
            self.assertIn("main › shell", text)
            # the working agent's glyph is a braille spinner frame, not a static dot
            self.assertTrue(any(frame in text for frame in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"))

    async def test_sidebar_shows_attention_workspace_and_workflow_summaries(self):
        app = PyHerdrTui(client=FakeClient(), poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            attention = app._attention_text().plain
            self.assertIn("working 1", attention)
            self.assertIn("agents 1  panes 3", attention)
            row = app._workspace_row_text(1, STATE["workspaces"][0], True).plain
            self.assertIn("1 ● main", row)
            self.assertIn("2 tabs", row)
            self.assertIn("working 1", row)
            workflow = app._workflow_text().plain
            self.assertIn("workflow", workflow)
            self.assertIn("calls  logs  graph", workflow)

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

    async def test_move_workspace_up_down(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._run_prefix_action("}", "}")  # prefix + } = move workspace down
            await pilot.pause()
            self.assertIn(("ws1", "down"), client.moved_workspaces)

    async def test_move_tab_left_right(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._run_prefix_action(">", ">")  # prefix + > = move tab right
            await pilot.pause()
            self.assertIn(("t1", "right"), client.moved)
            app._run_prefix_action("<", "<")  # prefix + < = move tab left
            await pilot.pause()
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
            await pilot.click("#ctx-7")  # "close pane" (after split×2, zoom, scroll×2, copy, resource usage)
            await pilot.pause()
            await pilot.pause()
            self.assertIn("1-1", client.closed_panes)

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
            await pilot.pause()
            self.assertIn(("1-1", "a"), client.sent_text)

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

    async def test_shell_dropdown_creates_tab_with_chosen_shell(self):
        client = FakeClient()
        app = PyHerdrTui(client=client, poll_interval=100)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#newterm")  # open the dropdown
            await pilot.pause()
            self.assertIsInstance(app.screen, ShellPickerScreen)
            label, command = app._shells[0]
            await pilot.click(f"#shellpick-{label}")
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
