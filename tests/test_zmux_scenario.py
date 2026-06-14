import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.zmux_scenario import main, run_zmux_scenario


class ZmuxScenarioTests(unittest.TestCase):
    def test_zmux_scenario_proves_multiplexer_fundamentals(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_zmux_scenario(Path(temp))

            self.assertEqual(report["result"], "ok")
            self.assertEqual(
                report["steps"],
                ["workspace_created", "panes_split", "layout_resized", "panes_swapped", "pane_zoomed", "layout_saved"],
            )
            self.assertEqual(report["pane_count"], 4)
            self.assertNotEqual(report["resize"]["before_ratio"], report["resize"]["after_ratio"])
            self.assertEqual(set(report["swap"]), {"first", "last", "before", "after"})
            self.assertEqual(report["zoom"]["visible_panes"], 1)
            self.assertEqual(report["saved_layout"]["id"], "zmux-grid")
            self.assertTrue(Path(report["saved_layout"]["path"]).exists())
            self.assertEqual(report["applied_layout"]["pane_count"], 4)

    def test_zmux_scenario_main_prints_json_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = StringIO()
            with redirect_stdout(out):
                exit_code = main(["--work-dir", temp, "--json"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"result": "ok"', out.getvalue())


if __name__ == "__main__":
    unittest.main()
