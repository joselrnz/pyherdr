import subprocess
import unittest

from pyherdr.api import dispatch
from pyherdr.models import AppState
from pyherdr.remote import probe_remote


class RemoteTests(unittest.TestCase):
    def test_remote_probe_reports_unavailable_host_clearly(self):
        def fake_run(command, **kwargs):
            raise OSError("network unreachable")

        result = probe_remote("missing.example", runner=fake_run)

        self.assertFalse(result["ok"])
        self.assertEqual(result["host"], "missing.example")
        self.assertIn("network unreachable", result["message"])

    def test_remote_probe_reports_command_failure(self):
        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 255, "", "permission denied")

        result = probe_remote("server", runner=fake_run)

        self.assertFalse(result["ok"])
        self.assertIn("permission denied", result["message"])
        self.assertIn("ssh", result["command"][0])

    def test_remote_pane_metadata_is_distinct_from_local(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane
        pane.remote_host = "buildbox"
        pane.remote_cwd = "/srv/app"

        response = dispatch(state, {"id": "pane", "method": "pane.get", "params": {"pane_id": pane.id}})
        record = response["result"]["pane"]

        self.assertEqual(record["location"], "remote")
        self.assertEqual(record["remote_host"], "buildbox")
        self.assertEqual(record["display_cwd"], "buildbox:/srv/app")


if __name__ == "__main__":
    unittest.main()
