import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pyherdr.config.settings import Config, LauncherPresetConfig, LaunchersConfig, PluginsConfig
from pyherdr.launchers import launcher_presets


class LauncherTests(unittest.TestCase):
    def test_launcher_presets_include_builtins_and_custom_config(self):
        config = Config(
            launchers=LaunchersConfig(
                presets=[
                    LauncherPresetConfig(
                        id="logs",
                        label="Tail logs",
                        command="tail -f app.log",
                        description="Watch app logs",
                    )
                ]
            )
        )

        presets = launcher_presets(config, default_shell="bash")

        self.assertEqual(presets[0].id, "claude")
        self.assertEqual(presets[1].command, "codex")
        self.assertEqual(presets[2].command, "aider")
        self.assertEqual(presets[-1].id, "logs")
        self.assertEqual(presets[-1].label, "Tail logs")
        self.assertEqual(presets[-1].command, "tail -f app.log")

    def test_launcher_presets_include_launcher_plugins(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "launcher.py").write_text(
                "def launchers():\n"
                "    return [{'id': 'ops-shell', 'label': 'Ops Shell', 'command': 'ssh ops@example.com'}]\n",
                encoding="utf-8",
            )
            manifest = root / "plugin.json"
            manifest.write_text(
                '{"name":"ops-launchers","version":"1.0.0","kind":"launcher","entrypoint":"launcher.py"}',
                encoding="utf-8",
            )
            config = Config(plugins=PluginsConfig(launchers=[str(manifest)]))

            presets = launcher_presets(config, default_shell="bash")

        self.assertEqual(presets[-1].id, "ops-shell")
        self.assertEqual(presets[-1].label, "Ops Shell")
        self.assertEqual(presets[-1].command, "ssh ops@example.com")


if __name__ == "__main__":
    unittest.main()
