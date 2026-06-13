import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pyherdr.models import AgentStatus
from pyherdr.plugins import load_detector_plugin, load_plugin_manifest


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

    def test_invalid_plugin_manifest_fails_clearly(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "plugin.json"
            path.write_text(json.dumps({"name": "", "kind": "unknown"}), encoding="utf-8")

            with self.assertRaises(ValueError) as caught:
                load_plugin_manifest(path)

        self.assertIn("invalid plugin manifest", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
