import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.recovery_scenario import CRASH_MARKER, RECOVERY_MARKER, main, run_recovery_scenario


class RecoveryScenarioTests(unittest.TestCase):
    def test_recovery_scenario_proves_crash_restart_attach_recover(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_recovery_scenario(Path(temp))
            state_file_exists = Path(report["state_file"]).exists()

        self.assertEqual(report["result"], "ok")
        self.assertEqual(
            report["steps"],
            [
                "workspace_created",
                "pane_crash_captured",
                "state_saved",
                "server_restarted",
                "attach_recovered",
                "pane_recovered",
                "state_resaved",
            ],
        )
        self.assertEqual(report["crash"]["exit_code"], 7)
        self.assertEqual(report["crash"]["status"], "blocked")
        self.assertTrue(report["crash"]["output_contains_marker"])
        self.assertEqual(report["reattached"]["status"], "blocked")
        self.assertTrue(report["reattached"]["capture_contains_crash"])
        self.assertEqual(report["recovery"]["exit_code"], 0)
        self.assertEqual(report["recovery"]["status"], "done")
        self.assertTrue(report["recovery"]["output_contains_marker"])
        self.assertEqual(report["restored_after_recovery"]["status"], "done")
        self.assertTrue(report["restored_after_recovery"]["capture_contains_recovery"])
        self.assertTrue(state_file_exists)

    def test_recovery_scenario_main_prints_json_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = StringIO()
            with redirect_stdout(out):
                exit_code = main(["--work-dir", temp, "--json"])

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["result"], "ok")
        self.assertTrue(payload["crash"]["output_contains_marker"])
        self.assertIn(CRASH_MARKER, payload["crash"]["marker"])
        self.assertIn(RECOVERY_MARKER, payload["recovery"]["marker"])


if __name__ == "__main__":
    unittest.main()
