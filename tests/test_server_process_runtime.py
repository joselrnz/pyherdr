import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pyherdr.runtime import pty_available
from pyherdr.server import read_server_info, request

# readline (not `for line in sys.stdin`) so input is not read-ahead buffered over a PTY.
ECHO_SCRIPT = (
    "import sys\n"
    "for line in iter(sys.stdin.readline, ''):\n"
    "    print('echo:' + line.strip(), flush=True)\n"
)


@unittest.skipUnless(pty_available(), "no PTY backend available on this platform")
class ServerProcessRuntimeTests(unittest.TestCase):
    def setUp(self):
        repo = Path(__file__).resolve().parents[1]
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        temp = Path(tmp.name)
        echo_path = temp / "echo.py"
        echo_path.write_text(ECHO_SCRIPT, encoding="utf-8")
        self.echo_command = f"{sys.executable} -u {echo_path}"
        env = os.environ.copy()
        env["PYHERDR_STATE_PATH"] = str(temp / "session.json")
        env["PYHERDR_RUNTIME_DIR"] = str(temp / "run")
        patcher = patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "pyherdr", "server", "run"],
            cwd=repo,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        self.addCleanup(self._terminate_server)
        self.info = self._wait_for_info()

    def test_pty_pane_round_trips_text(self):
        self._request("start", "pane.start", {"pane_id": "1-1", "command": self.echo_command})
        self._request("send", "pane.send_text", {"pane_id": "1-1", "text": "server\n"})
        self.assertIn("echo:server", self._wait_for_output("echo:server"))

    def test_pty_pane_accepts_send_key_enter(self):
        self._request("start", "pane.start", {"pane_id": "1-1", "command": self.echo_command})
        self._request("type", "pane.send_text", {"pane_id": "1-1", "text": "hello"})
        self._request("enter", "pane.send_key", {"pane_id": "1-1", "key": "enter"})
        self.assertIn("echo:hello", self._wait_for_output("echo:hello"))

    def test_pane_resize_succeeds(self):
        self._request("start", "pane.start", {"pane_id": "1-1", "command": self.echo_command})
        response = self._request("resize", "pane.resize", {"pane_id": "1-1", "rows": 30, "cols": 100})
        self.assertEqual(response["result"]["type"], "pane_resize")
        self.assertEqual(response["result"]["rows"], 30)

    def _request(self, req_id: str, method: str, params: dict) -> dict:
        return request(self.info, {"id": req_id, "method": method, "params": params})

    def _terminate_server(self):
        info = read_server_info()
        if info is not None:
            try:
                request(info, {"id": "stop", "method": "server.stop", "params": {}}, timeout=1)
            except Exception:
                pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def _wait_for_info(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            info = read_server_info()
            if info is not None:
                return info
            time.sleep(0.05)
        self.fail("server did not publish runtime info")

    def _wait_for_output(self, needle: str) -> str:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            response = self._request("read", "pane.read", {"pane_id": "1-1", "lines": 40})
            output = response["result"]["output"]
            if needle in output:
                return output
            time.sleep(0.05)
        self.fail(f"timed out waiting for {needle!r}")


if __name__ == "__main__":
    unittest.main()
