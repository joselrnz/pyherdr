import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.headless_scenario import DEFAULT_MARKER, main, run_headless_scenario


class HeadlessScenarioTests(unittest.TestCase):
    def test_headless_scenario_proves_no_tui_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_headless_scenario(Path(temp))
            state_file_exists = Path(report["state_file"]).exists()

        self.assertEqual(report["result"], "ok")
        self.assertEqual(
            report["steps"],
            [
                "workspace_created",
                "command_ran",
                "output_waited",
                "status_waited",
                "output_captured",
                "state_saved",
            ],
        )
        self.assertEqual(report["workspace"]["label"], "headless-ci")
        self.assertEqual(report["workspace"]["tab"]["label"], "ci")
        self.assertEqual(report["pane"]["title"], "runner")
        self.assertEqual(report["pane"]["agent_status"], "done")
        self.assertEqual(report["run"]["exit_code"], 0)
        self.assertTrue(report["wait"]["output_matched"])
        self.assertEqual(report["wait"]["status"], "done")
        self.assertTrue(report["capture"]["output_contains_marker"])
        self.assertGreaterEqual(report["capture"]["line_count"], 3)
        self.assertEqual(report["restored"]["agent_status"], "done")
        self.assertTrue(state_file_exists)

    def test_headless_scenario_main_prints_json_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = StringIO()
            with redirect_stdout(out):
                exit_code = main(["--work-dir", temp, "--json"])

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["result"], "ok")
        self.assertTrue(payload["capture"]["output_contains_marker"])

    def test_headless_scenario_accepts_custom_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_headless_scenario(Path(temp), marker="CUSTOM_HEADLESS_MARKER")

        self.assertNotIn(DEFAULT_MARKER, report["command"])
        self.assertTrue(report["wait"]["output_matched"])


if __name__ == "__main__":
    unittest.main()
