import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pyherdr.api import dispatch
from pyherdr.config import Config, PluginsConfig
from pyherdr.models import AgentStatus, AppState


class _SessionManager:
    """Stands in for a TerminalManager that has a live session for the pane."""

    def __init__(self, output: str) -> None:
        self._output = output

    def read(self, pane_id: str, lines=None) -> str:
        return self._output

    def running(self, pane_id: str) -> bool:
        return True

    def wait_for_output(self, versions: dict[str, int], timeout: float = 1.0) -> dict:
        return {"changed": {"1-1": 2}, "versions": {"1-1": 2}, "timed_out": False}


class _NoSessionManager:
    """Stands in for a TerminalManager with no session for the pane."""

    def read(self, pane_id: str, lines=None) -> str:
        raise KeyError(pane_id)


class _FailingManager:
    """A manager whose terminal I/O fails (e.g. the pane process exited)."""

    def read(self, pane_id: str, lines=None) -> str:
        return ""

    def running(self, pane_id: str) -> bool:
        return True

    def send_text(self, pane_id: str, text: str) -> None:
        raise OSError("pane process is gone")


class PaneReadTests(unittest.TestCase):
    def _read(self, state, processes):
        pane = state.focused_workspace.focused_tab.focused_pane
        return dispatch(state, {"id": "r", "method": "pane.read", "params": {"pane_id": pane.id}}, processes)

    def test_prefers_live_terminal_session_over_stored_output(self):
        state = AppState.bootstrap(cwd="C:/work")
        state.focused_workspace.focused_tab.focused_pane.append_output("stale run output")

        response = self._read(state, _SessionManager("LIVE SCREEN"))

        self.assertEqual(response["result"]["output"], "LIVE SCREEN")
        self.assertNotIn("stale", response["result"]["output"])

    def test_falls_back_to_stored_output_without_session(self):
        state = AppState.bootstrap(cwd="C:/work")
        state.focused_workspace.focused_tab.focused_pane.append_output("only stored")

        response = self._read(state, _NoSessionManager())

        self.assertIn("only stored", response["result"]["output"])

    def test_uses_stored_output_when_no_manager(self):
        state = AppState.bootstrap(cwd="C:/work")
        state.focused_workspace.focused_tab.focused_pane.append_output("no manager output")

        response = self._read(state, None)

        self.assertIn("no manager output", response["result"]["output"])

    def test_pane_read_updates_status_from_agent_screen(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane
        pane.agent = "claude"
        screen = "✻ Pondering… (esc to interrupt)\n────────────\n❯ \n────────────\n"

        dispatch(state, {"id": "r", "method": "pane.read", "params": {"pane_id": pane.id}}, _SessionManager(screen))

        self.assertEqual(pane.status, AgentStatus.WORKING)

    def test_pane_read_updates_status_from_detector_plugin(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "detector.py").write_text(
                "def detect(content):\n"
                "    return {'state': 'blocked', 'visible_blocker': True} if 'APPROVE' in content else 'idle'\n",
                encoding="utf-8",
            )
            manifest = root / "plugin.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "sample-agent",
                        "version": "1.0.0",
                        "kind": "detector",
                        "entrypoint": "detector.py",
                        "aliases": ["sample"],
                    }
                ),
                encoding="utf-8",
            )
            state = AppState.bootstrap(cwd="C:/work")
            pane = state.focused_workspace.focused_tab.focused_pane
            pane.agent = "sample"
            config = Config(plugins=PluginsConfig(detectors=[str(manifest)]))

            with patch("pyherdr.api.load_config", return_value=config):
                dispatch(
                    state,
                    {"id": "r", "method": "pane.read", "params": {"pane_id": pane.id}},
                    _SessionManager("APPROVE deploy"),
                )

        self.assertEqual(pane.status, AgentStatus.BLOCKED)

    def test_pane_wait_output_returns_changed_versions(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane

        response = dispatch(
            state,
            {"id": "w", "method": "pane.wait_output", "params": {"versions": {pane.id: 1}, "timeout": 0.01}},
            _SessionManager("LIVE SCREEN"),
        )

        self.assertEqual(response["result"]["type"], "pane_output_wait")
        self.assertEqual(response["result"]["changed"], {pane.id: 2})
        self.assertFalse(response["result"]["timed_out"])

    def test_pty_io_failure_becomes_structured_error(self):
        state = AppState.bootstrap(cwd="C:/work")
        pane = state.focused_workspace.focused_tab.focused_pane

        response = dispatch(
            state,
            {"id": "s", "method": "pane.send_text", "params": {"pane_id": pane.id, "text": "x"}},
            _FailingManager(),
        )

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], "runtime_error")


if __name__ == "__main__":
    unittest.main()
