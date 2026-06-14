import json
import tempfile
import unittest
from pathlib import Path

from pyherdr.models import AgentStatus, AppState
from pyherdr.store import load_state, save_state


class StoreTests(unittest.TestCase):
    def test_round_trip_preserves_status_and_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            state = AppState.bootstrap(cwd="C:/work")
            pane = state.focused_workspace.focused_tab.focused_pane
            pane.status = AgentStatus.DONE
            pane.append_output("tests passed")

            save_state(state, path)
            restored = load_state(path)
            restored_pane = restored.focused_workspace.focused_tab.focused_pane

            self.assertEqual(restored_pane.status, AgentStatus.DONE)
            self.assertEqual(restored_pane.output, ["tests passed"])

    def test_save_state_writes_versioned_state_envelope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            state = AppState.bootstrap(cwd="C:/work")

            save_state(state, path)
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["schema_version"], 1)
            self.assertIn("state", payload)
            self.assertIn("workspaces", payload["state"])

    def test_load_state_migrates_legacy_raw_state_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            path.write_text(
                json.dumps(
                    {
                        "current_workspace_id": "ws_old",
                        "workspaces": [
                            {
                                "id": "ws_old",
                                "name": "legacy",
                                "path": "C:/legacy",
                                "current_tab_id": "tab_old",
                                "tabs": [
                                    {
                                        "id": "tab_old",
                                        "name": "main",
                                        "current_pane_id": "pane_old",
                                        "panes": [
                                            {
                                                "id": "pane_old",
                                                "label": "shell",
                                                "output": ["ready"],
                                                "status": "done",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            restored = load_state(path)
            workspace = restored.focused_workspace
            tab = workspace.focused_tab
            pane = tab.focused_pane

            self.assertEqual(workspace.label, "legacy")
            self.assertEqual(workspace.cwd, "C:/legacy")
            self.assertEqual(tab.label, "main")
            self.assertEqual(pane.title, "shell")
            self.assertEqual(pane.cwd, "C:/legacy")
            self.assertEqual(pane.status, AgentStatus.DONE)
            self.assertEqual(pane.output, ["ready"])

    def test_load_state_rejects_future_schema_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            path.write_text(json.dumps({"schema_version": 999, "state": {}}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported PyHerdr state schema version"):
                load_state(path)


if __name__ == "__main__":
    unittest.main()
