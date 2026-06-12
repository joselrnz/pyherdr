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

    def test_sidebar_width_config_loads_from_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[ui]
sidebar_width = 32
sidebar_min_width = 20
sidebar_max_width = 50
""".strip(),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.ui.sidebar_width, 32)
        self.assertEqual(config.ui.sidebar_min_width, 20)
        self.assertEqual(config.ui.sidebar_max_width, 50)

    def test_pane_appearance_config_loads_from_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[ui]
pane_separator = "accent"
pane_border = "visible"
""".strip(),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.ui.pane_separator, "accent")
        self.assertEqual(config.ui.pane_border, "visible")

    def test_startup_profiles_parse_reusable_connection_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            connections = "\n".join(
                f"""
[connections.host{i}]
type = "ssh"
host = "host{i}.example.com"
user = "ops"
key = "~/.ssh/id_ed25519"
""".strip()
                for i in range(1, 101)
            )
            config_path.write_text(
                f"""
{connections}

[profiles.ops]
workspace = "ops"
layout = "main-left"

[[profiles.ops.panes]]
name = "prod-1"
connection = "host1"
command = "uptime"

[[profiles.ops.panes]]
name = "prod-10"
connection = "host10"
command = "journalctl -f"

[workflows.health]
profile = "ops"

[[workflows.health.steps]]
pane = "prod-1"
send = "uptime"
""".strip(),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(len(config.connections), 100)
        self.assertEqual(config.connections["host10"].host, "host10.example.com")
        self.assertEqual(config.profiles["ops"].panes[1].connection, "host10")
        self.assertEqual(config.workflows["health"].steps[0].pane, "prod-1")


if __name__ == "__main__":
    unittest.main()
