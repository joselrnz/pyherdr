import unittest

from pyherdr.api import dispatch
from pyherdr.models import AppState


class ApiLifecycleTests(unittest.TestCase):
    def test_workspace_get_rename_and_close(self):
        state = AppState.bootstrap(cwd="C:/work")
        workspace = state.focused_workspace

        get_response = dispatch(
            state,
            {"id": "get", "method": "workspace.get", "params": {"workspace_id": workspace.id}},
        )
        self.assertEqual(get_response["result"]["workspace"]["workspace_id"], workspace.id)

        rename_response = dispatch(
            state,
            {
                "id": "rename",
                "method": "workspace.rename",
                "params": {"workspace_id": workspace.id, "label": "renamed"},
            },
        )
        self.assertEqual(rename_response["result"]["workspace"]["label"], "renamed")

        close_response = dispatch(
            state,
            {"id": "close", "method": "workspace.close", "params": {"workspace_id": workspace.id}},
        )
        self.assertTrue(close_response["result"]["closed"])
        self.assertEqual(state.workspaces, [])

    def test_tab_get_rename_and_close(self):
        state = AppState.bootstrap(cwd="C:/work")
        workspace = state.focused_workspace
        tab = workspace.focused_tab

        get_response = dispatch(
            state,
            {
                "id": "get",
                "method": "tab.get",
                "params": {"workspace_id": workspace.id, "tab_id": tab.id},
            },
        )
        self.assertEqual(get_response["result"]["tab"]["tab_id"], tab.id)

        rename_response = dispatch(
            state,
            {
                "id": "rename",
                "method": "tab.rename",
                "params": {"workspace_id": workspace.id, "tab_id": tab.id, "label": "logs"},
            },
        )
        self.assertEqual(rename_response["result"]["tab"]["label"], "logs")

        close_response = dispatch(
            state,
            {
                "id": "close",
                "method": "tab.close",
                "params": {"workspace_id": workspace.id, "tab_id": tab.id},
            },
        )
        self.assertTrue(close_response["result"]["closed"])
        self.assertEqual(workspace.tabs, [])

    def test_pane_create_adds_pane_to_focused_tab(self):
        state = AppState.bootstrap(cwd="C:/work")
        tab = state.focused_workspace.focused_tab
        before = len(tab.panes)

        response = dispatch(state, {"id": "c", "method": "pane.create", "params": {"title": "logs"}})

        self.assertEqual(response["result"]["type"], "pane_created")
        self.assertEqual(response["result"]["pane"]["title"], "logs")
        self.assertEqual(len(tab.panes), before + 1)

    def test_pane_close(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane

        response = dispatch(
            state,
            {"id": "close", "method": "pane.close", "params": {"pane_id": pane.id}},
        )

        self.assertTrue(response["result"]["closed"])
        self.assertEqual(state.focused_workspace.focused_tab.panes, [])


if __name__ == "__main__":
    unittest.main()
