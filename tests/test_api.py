import unittest
from pathlib import Path
from unittest.mock import patch

from pyherdr.api import dispatch
from pyherdr.models import AppState
from pyherdr.workspace_recents import load_workspace_recents, prune_workspace_recents


class _FakeProcesses:
    def __init__(self) -> None:
        self.broadcasts: list[tuple[list[str], str]] = []

    def broadcast(self, pane_ids: list[str], text: str) -> int:
        self.broadcasts.append((list(pane_ids), text))
        return len(pane_ids)


class ApiTests(unittest.TestCase):
    def test_ping(self):
        state = AppState.bootstrap(cwd="C:/work")

        response = dispatch(state, {"id": "1", "method": "ping", "params": {}})

        self.assertEqual(response["id"], "1")
        self.assertEqual(response["result"]["type"], "pong")

    def test_workspace_create_adds_tab_and_pane(self):
        state = AppState.bootstrap(cwd="C:/work")

        response = dispatch(
            state,
            {
                "id": "1",
                "method": "workspace.create",
                "params": {"label": "api", "cwd": "C:/api"},
            },
        )

        self.assertEqual(response["result"]["workspace"]["label"], "api")
        self.assertEqual(len(state.focused_workspace.tabs), 1)
        self.assertEqual(len(state.focused_workspace.focused_tab.panes), 1)

    def test_workspace_create_records_recent_root(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            workspace = root / "project"
            workspace.mkdir()
            with patch.dict(
                "os.environ",
                {"PYHERDR_PORTABLE": "0", "PYHERDR_RUNTIME_DIR": str(runtime)},
                clear=False,
            ):
                state = AppState.bootstrap(cwd=str(root))
                dispatch(
                    state,
                    {
                        "id": "1",
                        "method": "workspace.create",
                        "params": {"label": "api", "cwd": str(workspace)},
                    },
                )

                recents = load_workspace_recents()

        self.assertEqual(recents[0]["path"], str(workspace.resolve()))
        self.assertEqual(recents[0]["label"], "api")

    def test_workspace_recents_can_include_and_prune_stale_roots(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "existing"
            stale = root / "missing"
            existing.mkdir()
            recents_path = root / "workspace_recents.json"
            recents_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "roots": [
                            {"path": str(stale), "label": "gone", "last_opened": 2.0, "repo_root": ""},
                            {"path": str(existing), "label": "here", "last_opened": 1.0, "repo_root": ""},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            visible = load_workspace_recents(recents_path)
            all_roots = load_workspace_recents(recents_path, include_stale=True)
            summary = prune_workspace_recents(recents_path)

            after_prune = load_workspace_recents(recents_path, include_stale=True)

        self.assertEqual([record["label"] for record in visible], ["here"])
        self.assertEqual([record["label"] for record in all_roots], ["gone", "here"])
        self.assertTrue(all_roots[0]["stale"])
        self.assertFalse(all_roots[1]["stale"])
        self.assertEqual(summary["removed"], 1)
        self.assertEqual(summary["kept"], 1)
        self.assertEqual([record["label"] for record in after_prune], ["here"])

    def test_pane_report_agent_changes_status(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane

        response = dispatch(
            state,
            {
                "id": "1",
                "method": "pane.report_agent",
                "params": {"pane_id": pane.id, "state": "blocked", "message": "approval"},
            },
        )

        self.assertEqual(response["result"]["pane"]["agent_status"], "blocked")
        self.assertEqual(pane.custom_status, "approval")

    def test_pane_fanout_dry_run_resolves_mixed_targets_without_sending(self):
        state = AppState.bootstrap(cwd="C:/work")
        main = state.focused_workspace
        main.label = "main"
        main_pane = main.focused_tab.focused_pane
        main_pane.title = "loop"
        other = state.create_workspace("docs", "C:/docs")
        state.create_tab(other.id, "review")
        other_pane = other.focused_tab.focused_pane
        processes = _FakeProcesses()

        response = dispatch(
            state,
            {
                "id": "fanout",
                "method": "pane.fanout",
                "params": {
                    "targets": ["session:current", "workspace:main", "tab:review", f"pane:{main_pane.id}"],
                    "text": "pytest -q",
                    "dry_run": True,
                },
            },
            processes,
        )

        result = response["result"]
        self.assertEqual(result["type"], "pane_fanout")
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["target_count"], 2)
        self.assertEqual([target["pane_id"] for target in result["targets"]], [main_pane.id, other_pane.id])
        self.assertEqual(processes.broadcasts, [])

    def test_pane_fanout_execute_sends_to_agent_targets_without_enter(self):
        state = AppState.bootstrap(cwd="C:/work")
        first = state.focused_workspace.focused_tab.focused_pane
        first.agent = "codex"
        second = state.create_pane(state.focused_workspace.id, state.focused_workspace.focused_tab.id, "review")
        second.agent = "codex"
        third = state.create_pane(state.focused_workspace.id, state.focused_workspace.focused_tab.id, "logs")
        third.agent = "claude"
        processes = _FakeProcesses()

        response = dispatch(
            state,
            {
                "id": "fanout",
                "method": "pane.fanout",
                "params": {
                    "targets": ["agent:codex"],
                    "text": "git status",
                    "enter": False,
                    "dry_run": False,
                },
            },
            processes,
        )

        result = response["result"]
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["sent"], 2)
        self.assertEqual(processes.broadcasts, [([first.id, second.id], "git status")])
        self.assertNotIn(third.id, [target["pane_id"] for target in result["targets"]])

    def test_pane_fanout_risky_multi_pane_command_requires_confirmation(self):
        state = AppState.bootstrap(cwd="C:/work")
        first = state.focused_workspace.focused_tab.focused_pane
        second = state.create_pane(state.focused_workspace.id, state.focused_workspace.focused_tab.id, "review")
        processes = _FakeProcesses()

        preview = dispatch(
            state,
            {
                "id": "fanout",
                "method": "pane.fanout",
                "params": {"targets": ["all"], "text": "rm -rf build", "dry_run": True},
            },
            processes,
        )

        preview_result = preview["result"]
        self.assertTrue(preview_result["requires_confirmation"])
        self.assertIn("recursive force remove", preview_result["risk"])

        blocked = dispatch(
            state,
            {
                "id": "fanout",
                "method": "pane.fanout",
                "params": {"targets": ["all"], "text": "rm -rf build", "dry_run": False},
            },
            processes,
        )

        self.assertIn("error", blocked)
        self.assertIn("confirm_risky", blocked["error"]["message"])
        self.assertEqual(processes.broadcasts, [])

        confirmed = dispatch(
            state,
            {
                "id": "fanout",
                "method": "pane.fanout",
                "params": {
                    "targets": ["all"],
                    "text": "rm -rf build",
                    "dry_run": False,
                    "confirm_risky": True,
                },
            },
            processes,
        )

        self.assertEqual(confirmed["result"]["sent"], 2)
        self.assertEqual(processes.broadcasts, [([first.id, second.id], "rm -rf build\n")])


if __name__ == "__main__":
    unittest.main()
