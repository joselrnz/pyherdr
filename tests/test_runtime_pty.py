import os
import shutil
import sys
import tempfile
import time
import unittest

from pyherdr.runtime import TerminalManager, pty_available

# Reads stdin line-by-line (readline avoids the read-ahead buffering that
# `for line in sys.stdin` does, which stalls over a PTY) and echoes each line.
ECHO_SCRIPT = (
    "import sys\n"
    "for line in iter(sys.stdin.readline, ''):\n"
    "    sys.stdout.write('echo:' + line.strip() + '\\n')\n"
    "    sys.stdout.flush()\n"
)


@unittest.skipUnless(pty_available(), "no PTY backend available on this platform")
class PtyRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.manager = TerminalManager()
        self.addCleanup(self.manager.stop_all)
        self._dir = tempfile.mkdtemp(prefix="pyherdr-pty-")
        self.addCleanup(shutil.rmtree, self._dir, ignore_errors=True)
        self._echo_path = os.path.join(self._dir, "echo.py")
        with open(self._echo_path, "w", encoding="utf-8") as handle:
            handle.write(ECHO_SCRIPT)

    def _echo_cmd(self) -> list[str]:
        return [sys.executable, "-u", self._echo_path]

    def test_captures_process_output(self):
        self.assertTrue(self.manager.start("p1", [sys.executable, "-c", "print('hello-pty-123')"]))
        output = self._wait_for("p1", "hello-pty-123")
        self.assertIn("hello-pty-123", output)

    def test_start_is_idempotent_while_running(self):
        self.assertTrue(self.manager.start("p1", self._echo_cmd()))
        self.assertFalse(self.manager.start("p1", self._echo_cmd()))

    def test_interactive_input_round_trips(self):
        self.manager.start("p1", self._echo_cmd())
        self.manager.send_text("p1", "ping\n")
        output = self._wait_for("p1", "echo:ping")
        self.assertIn("echo:ping", output)

    def test_read_missing_session_raises(self):
        with self.assertRaises(KeyError):
            self.manager.read("nope")

    def _wait_for(self, pane_id: str, needle: str) -> str:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            output = self.manager.read(pane_id)
            if needle in output:
                return output
            time.sleep(0.05)
        self.fail(f"timed out waiting for {needle!r}; last output was:\n{self.manager.read(pane_id)!r}")


if __name__ == "__main__":
    unittest.main()
