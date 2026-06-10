import unittest
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
