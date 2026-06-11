import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pyherdr.replay import load_recording, summarize_recording


class ReplayTests(unittest.TestCase):
    def test_replay_summary_reads_fixture_recording(self):
        recording = {
            "type": "session_recording",
            "version": 1,
            "session": "default",
            "created_at": "2026-06-11T00:00:00Z",
            "workspaces": [
                {
                    "workspace_id": "ws1",
                    "label": "main",
                    "tabs": [
                        {
                            "tab_id": "t1",
                            "label": "agents",
                            "panes": [
                                {
                                    "pane_id": "1-1",
                                    "title": "codex",
                                    "agent_status": "done",
                                    "output": {"lines": ["one", "two"], "line_count": 2, "total_lines": 2},
                                }
                            ],
                        }
                    ],
                }
            ],
            "timeline": [
                {"kind": "agent_status", "pane_id": "1-1", "status": "done"},
                {"kind": "pane_output", "pane_id": "1-1", "line_count": 2},
            ],
        }
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recording.json"
            path.write_text(json.dumps(recording), encoding="utf-8")

            loaded = load_recording(path)
            summary = summarize_recording(loaded)

        self.assertEqual(summary["type"], "recording_summary")
        self.assertEqual(summary["session"], "default")
        self.assertEqual(summary["workspace_count"], 1)
        self.assertEqual(summary["tab_count"], 1)
        self.assertEqual(summary["pane_count"], 1)
        self.assertEqual(summary["timeline_count"], 2)
        self.assertEqual(summary["panes"][0]["pane_id"], "1-1")
        self.assertEqual(summary["panes"][0]["last_lines"], ["one", "two"])

    def test_load_recording_rejects_wrong_type(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text(json.dumps({"type": "other"}), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_recording(path)


if __name__ == "__main__":
    unittest.main()
