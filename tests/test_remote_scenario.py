import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.remote_scenario import DEFAULT_HOST, main, run_remote_scenario


class RemoteScenarioTests(unittest.TestCase):
    def test_remote_scenario_proves_remote_workspace_story(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_remote_scenario(Path(temp))

            self.assertEqual(report["result"], "ok")
            self.assertEqual(
                report["steps"],
                [
                    "workspace_created",
                    "config_validated",
                    "profile_planned",
                    "remote_probed",
                    "remote_pane_created",
                    "remote_metadata_restored",
                ],
            )
            self.assertEqual(report["connection"]["name"], "walter")
            self.assertEqual(report["connection"]["host"], DEFAULT_HOST)
            self.assertTrue(report["validation"]["ok"])
            self.assertEqual(report["profile"]["workspace"], "walter")
            self.assertEqual(report["profile"]["remote_connections"][0]["host"], DEFAULT_HOST)
            self.assertTrue(report["probe"]["ok"])
            self.assertEqual(report["probe"]["host"], DEFAULT_HOST)
            self.assertIn("BatchMode=yes", " ".join(report["probe"]["command"]))
            self.assertEqual(report["pane"]["location"], "remote")
            self.assertEqual(report["pane"]["remote_host"], DEFAULT_HOST)
            self.assertEqual(report["pane"]["display_cwd"], f"{DEFAULT_HOST}:/srv/pyherdr")
            self.assertEqual(report["restored"]["remote_host"], DEFAULT_HOST)
            self.assertTrue(Path(report["state_file"]).exists())

    def test_remote_scenario_accepts_walter_hostname_override(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_remote_scenario(Path(temp), connection_name="walter", host="150")

            self.assertEqual(report["connection"]["name"], "walter")
            self.assertEqual(report["connection"]["host"], "150")
            self.assertEqual(report["pane"]["remote_host"], "150")

    def test_remote_scenario_main_prints_json_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = StringIO()
            with redirect_stdout(out):
                exit_code = main(["--work-dir", temp, "--json"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"result": "ok"', out.getvalue())


if __name__ == "__main__":
    unittest.main()
