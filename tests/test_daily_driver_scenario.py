import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.daily_driver_scenario import main, run_daily_driver_scenario


@unittest.skipUnless(shutil.which("git"), "git is required for the daily-driver scenario")
class DailyDriverScenarioTests(unittest.TestCase):
    def test_daily_driver_scenario_creates_worktree_agents_and_reattaches(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_daily_driver_scenario(Path(temp))

            self.assertEqual(report["result"], "ok")
            self.assertEqual(
                report["steps"],
                ["repo_created", "worktree_created", "agents_launched", "status_visible", "detached", "reattached"],
            )
            self.assertTrue(Path(report["worktree"]).exists())
            self.assertTrue(Path(report["state_file"]).exists())
            self.assertEqual({agent["agent"] for agent in report["agents"]}, {"claude", "codex", "shell"})
            self.assertEqual({agent["status"] for agent in report["agents"]}, {"working", "done", "blocked"})
            self.assertEqual(report["reattached"]["workspace_count"], 2)
            self.assertEqual({agent["running"] for agent in report["reattached"]["agents"]}, {"false"})

    def test_daily_driver_main_prints_json_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = StringIO()
            with redirect_stdout(out):
                exit_code = main(["--work-dir", temp, "--json"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"result": "ok"', out.getvalue())


if __name__ == "__main__":
    unittest.main()
