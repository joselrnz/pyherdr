import unittest

from pyherdr.live_updates import build_state_events
from pyherdr.models import AgentStatus, AppState


class LiveUpdatesTests(unittest.TestCase):
    def test_state_events_include_workspace_and_status_changes(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane
        pane.status = AgentStatus.WORKING

        events = build_state_events(state)

        self.assertTrue(any(event["kind"] == "workspace" and event["action"] == "snapshot" for event in events))
        self.assertTrue(
            any(
                event["kind"] == "agent_status"
                and event["pane_id"] == pane.id
                and event["status"] == "working"
                for event in events
            )
        )

    def test_state_events_can_diff_against_previous_snapshot(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane
        previous = build_state_events(state)

        pane.status = AgentStatus.BLOCKED
        events = build_state_events(state, previous_events=previous)

        self.assertTrue(any(event["kind"] == "workspace" and event["status"] == "blocked" for event in events))
        self.assertTrue(any(event["kind"] == "agent_status" and event["status"] == "blocked" for event in events))


if __name__ == "__main__":
    unittest.main()
