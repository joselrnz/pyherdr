import unittest

from pyherdr.server import mutates_state, quiet_request, skips_state_lock


class MutatesStateTests(unittest.TestCase):
    def test_persisting_methods_are_marked_mutating(self):
        for method in ("workspace.create", "tab.create", "pane.create", "pane.start", "pane.stop", "pane.run"):
            self.assertTrue(mutates_state(method), method)

    def test_live_terminal_io_does_not_persist(self):
        # These drive the PTY but do not change persisted session state, so they
        # must not trigger a session.json write (important for per-key forwarding).
        for method in ("pane.send_text", "pane.send_key", "pane.resize", "pane.read", "pane.capture", "session.record"):
            self.assertFalse(mutates_state(method), method)

    def test_read_only_queries_do_not_persist(self):
        for method in ("ping", "state.get", "events.snapshot", "workspace.list", "tab.list", "pane.list"):
            self.assertFalse(mutates_state(method), method)

    def test_high_frequency_terminal_requests_are_quiet(self):
        # These can fire for every keypress or output refresh. Logging them
        # rewrites workflow.jsonl and makes interactive terminal input lag.
        for method in (
            "ping",
            "state.get",
            "stats.get",
            "pane.read",
            "pane.wait_output",
            "pane.send_text",
            "pane.send_key",
            "pane.resize",
            "pane.scroll",
        ):
            self.assertTrue(quiet_request(method), method)

    def test_live_terminal_io_skips_state_lock(self):
        # These operate on PTY/process state rather than the persisted workspace
        # model, so they should not queue behind state saves or slow readers.
        for method in (
            "stats.get",
            "pane.read",
            "pane.wait_output",
            "pane.send_text",
            "pane.send_key",
            "pane.resize",
            "pane.scroll",
        ):
            self.assertTrue(skips_state_lock(method), method)


if __name__ == "__main__":
    unittest.main()
