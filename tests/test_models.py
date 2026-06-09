import unittest

from pyherdr.models import AgentStatus, AppState


class AppStateTests(unittest.TestCase):
    def test_bootstrap_creates_workspace_tab_and_pane(self):
        state = AppState.bootstrap(cwd="C:/work")

        workspace = state.focused_workspace
        self.assertIsNotNone(workspace)
        self.assertEqual(workspace.label, "main")
        self.assertEqual(workspace.cwd, "C:/work")
        self.assertEqual(len(workspace.tabs), 1)
        self.assertEqual(len(workspace.focused_tab.panes), 1)

    def test_workspace_status_rolls_up_most_urgent_pane(self):
        state = AppState.bootstrap(cwd="C:/work")
        workspace = state.focused_workspace
        tab = workspace.focused_tab
        first = tab.focused_pane
        second = state.create_pane(workspace.id, tab.id, "agent")

        first.status = AgentStatus.WORKING
        second.status = AgentStatus.BLOCKED

        self.assertEqual(tab.status, AgentStatus.BLOCKED)
        self.assertEqual(workspace.status, AgentStatus.BLOCKED)

    def test_create_tab_focuses_new_tab(self):
        state = AppState.bootstrap(cwd="C:/work")
        workspace = state.focused_workspace

        tab = state.create_tab(workspace.id, "tests")

        self.assertEqual(workspace.focused_tab_id, tab.id)
        self.assertEqual(workspace.focused_tab.label, "tests")


if __name__ == "__main__":
    unittest.main()
