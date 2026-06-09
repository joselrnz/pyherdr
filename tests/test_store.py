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


if __name__ == "__main__":
    unittest.main()
