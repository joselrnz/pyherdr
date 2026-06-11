import unittest
from pathlib import Path


class RoadmapDocsTests(unittest.TestCase):
    def test_remote_ssh_design_covers_ownership_and_reconnect(self):
        text = Path("docs/remote-ssh.md").read_text(encoding="utf-8").lower()

        self.assertIn("process ownership", text)
        self.assertIn("reconnect", text)
        self.assertIn("remote_host", text)

    def test_multi_client_policy_covers_read_only_and_multi_writer(self):
        text = Path("docs/multi-client-policy.md").read_text(encoding="utf-8").lower()

        self.assertIn("read-only", text)
        self.assertIn("multi-writer", text)
        self.assertIn("single writer", text)

    def test_dashboard_decision_covers_scope_auth_and_live_updates(self):
        text = Path("docs/web-dashboard.md").read_text(encoding="utf-8").lower()

        self.assertIn("mvp scope", text)
        self.assertIn("remote bind is opt-in", text)
        self.assertIn("live updates", text)


if __name__ == "__main__":
    unittest.main()
