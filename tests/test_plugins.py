import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pyherdr.models import AgentStatus
from pyherdr.plugins import (
    load_detector_plugin,
    load_exporter_plugin,
    load_launcher_plugin,
    load_plugin_manifest,
    load_theme_plugin,
)


class PluginManifestTests(unittest.TestCase):
    def _write_detector_plugin(self, temp: str) -> Path:
        root = Path(temp)
        (root / "detector.py").write_text(
            "def detect(content):\n"
            "    if 'APPROVE' in content:\n"
            "        return {'state': 'blocked', 'visible_blocker': True}\n"
            "    if 'RUNNING' in content:\n"
            "        return 'working'\n"
            "    return 'idle'\n",
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
                    "description": "Adds a detector",
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_valid_plugin_manifest_loads(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "plugin.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "status-detector",
                        "version": "1.0.0",
                        "kind": "detector",
                        "entrypoint": "plugin.py",
                        "description": "Adds a detector",
                    }
                ),
                encoding="utf-8",
            )

            manifest = load_plugin_manifest(path)

        self.assertEqual(manifest.name, "status-detector")
        self.assertEqual(manifest.kind, "detector")
        self.assertEqual(manifest.execution, "in_process")

    def test_plugin_manifest_accepts_explicit_in_process_execution(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "plugin.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "status-detector",
                        "version": "1.0.0",
                        "kind": "detector",
                        "entrypoint": "plugin.py",
                        "execution": "in_process",
                    }
                ),
                encoding="utf-8",
            )

            manifest = load_plugin_manifest(path)

        self.assertEqual(manifest.execution, "in_process")

    def test_plugin_manifest_rejects_unsupported_execution_boundary(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "plugin.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "status-detector",
                        "version": "1.0.0",
                        "kind": "detector",
                        "entrypoint": "plugin.py",
                        "execution": "subprocess",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as caught:
                load_plugin_manifest(path)

        self.assertIn("invalid plugin manifest", str(caught.exception))

    def test_detector_plugin_loads_and_runs(self):
        with TemporaryDirectory() as temp:
            path = self._write_detector_plugin(temp)

            plugin = load_detector_plugin(path)
            blocked = plugin.detect("APPROVE this command")
            working = plugin.detect("RUNNING tools")

        self.assertIn("sample", plugin.labels)
        self.assertEqual(blocked.state, AgentStatus.BLOCKED)
        self.assertTrue(blocked.visible_blocker)
        self.assertEqual(working.state, AgentStatus.WORKING)

    def test_launcher_plugin_loads_launchers(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "launcher.py").write_text(
                "def launchers():\n"
                "    return [\n"
                "        {\n"
                "            'id': 'ops-shell',\n"
                "            'label': 'Ops Shell',\n"
                "            'command': 'ssh ops@example.com',\n"
                "            'description': 'Open ops host',\n"
                "            'agent': 'shell',\n"
                "        }\n"
                "    ]\n",
                encoding="utf-8",
            )
            manifest = root / "plugin.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "ops-launchers",
                        "version": "1.0.0",
                        "kind": "launcher",
                        "entrypoint": "launcher.py",
                    }
                ),
                encoding="utf-8",
            )

            plugin = load_launcher_plugin(manifest)
            [launcher] = plugin.launchers()

        self.assertEqual(launcher["id"], "ops-shell")
        self.assertEqual(launcher["label"], "Ops Shell")
        self.assertEqual(launcher["command"], "ssh ops@example.com")

    def test_theme_plugin_loads_themes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "theme.py").write_text(
                "def themes():\n"
                "    return [{\n"
                "        'name': 'ops-dark',\n"
                "        'description': 'Ops dark palette',\n"
                "        'palette': {\n"
                "            'accent': '#00ffff', 'panel_bg': '#101820', 'surface0': '#17232d',\n"
                "            'surface1': '#20313d', 'surface_dim': '#0b1117', 'overlay0': '#5d7788',\n"
                "            'overlay1': '#7894a7', 'text': '#e8f7ff', 'subtext0': '#a8c4d4',\n"
                "            'mauve': '#c4a7ff', 'green': '#70e08d', 'yellow': '#ffd166',\n"
                "            'red': '#ff6b8a', 'blue': '#5abfff', 'teal': '#2dd4bf', 'peach': '#ffb86b',\n"
                "        },\n"
                "    }]\n",
                encoding="utf-8",
            )
            manifest = root / "plugin.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "ops-themes",
                        "version": "1.0.0",
                        "kind": "theme",
                        "entrypoint": "theme.py",
                    }
                ),
                encoding="utf-8",
            )

            plugin = load_theme_plugin(manifest)
            [theme] = plugin.themes()

        self.assertEqual(theme["name"], "ops-dark")
        self.assertEqual(theme["palette"]["accent"], "#00ffff")

    def test_exporter_plugin_writes_recording_export(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "exporter.py").write_text(
                "def exporters():\n"
                "    return [{'id': 'text', 'label': 'Plain text', 'extension': '.txt'}]\n"
                "\n"
                "def export(recording, output, exporter_id=''):\n"
                "    panes = []\n"
                "    for workspace in recording.get('workspaces', []):\n"
                "        for tab in workspace.get('tabs', []):\n"
                "            panes.extend(tab.get('panes', []))\n"
                "    output.write_text('\\n'.join(pane.get('title', '') for pane in panes), encoding='utf-8')\n"
                "    return {'exporter': exporter_id or 'text', 'pane_count': len(panes)}\n",
                encoding="utf-8",
            )
            manifest = root / "plugin.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "text-exporter",
                        "version": "1.0.0",
                        "kind": "exporter",
                        "entrypoint": "exporter.py",
                    }
                ),
                encoding="utf-8",
            )
            output = root / "recording.txt"
            plugin = load_exporter_plugin(manifest)

            [exporter] = plugin.exporters()
            result = plugin.export(
                {"type": "session_recording", "workspaces": [{"tabs": [{"panes": [{"title": "api"}]}]}]},
                output,
                exporter_id="text",
            )
            exported_text = output.read_text(encoding="utf-8")

        self.assertEqual(exporter["id"], "text")
        self.assertEqual(result["pane_count"], 1)
        self.assertEqual(result["output"], str(output))
        self.assertEqual(exported_text, "api")

    def test_invalid_plugin_manifest_fails_clearly(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "plugin.json"
            path.write_text(json.dumps({"name": "", "kind": "unknown"}), encoding="utf-8")

            with self.assertRaises(ValueError) as caught:
                load_plugin_manifest(path)

        self.assertIn("invalid plugin manifest", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
