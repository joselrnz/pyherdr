import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pyherdr.api import dispatch
from pyherdr.models import AgentStatus, AppState
from pyherdr.workspace_recents import load_workspace_recents, prune_workspace_recents, remove_workspace_recent


class _FakeProcesses:
    def __init__(self) -> None:
        self.broadcasts: list[tuple[list[str], str]] = []

    def broadcast(self, pane_ids: list[str], text: str) -> int:
        self.broadcasts.append((list(pane_ids), text))
        return len(pane_ids)


class _CaptureProcesses:
    """A manager with a live session whose full buffer/styled screen are fixed."""

    def __init__(self, buffer: str, styled: str = "") -> None:
        self._buffer = buffer
        self._styled = styled or buffer

    def read(self, pane_id: str, lines=None) -> str:
        return self._buffer

    def render_styled(self, pane_id: str, cursor: bool = False) -> str:
        return self._styled


class _NoSessionProcesses:
    """A manager with no live session for the pane (read raises KeyError)."""

    def read(self, pane_id: str, lines=None) -> str:
        raise KeyError(pane_id)


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

    def test_workspace_recents_can_remove_one_root(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "existing"
            stale_one = root / "missing-one"
            stale_two = root / "missing-two"
            existing.mkdir()
            recents_path = root / "workspace_recents.json"
            recents_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "roots": [
                            {"path": str(stale_one), "label": "one", "last_opened": 3.0, "repo_root": ""},
                            {"path": str(stale_two), "label": "two", "last_opened": 2.0, "repo_root": ""},
                            {"path": str(existing), "label": "here", "last_opened": 1.0, "repo_root": ""},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = remove_workspace_recent(stale_one, recents_path)
            after_remove = load_workspace_recents(recents_path, include_stale=True)

        self.assertEqual(summary["removed"], 1)
        self.assertEqual(summary["kept"], 2)
        self.assertEqual([record["label"] for record in after_remove], ["two", "here"])

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

    def _capture(self, state, processes, params=None):
        pane = state.focused_workspace.focused_tab.focused_pane
        request = {"id": "c", "method": "pane.capture", "params": {"pane_id": pane.id, **(params or {})}}
        return dispatch(state, request, processes)["result"]

    def test_pane_capture_returns_full_buffer_with_counts(self):
        state = AppState.bootstrap(cwd="C:/work")
        buffer = "line one\nline two\nline three"

        result = self._capture(state, _CaptureProcesses(buffer))

        self.assertEqual(result["type"], "pane_capture")
        self.assertEqual(result["output"], buffer)
        self.assertEqual(result["lines"], ["line one", "line two", "line three"])
        self.assertEqual(result["total_lines"], 3)
        self.assertEqual(result["line_count"], 3)
        self.assertFalse(result["truncated"])

    def test_pane_capture_tails_lines_and_marks_truncated(self):
        state = AppState.bootstrap(cwd="C:/work")
        buffer = "one\ntwo\nthree\nfour"

        result = self._capture(state, _CaptureProcesses(buffer), {"lines": 2})

        self.assertEqual(result["lines"], ["three", "four"])
        self.assertEqual(result["total_lines"], 4)
        self.assertEqual(result["line_count"], 2)
        self.assertTrue(result["truncated"])

    def test_pane_capture_zero_lines_returns_empty_tail(self):
        state = AppState.bootstrap(cwd="C:/work")

        result = self._capture(state, _CaptureProcesses("one\ntwo"), {"lines": 0})

        self.assertEqual(result["lines"], [])
        self.assertEqual(result["output"], "")
        self.assertEqual(result["total_lines"], 2)
        self.assertEqual(result["line_count"], 0)
        self.assertTrue(result["truncated"])

    def test_pane_capture_styled_uses_rendered_visible_screen(self):
        state = AppState.bootstrap(cwd="C:/work")

        result = self._capture(state, _CaptureProcesses("plain", styled="\x1b[0m styled"), {"styled": True})

        self.assertTrue(result["styled"])
        self.assertEqual(result["output"], "\x1b[0m styled")

    def test_pane_capture_falls_back_to_stored_output_without_session(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane
        pane.append_output("stored one")
        pane.append_output("stored two")

        result = self._capture(state, _NoSessionProcesses())

        self.assertEqual(result["lines"], ["stored one", "stored two"])
        self.assertEqual(result["total_lines"], 2)

    def test_pane_capture_uses_stored_output_when_no_manager(self):
        state = AppState.bootstrap(cwd="C:/work")
        state.focused_workspace.focused_tab.focused_pane.append_output("offline capture")

        result = self._capture(state, None)

        self.assertIn("offline capture", result["output"])

    def test_session_record_writes_output_and_status_timeline(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane
        pane.title = "codex loop"
        pane.status = AgentStatus.BLOCKED
        pane.custom_status = "needs approval"

        with TemporaryDirectory() as temp:
            output = Path(temp) / "recording.json"
            response = dispatch(
                state,
                {
                    "id": "record",
                    "method": "session.record",
                    "params": {"output": str(output), "lines": 1},
                },
                _CaptureProcesses("line one\ntoken=secret-value"),
            )

            result = response["result"]
            self.assertEqual(result["type"], "session_recording")
            self.assertEqual(result["path"], str(output))
            self.assertEqual(result["pane_count"], 1)
            self.assertTrue(output.exists())

            recording = json.loads(output.read_text(encoding="utf-8"))
            recorded_pane = recording["workspaces"][0]["tabs"][0]["panes"][0]
            self.assertEqual(recorded_pane["title"], "codex loop")
            self.assertEqual(recorded_pane["agent_status"], "blocked")
            self.assertEqual(recorded_pane["custom_status"], "needs approval")
            self.assertEqual(recorded_pane["output"]["lines"], ["token=[redacted]"])
            self.assertEqual(recorded_pane["output"]["line_count"], 1)
            self.assertTrue(recorded_pane["output"]["truncated"])
            self.assertTrue(
                any(
                    event["kind"] == "agent_status"
                    and event["pane_id"] == pane.id
                    and event["status"] == "blocked"
                    for event in recording["timeline"]
                )
            )
            self.assertTrue(
                any(
                    event["kind"] == "pane_output" and event["pane_id"] == pane.id and event["line_count"] == 1
                    for event in recording["timeline"]
                )
            )

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
