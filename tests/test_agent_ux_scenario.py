import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.agent_ux_scenario import main, run_agent_ux_scenario


class AgentUxScenarioTests(unittest.TestCase):
    def test_agent_ux_scenario_proves_polished_agent_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_agent_ux_scenario(Path(temp), render_screenshot=False)

            self.assertEqual(report["result"], "ok")
            self.assertEqual(
                report["steps"],
                [
                    "workspace_created",
                    "launcher_presets_visible",
                    "agents_reported",
                    "attention_focused",
                    "toast_delivered",
                    "screenshot_skipped",
                ],
            )
            self.assertEqual(
                {launcher["id"] for launcher in report["launchers"]},
                {"claude", "codex", "aider", "shell"},
            )
            self.assertEqual({agent["agent"] for agent in report["agents"]}, {"claude", "codex", "aider"})
            self.assertEqual(report["sidebar"]["agent_count"], 3)
            self.assertEqual(report["sidebar"]["blocked"], 1)
            self.assertEqual(report["sidebar"]["working"], 1)
            self.assertEqual(report["sidebar"]["done"], 1)
            self.assertEqual(report["sidebar"]["attention_count"], 2)
            self.assertEqual(report["attention_focus"]["agent"], "claude")
            self.assertEqual(report["attention_focus"]["status"], "blocked")
            self.assertEqual(report["toast"]["delivery"], "herdr")
            self.assertFalse(report["screenshot"]["exists"])

    def test_agent_ux_main_prints_json_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = StringIO()
            with redirect_stdout(out):
                exit_code = main(["--work-dir", temp, "--json", "--no-screenshot"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"result": "ok"', out.getvalue())


if __name__ == "__main__":
    unittest.main()
