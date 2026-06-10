import json
import tempfile
import unittest
from pathlib import Path

from pyherdr.workflow import (
    append_event,
    build_graph,
    event_to_dict,
    graph_to_mermaid,
    new_event,
    read_events,
    redact,
)


class WorkflowTests(unittest.TestCase):
    def test_redacts_nested_sensitive_values(self):
        payload = {
            "token": "abc123",
            "nested": {"api_key": "sk-test", "safe": "visible"},
            "line": "token=abc123 password=hunter2",
        }

        redacted = redact(payload)

        self.assertEqual(redacted["token"], "[redacted]")
        self.assertEqual(redacted["nested"]["api_key"], "[redacted]")
        self.assertEqual(redacted["nested"]["safe"], "visible")
        self.assertIn("token=[redacted]", redacted["line"])
        self.assertIn("password=[redacted]", redacted["line"])

    def test_append_event_keeps_bounded_jsonl_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflow.jsonl"

            for index in range(3):
                append_event(new_event("api.request", message=f"event {index}"), path=path, max_events=2)

            events = read_events(path)
            empty = read_events(path, limit=0)

        self.assertEqual([event.message for event in events], ["event 1", "event 2"])
        self.assertEqual(empty, [])

    def test_graph_contains_worksite_agent_pane_artifact_and_event_links(self):
        event = new_event(
            "validation.ok",
            message="ruff passed",
            worksite="WS-121",
            agent="codex",
            pane_id="1-1",
            artifacts=["proof/report.json"],
            details={"command": "ruff check pyherdr tools tests"},
        )

        graph = build_graph([event])

        self.assertIn("worksite:WS-121", graph["nodes"])
        self.assertIn("agent:codex", graph["nodes"])
        self.assertIn("pane:1-1", graph["nodes"])
        self.assertIn("artifact:proof/report.json", graph["nodes"])
        self.assertTrue(any(edge["from"] == "worksite:WS-121" for edge in graph["edges"]))

    def test_mermaid_export_is_stable_and_readable(self):
        event = new_event("api.request", message="pane split", worksite="WS-121", target="pane.split")
        mermaid = graph_to_mermaid(build_graph([event]))

        self.assertIn("flowchart TD", mermaid)
        self.assertIn("WS-121", mermaid)
        self.assertIn("pane split", mermaid)
        self.assertIn("pane.split", mermaid)

    def test_event_dict_is_json_serializable_and_redacted(self):
        event = new_event("api.request", details={"token": "abc123", "method": "ping"})
        payload = event_to_dict(event)

        self.assertEqual(payload["details"]["token"], "[redacted]")
        self.assertEqual(payload["details"]["method"], "ping")
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
