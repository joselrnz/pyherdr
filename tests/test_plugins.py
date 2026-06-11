import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pyherdr.plugins import load_plugin_manifest


class PluginManifestTests(unittest.TestCase):
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

    def test_invalid_plugin_manifest_fails_clearly(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "plugin.json"
            path.write_text(json.dumps({"name": "", "kind": "unknown"}), encoding="utf-8")

            with self.assertRaises(ValueError) as caught:
                load_plugin_manifest(path)

        self.assertIn("invalid plugin manifest", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
