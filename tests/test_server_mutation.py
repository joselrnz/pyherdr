import unittest
from unittest.mock import Mock, patch

from pyherdr.presentation.client import ServerClient
from pyherdr.server import ServerInfo, mutates_state, quiet_request, skips_state_lock


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


class ServerClientRequestTests(unittest.TestCase):
    def test_server_client_reuses_server_info(self):
        info = ServerInfo("127.0.0.1", 12345, 1, "state.json", "token")
        with (
            patch("pyherdr.presentation.client.start_background", return_value=info) as start,
            patch("pyherdr.presentation.client.request", return_value={"result": {"type": "ok"}}) as send,
        ):
            client = ServerClient()
            client.send_text("pane-1", "a")
            client.send_text("pane-1", "b")

        self.assertEqual(start.call_count, 1)
        self.assertEqual(send.call_count, 2)

    def test_server_client_rediscovers_after_failed_cached_request(self):
        first = ServerInfo("127.0.0.1", 1111, 1, "state.json", "old")
        second = ServerInfo("127.0.0.1", 2222, 2, "state.json", "new")
        send = Mock(side_effect=[OSError("gone"), {"result": {"type": "ok"}}])
        with (
            patch("pyherdr.presentation.client.start_background", side_effect=[first, second]) as start,
            patch("pyherdr.presentation.client.request", send),
        ):
            client = ServerClient()
            client.send_key("pane-1", "enter")

        self.assertEqual(start.call_count, 2)
        self.assertEqual(send.call_args_list[-1].args[0], second)


if __name__ == "__main__":
    unittest.main()
