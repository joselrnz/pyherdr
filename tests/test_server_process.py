import dataclasses
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pyherdr.server import read_server_info, request, server_info_path


class ServerProcessTests(unittest.TestCase):
    def test_server_process_handles_json_requests(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            env = os.environ.copy()
            env["PYHERDR_STATE_PATH"] = str(temp / "session.json")
            env["PYHERDR_RUNTIME_DIR"] = str(temp / "run")
            process = subprocess.Popen(
                [sys.executable, "-m", "pyherdr", "server", "run"],
                cwd=repo,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            try:
                with patch.dict(os.environ, env, clear=False):
                    info = self._wait_for_info()
                    response = request(info, {"id": "1", "method": "ping", "params": {}})
                    self.assertEqual(response["result"]["type"], "pong")

                    create = request(
                        info,
                        {
                            "id": "2",
                            "method": "workspace.create",
                            "params": {"label": "api", "cwd": str(repo)},
                        },
                    )
                    self.assertEqual(create["result"]["workspace"]["label"], "api")

                    stop = request(info, {"id": "3", "method": "server.stop", "params": {}})
                    self.assertEqual(stop["result"]["type"], "server_stop")
                    process.wait(timeout=5)
                    self.assertFalse(server_info_path().exists())
                    self.assertTrue((temp / "session.json").exists())
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    def test_server_rejects_requests_without_valid_token(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            env = os.environ.copy()
            env["PYHERDR_STATE_PATH"] = str(temp / "session.json")
            env["PYHERDR_RUNTIME_DIR"] = str(temp / "run")
            process = subprocess.Popen(
                [sys.executable, "-m", "pyherdr", "server", "run"],
                cwd=repo,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            try:
                with patch.dict(os.environ, env, clear=False):
                    info = self._wait_for_info()
                    forged = dataclasses.replace(info, token="not-the-real-token")
                    response = request(forged, {"id": "x", "method": "ping", "params": {}})
                    self.assertEqual(response["error"]["code"], "unauthorized")

                    valid = request(info, {"id": "y", "method": "ping", "params": {}})
                    self.assertEqual(valid["result"]["type"], "pong")

                    request(info, {"id": "z", "method": "server.stop", "params": {}})
                    process.wait(timeout=5)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    def _wait_for_info(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            info = read_server_info()
            if info is not None:
                return info
            time.sleep(0.05)
        self.fail("server did not publish runtime info")


if __name__ == "__main__":
    unittest.main()
