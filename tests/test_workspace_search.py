import os
import tempfile
import unittest
from pathlib import Path

from pyherdr.workspace_search import SearchRoot, search_workspace_rows


class WorkspaceSearchTests(unittest.TestCase):
    def test_discovers_repositories_and_skips_ignored_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "alpha-app"
            repo.mkdir()
            (repo / ".git").mkdir()
            ignored = root / "node_modules" / "alpha-hidden"
            ignored.mkdir(parents=True)
            hidden = root / ".venv" / "alpha-env"
            hidden.mkdir(parents=True)

            rows = search_workspace_rows("alpha", [SearchRoot(str(root), label="code")])

        labels = [row.label for row in rows]
        self.assertIn("alpha-app", labels)
        self.assertNotIn("alpha-hidden", labels)
        self.assertNotIn("alpha-env", labels)
        self.assertEqual(rows[0].kind, "repo")
        self.assertEqual(rows[0].label, "alpha-app")

    def test_ranks_exact_prefix_and_substring_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exact = root / "api"
            prefix = root / "api-server"
            substring = root / "my-api"
            exact.mkdir()
            prefix.mkdir()
            substring.mkdir()

            rows = search_workspace_rows("api", [SearchRoot(str(root))])

        self.assertEqual([row.label for row in rows[:3]], ["api", "api-server", "my-api"])
        self.assertGreater(rows[0].score, rows[1].score)
        self.assertGreater(rows[1].score, rows[2].score)

    def test_includes_matching_stale_roots_without_opening_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "ghostc-plugin"

            rows = search_workspace_rows("ghost", [SearchRoot(str(missing), label="ghostc-plugin", source="recent")])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "stale")
        self.assertTrue(rows[0].stale)
        self.assertEqual(rows[0].label, "ghostc-plugin")

    def test_respects_depth_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "one" / "two" / "target-project"
            target.mkdir(parents=True)

            shallow = search_workspace_rows("target", [SearchRoot(str(root))], max_depth=1)
            deep = search_workspace_rows("target", [SearchRoot(str(root))], max_depth=3)

        self.assertEqual(shallow, [])
        self.assertEqual([row.label for row in deep], ["target-project"])

    @unittest.skipIf(os.name == "nt", "directory symlink creation is not reliable on all Windows setups")
    def test_skips_symlink_loops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "looped-project"
            child.mkdir()
            (child / "back").symlink_to(root, target_is_directory=True)

            rows = search_workspace_rows("looped", [SearchRoot(str(root))], max_depth=5)

        self.assertEqual([row.label for row in rows], ["looped-project"])


if __name__ == "__main__":
    unittest.main()
