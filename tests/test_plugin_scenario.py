import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.plugin_scenario import main, run_plugin_scenario


class PluginScenarioTests(unittest.TestCase):
    def test_plugin_scenario_proves_extension_story(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_plugin_scenario(Path(temp))
            state_file_exists = Path(report["state_file"]).exists()
            export_file_exists = Path(report["export"]["output"]).exists()

        self.assertEqual(report["result"], "ok")
        self.assertEqual(
            report["steps"],
            [
                "manifests_validated",
                "launchers_loaded",
                "detector_loaded",
                "theme_loaded",
                "workspace_created",
                "plugin_status_detected",
                "recording_exported",
                "state_saved",
            ],
        )
        self.assertEqual(
            {launcher["id"] for launcher in report["launchers"].values()},
            {"walter-ssh", "ollama-local", "codex-cli", "claude-code"},
        )
        self.assertEqual(report["launchers"]["walter-ssh"]["command"], "ssh joselrnz@192.168.50.150")
        self.assertEqual(report["launchers"]["ollama-local"]["command"], "ollama run llama3.1")
        self.assertEqual(report["launchers"]["codex-cli"]["command"], "codex")
        self.assertEqual(report["launchers"]["claude-code"]["command"], "claudecode")
        self.assertEqual(report["detector"]["state"], "blocked")
        self.assertTrue(report["detector"]["visible_blocker"])
        self.assertEqual(report["pane"]["agent"], "pyherdr-plugin-agent")
        self.assertEqual(report["pane"]["agent_status"], "blocked")
        self.assertEqual(report["theme"]["name"], "pyherdr-ops")
        self.assertEqual(report["export"]["exporter"], "markdown")
        self.assertEqual(report["export"]["pane_count"], 1)
        self.assertTrue(state_file_exists)
        self.assertTrue(export_file_exists)

    def test_plugin_scenario_main_prints_json_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = StringIO()
            with redirect_stdout(out):
                exit_code = main(["--work-dir", temp, "--json"])

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["result"], "ok")
        self.assertEqual(payload["detector"]["state"], "blocked")


if __name__ == "__main__":
    unittest.main()
