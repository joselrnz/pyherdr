import tempfile
import unittest
from pathlib import Path

from pyherdr.config import load_config


class ConfigTests(unittest.TestCase):
    def test_workspace_search_config_loads_from_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[workspace]
search_roots = ["~/github", "C:/work"]
search_ignore = [".git", ".venv", "node_modules"]
search_max_depth = 4
search_max_results = 120
search_include_hidden = true
search_cache_ttl_seconds = 30
""".strip(),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.workspace.search_roots, ["~/github", "C:/work"])
        self.assertEqual(config.workspace.search_ignore, [".git", ".venv", "node_modules"])
        self.assertEqual(config.workspace.search_max_depth, 4)
        self.assertEqual(config.workspace.search_max_results, 120)
        self.assertTrue(config.workspace.search_include_hidden)
        self.assertEqual(config.workspace.search_cache_ttl_seconds, 30)

    def test_launcher_presets_load_from_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[[launchers.presets]]
id = "deploy"
label = "Deploy SSH"
command = "ssh deploy@example.com"
description = "Open production shell"
agent = "shell"
""".strip(),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(len(config.launchers.presets), 1)
        self.assertEqual(config.launchers.presets[0].id, "deploy")
        self.assertEqual(config.launchers.presets[0].command, "ssh deploy@example.com")


if __name__ == "__main__":
    unittest.main()
