import unittest

from pyherdr.server import mutates_state


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
        for method in ("ping", "state.get", "workspace.list", "tab.list", "pane.list"):
            self.assertFalse(mutates_state(method), method)


if __name__ == "__main__":
    unittest.main()
