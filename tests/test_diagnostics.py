import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from pyherdr.diagnostics import create_debug_bundle


class DiagnosticsTests(unittest.TestCase):
    def test_debug_bundle_redacts_tokens_and_passwords(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "session.json"
            workflow = root / "workflow.jsonl"
            server = root / "server.json"
            output = root / "bundle.zip"
            state.write_text(
                json.dumps(
                    {
                        "env": {"token": "abc"},
                        "line": "password=hunter2 Authorization: Bearer bearer-token",
                        "remote": "https://user:url-pass@example.com/path",
                    }
                ),
                encoding="utf-8",
            )
            workflow.write_text(
                json.dumps({"details": {"api_key": "sk-test", "command": "--token cli-secret"}}) + "\n",
                encoding="utf-8",
            )
            server.write_text(
                json.dumps({"host": "127.0.0.1", "port": 1234, "token": "server-token-value"}),
                encoding="utf-8",
            )

            created = create_debug_bundle(
                output,
                state_path=state,
                workflow_path=workflow,
                server_info_path=server,
            )

            self.assertEqual(created, output)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("state.json", names)
                self.assertIn("workflow.jsonl", names)
                self.assertIn("server.json", names)
                payload = "\n".join(archive.read(name).decode("utf-8") for name in sorted(names))

        self.assertNotIn("hunter2", payload)
        self.assertNotIn("bearer-token", payload)
        self.assertNotIn("url-pass", payload)
        self.assertNotIn("sk-test", payload)
        self.assertNotIn("cli-secret", payload)
        self.assertNotIn("server-token-value", payload)
        self.assertIn("[redacted]", payload)


if __name__ == "__main__":
    unittest.main()
