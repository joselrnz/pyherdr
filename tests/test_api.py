import unittest

from pyherdr.api import dispatch
from pyherdr.models import AppState


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


if __name__ == "__main__":
    unittest.main()
