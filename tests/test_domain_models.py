import unittest

from pydantic import ValidationError

from pyherdr.domain.models import AppState, Pane
from pyherdr.domain.status import AgentStatus


class DomainModelTests(unittest.TestCase):
    def test_pane_normalizes_blank_title(self):
        pane = Pane(id="1-1", title="  ", cwd="C:/work")

        self.assertEqual(pane.title, "pane")

    def test_pane_rejects_invalid_status(self):
        with self.assertRaises(ValidationError):
            Pane(id="1-1", title="pane", cwd="C:/work", status="wat")

    def test_append_output_caps_buffer(self):
        pane = Pane(id="1-1", title="pane", cwd="C:/work")

        pane.append_output("a\nb\nc", max_lines=2)

        self.assertEqual(pane.output, ["b", "c"])

    def test_app_state_bootstrap_uses_pydantic_models(self):
        state = AppState.bootstrap(cwd="C:/work")

        self.assertEqual(state.focused_workspace.label, "main")
        self.assertEqual(state.focused_workspace.focused_tab.focused_pane.status, AgentStatus.IDLE)

    def test_pane_ids_are_unique_across_tabs(self):
        state = AppState.bootstrap(cwd="C:/work")
        workspace = state.focused_workspace
        state.create_tab(workspace.id, "second")
        state.create_tab(workspace.id, "third")

        pane_ids = [pane.id for tab in workspace.tabs for pane in tab.panes]

        self.assertEqual(len(pane_ids), len(set(pane_ids)))

    def test_loading_state_advances_pane_counter_past_existing_ids(self):
        payload = {
            "next_pane_number": 1,
            "focused_workspace_id": "ws",
            "workspaces": [
                {
                    "id": "ws",
                    "label": "main",
                    "cwd": "C:/x",
                    "focused_tab_id": "t",
                    "tabs": [
                        {
                            "id": "t",
                            "label": "shell",
                            "focused_pane_id": "1-5",
                            "panes": [{"id": "1-5", "title": "p", "cwd": "C:/x"}],
                        }
                    ],
                }
            ],
        }

        state = AppState.model_validate(payload)
        self.assertEqual(state.next_pane_number, 6)

        new_pane = state.create_pane("ws", "t")
        self.assertNotEqual(new_pane.id, "1-5")

    def test_each_created_pane_is_addressable(self):
        state = AppState.bootstrap(cwd="C:/work")
        workspace = state.focused_workspace
        second_tab = state.create_tab(workspace.id, "second")
        target = second_tab.panes[0]

        self.assertIs(state.require_pane(target.id), target)


if __name__ == "__main__":
    unittest.main()
