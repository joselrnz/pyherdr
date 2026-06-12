import unittest

from pyherdr.config.settings import Config, LauncherPresetConfig, LaunchersConfig
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


if __name__ == "__main__":
    unittest.main()
