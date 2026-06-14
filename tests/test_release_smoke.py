import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.release_smoke import VERSION_CHECK, build_smoke_commands, main, pyherdr_script, venv_python


class ReleaseSmokeTests(unittest.TestCase):
    def test_build_smoke_commands_create_install_and_launch_installed_cli(self):
        repo = Path("C:/repo")
        venv = Path("C:/tmp/smoke")

        commands = build_smoke_commands(repo, venv, "python")
        venv_py = venv_python(venv)
        pyherdr = pyherdr_script(venv)

        self.assertEqual(commands[0], ["python", "-m", "venv", str(venv)])
        self.assertEqual(commands[1], [str(venv_py), "-m", "pip", "install", str(repo)])
        self.assertEqual(commands[2], [str(venv_py), "-c", VERSION_CHECK])
        self.assertEqual(commands[3], [str(venv_py), "-m", "pyherdr", "--version"])
        self.assertEqual(commands[4], [str(pyherdr), "--version"])
        self.assertEqual(commands[5], [str(pyherdr), "headless", "status"])

    def test_dry_run_prints_commands_without_running_subprocesses(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("subprocess.run") as run:
                exit_code = main(["--repo", ".", "--work-dir", temp, "--python", "python", "--dry-run"])

        self.assertEqual(exit_code, 0)
        run.assert_not_called()
