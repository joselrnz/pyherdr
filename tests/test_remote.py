import subprocess
import unittest

from pyherdr.api import dispatch
from pyherdr.config import ConnectionConfig
from pyherdr.models import AppState
from pyherdr.remote import probe_connection, probe_remote


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

    def test_remote_probe_uses_connection_ssh_options(self):
        captured: list[list[str]] = []

        def fake_run(command, **kwargs):
            captured.append(command)
            return subprocess.CompletedProcess(command, 0, "pyherdr 1.0", "")

        connection = ConnectionConfig(
            host="prod.example.com",
            user="ops",
            port=2222,
            key="~/.ssh/prod",
            proxy_jump="bastion",
            connect_timeout=8,
            strict_host_key_checking="accept-new",
        )

        result = probe_connection("prod", connection, runner=fake_run)

        self.assertTrue(result["ok"])
        self.assertEqual(result["connection"], "prod")
        self.assertEqual(result["host"], "prod.example.com")
        self.assertEqual(result["target"], "ops@prod.example.com")
        self.assertEqual(
            captured[0],
            [
                "ssh",
                "-p",
                "2222",
                "-i",
                "~/.ssh/prod",
                "-J",
                "bastion",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "ops@prod.example.com",
                "pyherdr",
                "--version",
            ],
        )

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
