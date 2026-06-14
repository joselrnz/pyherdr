import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from pyherdr.presentation.client import ServerClient
from pyherdr.server import (
    PyHerdrServer,
    RequestHandler,
    ServerInfo,
    mutates_state,
    quiet_request,
    read_server_info,
    request,
    server_info_path,
    skips_state_lock,
    write_server_info,
)


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
        for method in (
            "ping",
            "state.get",
            "events.snapshot",
            "layout.template.list",
            "workspace.list",
            "tab.list",
            "pane.list",
        ):
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


class RequestHandlerDisconnectTests(unittest.TestCase):
    def test_write_returns_false_when_client_disconnected(self):
        for error in (BrokenPipeError("closed"), ConnectionResetError("reset"), OSError("gone")):
            with self.subTest(error=type(error).__name__):
                handler = object.__new__(RequestHandler)
                handler.request = Mock()
                handler.request.sendall.side_effect = error

                self.assertFalse(handler._write({"id": "request", "result": {"type": "ok"}}))

    def test_write_returns_true_when_response_sent(self):
        handler = object.__new__(RequestHandler)
        handler.request = Mock()

        self.assertTrue(handler._write({"id": "request", "result": {"type": "ok"}}))
        sent = handler.request.sendall.call_args.args[0]
        self.assertTrue(sent.endswith(b"\n"))


class TokenRotationTests(unittest.TestCase):
    def test_rotate_token_rejects_old_token_and_accepts_new_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "PYHERDR_STATE_PATH": os.path.join(temp_dir, "session.json"),
                "PYHERDR_RUNTIME_DIR": os.path.join(temp_dir, "run"),
            }
            with patch.dict(os.environ, env, clear=False):
                with PyHerdrServer(("127.0.0.1", 0), token="old-token") as server:
                    host, port = server.server_address
                    write_server_info(
                        ServerInfo(str(host), int(port), os.getpid(), server.state_path.as_posix(), "old-token")
                    )
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    try:
                        old = read_server_info()
                        self.assertIsNotNone(old)
                        rotate = request(old, {"id": "rotate", "method": "server.rotate_token", "params": {}})
                        self.assertEqual(rotate["result"]["type"], "server_token_rotated")

                        current = read_server_info()
                        self.assertIsNotNone(current)
                        assert current is not None
                        self.assertNotEqual(current.token, "old-token")

                        rejected = request(old, {"id": "old", "method": "ping", "params": {}})
                        self.assertEqual(rejected["error"]["code"], "unauthorized")

                        accepted = request(current, {"id": "new", "method": "ping", "params": {}})
                        self.assertEqual(accepted["result"]["type"], "pong")
                    finally:
                        server.shutdown()
                        server.server_close()
                        thread.join(timeout=5)
                        if server_info_path().exists():
                            server_info_path().unlink()


if __name__ == "__main__":
    unittest.main()
