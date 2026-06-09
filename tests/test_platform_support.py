import os
import unittest
from pathlib import Path
from unittest.mock import patch

from pyherdr.platform_support import default_runtime_root, hidden_process_creation_flags


class PlatformSupportTests(unittest.TestCase):
    def test_env_override_wins_for_runtime_root(self):
        with patch.dict(os.environ, {"PYHERDR_RUNTIME_DIR": "C:/tmp/pyherdr-run"}, clear=False):
            self.assertEqual(default_runtime_root(), Path("C:/tmp/pyherdr-run").expanduser())

    def test_windows_runtime_root_uses_local_app_data(self):
        env = {"LOCALAPPDATA": "C:/Users/test/AppData/Local"}
        self.assertEqual(
            default_runtime_root(platform_name="win32", environ=env),
            Path("C:/Users/test/AppData/Local") / "PyHerdr",
        )

    def test_macos_runtime_root_uses_application_support(self):
        root = default_runtime_root(platform_name="darwin", home=Path("/Users/test"))
        self.assertEqual(root, Path("/Users/test/Library/Application Support/PyHerdr"))

    def test_linux_runtime_root_uses_xdg_state_home(self):
        root = default_runtime_root(
            platform_name="linux",
            environ={"XDG_STATE_HOME": "/home/test/.state"},
            home=Path("/home/test"),
        )
        self.assertEqual(root, Path("/home/test/.state/pyherdr"))

    def test_hidden_process_flags_are_zero_off_windows(self):
        self.assertEqual(hidden_process_creation_flags(os_name="posix"), 0)

    def test_hidden_process_flags_are_nonzero_on_windows(self):
        self.assertNotEqual(hidden_process_creation_flags(os_name="nt"), 0)


if __name__ == "__main__":
    unittest.main()
