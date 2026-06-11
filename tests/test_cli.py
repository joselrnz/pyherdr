import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from pyherdr.cli import build_parser
from pyherdr.demo_screenshot import render_demo_screenshot


class CliTests(unittest.TestCase):
    def test_demo_screenshot_accepts_workflow_view(self):
        args = build_parser().parse_args(["demo-screenshot", "--view", "workflow"])

        self.assertEqual(args.command, "demo-screenshot")
        self.assertEqual(args.view, "workflow")

    def test_demo_screenshot_accepts_fanout_view(self):
        args = build_parser().parse_args(["demo-screenshot", "--view", "fanout"])

        self.assertEqual(args.command, "demo-screenshot")
        self.assertEqual(args.view, "fanout")

    def test_demo_screenshot_accepts_workspace_picker_view(self):
        args = build_parser().parse_args(["demo-screenshot", "--view", "workspace-picker"])

        self.assertEqual(args.command, "demo-screenshot")
        self.assertEqual(args.view, "workspace-picker")

    def test_demo_screenshot_accepts_workspace_search_view(self):
        args = build_parser().parse_args(["demo-screenshot", "--view", "workspace-search"])

        self.assertEqual(args.command, "demo-screenshot")
        self.assertEqual(args.view, "workspace-search")

    def test_demo_screenshot_renders_workspace_picker_view(self):
        import html
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output = render_demo_screenshot(Path(tmp) / "picker.svg", width=100, height=30, view="workspace-picker")

            svg = output.read_text(encoding="utf-8")
        plain = html.unescape(svg).replace("\xa0", " ")
        self.assertIn("choose workspace folder", plain)
        self.assertIn("Open Folder", plain)
        self.assertIn("Enter", plain)
        self.assertIn("^H home", plain)
        self.assertIn("^W ws", plain)
        self.assertIn("^R repo", plain)
        self.assertIn("branch main", plain)
        self.assertIn("dirty", plain)

    def test_demo_screenshot_renders_workspace_search_view(self):
        import html
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output = render_demo_screenshot(Path(tmp) / "search.svg", width=100, height=30, view="workspace-search")

            svg = output.read_text(encoding="utf-8")
        plain = html.unescape(svg).replace("\xa0", " ")
        self.assertIn("search mode", plain)
        self.assertIn("[ ] repo", plain)
        self.assertIn("pyherdr-demo", plain)
        self.assertEqual(plain.count("[ ] repo"), 1)
        self.assertEqual(plain.count("[ ] dir"), 1)

    def test_workflow_graph_accepts_svg_output(self):
        args = build_parser().parse_args(["workflow", "graph", "--format", "svg", "--output", "graph.svg"])

        self.assertEqual(args.command, "workflow")
        self.assertEqual(args.workflow_command, "graph")
        self.assertEqual(args.format, "svg")
        self.assertEqual(args.output, "graph.svg")

    def test_workspace_recents_accepts_json_all_and_prune(self):
        args = build_parser().parse_args(["workspace", "recents", "--all", "--json", "--prune"])

        self.assertEqual(args.command, "workspace")
        self.assertEqual(args.workspace_command, "recents")
        self.assertTrue(args.all)
        self.assertTrue(args.json)
        self.assertTrue(args.prune)

    def test_workspace_search_accepts_json_and_scan_overrides(self):
        args = build_parser().parse_args(
            [
                "workspace",
                "search",
                "alpha",
                "--json",
                "--root",
                "C:/code",
                "--max-depth",
                "2",
                "--max-results",
                "7",
                "--ignore",
                "vendor",
                "--include-hidden",
            ]
        )

        self.assertEqual(args.command, "workspace")
        self.assertEqual(args.workspace_command, "search")
        self.assertEqual(args.query, "alpha")
        self.assertTrue(args.json)
        self.assertEqual(args.root, ["C:/code"])
        self.assertEqual(args.max_depth, 2)
        self.assertEqual(args.max_results, 7)
        self.assertEqual(args.ignore, ["vendor"])
        self.assertTrue(args.include_hidden)

    def test_workspace_search_json_outputs_matching_repositories(self):
        import json
        import tempfile

        from pyherdr.cli import run_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "alpha-api"
            repo.mkdir()
            (repo / ".git").mkdir()
            ignored = root / "vendor" / "alpha-hidden"
            ignored.mkdir(parents=True)
            args = build_parser().parse_args(
                [
                    "workspace",
                    "search",
                    "alpha",
                    "--json",
                    "--root",
                    str(root),
                    "--ignore",
                    "vendor",
                ]
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = run_workspace(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["query"], "alpha")
        self.assertEqual([row["label"] for row in payload["results"]], ["alpha-api"])
        self.assertEqual(payload["results"][0]["kind"], "repo")
        self.assertNotIn("alpha-hidden", json.dumps(payload))

    def test_pane_fanout_accepts_targets_and_execute_flag(self):
        args = build_parser().parse_args(
            [
                "pane",
                "fanout",
                "--all",
                "--target",
                "session:current",
                "--target",
                "workspace:main",
                "--target",
                "tab:tests",
                "--target",
                "pane:1-1",
                "--execute",
                "--confirm-risky",
                "--no-enter",
                "pytest",
                "-q",
            ]
        )

        self.assertEqual(args.command, "pane")
        self.assertEqual(args.pane_command, "fanout")
        self.assertTrue(args.all)
        self.assertEqual(args.target, ["session:current", "workspace:main", "tab:tests", "pane:1-1"])
        self.assertTrue(args.execute)
        self.assertTrue(args.confirm_risky)
        self.assertTrue(args.no_enter)
        self.assertEqual(args.command_parts, ["pytest", "-q"])

    def test_demo_screenshot_rejects_unknown_view_before_rendering(self):
        with self.assertRaises(ValueError):
            render_demo_screenshot(Path("unused.svg"), view="missing")


if __name__ == "__main__":
    unittest.main()
