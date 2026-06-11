import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

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

    def test_demo_screenshot_accepts_workspace_search_variant_views(self):
        for view in ("workspace-search-selected", "workspace-search-stale", "workspace-search-long-path"):
            with self.subTest(view=view):
                args = build_parser().parse_args(["demo-screenshot", "--view", view])

                self.assertEqual(args.command, "demo-screenshot")
                self.assertEqual(args.view, view)

    def test_demo_screenshot_renders_workspace_picker_view(self):
        import html
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output = render_demo_screenshot(Path(tmp) / "picker.svg", width=100, height=30, view="workspace-picker")

            svg = output.read_text(encoding="utf-8")
        plain = html.unescape(svg).replace("\xa0", " ")
        self.assertIn("choose workspace folder", plain)
        self.assertIn("Open Folder", plain)
        self.assertIn("Help", plain)
        self.assertIn("filter here", plain)
        self.assertIn("Enter", plain)
        self.assertNotIn("^W ws", plain)
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

    def test_demo_screenshot_renders_workspace_search_selected_view(self):
        import html
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output = render_demo_screenshot(
                Path(tmp) / "search-selected.svg",
                width=100,
                height=30,
                view="workspace-search-selected",
            )

            svg = output.read_text(encoding="utf-8")
        plain = html.unescape(svg).replace("\xa0", " ")
        self.assertIn("search mode", plain)
        self.assertIn("[x] repo", plain)
        self.assertIn("pyherdr-demo", plain)

    def test_demo_screenshot_renders_workspace_search_stale_view(self):
        import html
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output = render_demo_screenshot(
                Path(tmp) / "search-stale.svg",
                width=100,
                height=30,
                view="workspace-search-stale",
            )

            svg = output.read_text(encoding="utf-8")
        plain = html.unescape(svg).replace("\xa0", " ")
        self.assertIn("search mode", plain)
        self.assertIn("[ ] stale", plain)
        self.assertIn("pyherdr-missing", plain)

    def test_demo_screenshot_renders_workspace_search_long_path_view(self):
        import html
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output = render_demo_screenshot(
                Path(tmp) / "search-long-path.svg",
                width=100,
                height=30,
                view="workspace-search-long-path",
            )

            svg = output.read_text(encoding="utf-8")
        plain = html.unescape(svg).replace("\xa0", " ")
        self.assertIn("search mode", plain)
        self.assertIn("pyherdr-operations-console", plain)
        self.assertIn("regional-command-center", plain)

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

    def test_workspace_index_accepts_refresh_prune_and_scan_overrides(self):
        args = build_parser().parse_args(
            [
                "workspace",
                "index",
                "--json",
                "--all",
                "--refresh",
                "--prune",
                "--root",
                "C:/code",
                "--max-depth",
                "2",
                "--max-entries",
                "7",
                "--ignore",
                "vendor",
                "--include-hidden",
            ]
        )

        self.assertEqual(args.command, "workspace")
        self.assertEqual(args.workspace_command, "index")
        self.assertTrue(args.json)
        self.assertTrue(args.all)
        self.assertTrue(args.refresh)
        self.assertTrue(args.prune)
        self.assertEqual(args.root, ["C:/code"])
        self.assertEqual(args.max_depth, 2)
        self.assertEqual(args.max_entries, 7)
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

    def test_workspace_index_refresh_json_outputs_cached_repositories(self):
        import json
        import tempfile

        from pyherdr.cli import run_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "alpha-api"
            repo.mkdir()
            (repo / ".git").mkdir()
            cache_path = root / "workspace_search_cache.json"
            args = build_parser().parse_args(
                [
                    "workspace",
                    "index",
                    "--refresh",
                    "--json",
                    "--root",
                    str(root),
                    "--max-depth",
                    "1",
                ]
            )
            stdout = StringIO()
            with (
                patch("pyherdr.cli.default_workspace_search_cache_path", return_value=cache_path),
                patch("pyherdr.workspace_search._git_branch", return_value="main"),
                patch("pyherdr.workspace_search._git_dirty", return_value=True),
                redirect_stdout(stdout),
            ):
                exit_code = run_workspace(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summaries"][0]["indexed"], 1)
        self.assertEqual(payload["entries"][0]["label"], "alpha-api")
        self.assertEqual(payload["entries"][0]["branch"], "main")
        self.assertTrue(payload["entries"][0]["dirty"])

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

    def test_pane_capture_parses_lines_styled_and_text_flags(self):
        args = build_parser().parse_args(["pane", "capture", "1-1", "--lines", "50", "--styled", "--text"])

        self.assertEqual(args.command, "pane")
        self.assertEqual(args.pane_command, "capture")
        self.assertEqual(args.pane_id, "1-1")
        self.assertEqual(args.lines, 50)
        self.assertTrue(args.styled)
        self.assertTrue(args.text)

    def test_pane_capture_defaults_to_whole_buffer_as_json(self):
        from pyherdr.cli import run_pane

        args = build_parser().parse_args(["pane", "capture", "1-1"])
        self.assertIsNone(args.lines)

        captured: dict = {}

        def fake_request(request):
            captured.update(request)
            return {"id": "cli", "result": {"type": "pane_capture", "output": "a\nb", "total_lines": 2}}

        stdout = StringIO()
        with patch("pyherdr.cli.ensure_request", fake_request), redirect_stdout(stdout):
            exit_code = run_pane(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["method"], "pane.capture")
        self.assertEqual(captured["params"], {"pane_id": "1-1", "lines": None, "styled": False})
        self.assertIn('"total_lines": 2', stdout.getvalue())

    def test_pane_capture_text_flag_prints_raw_output(self):
        from pyherdr.cli import run_pane

        args = build_parser().parse_args(["pane", "capture", "1-1", "--text"])

        def fake_request(request):
            return {"id": "cli", "result": {"type": "pane_capture", "output": "raw line one\nraw line two"}}

        stdout = StringIO()
        with patch("pyherdr.cli.ensure_request", fake_request), redirect_stdout(stdout):
            exit_code = run_pane(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "raw line one\nraw line two")
        self.assertNotIn("pane_capture", stdout.getvalue())

    def test_session_record_parses_output_lines_and_styled_flags(self):
        args = build_parser().parse_args(["session", "record", "--output", "rec.json", "--lines", "50", "--styled"])

        self.assertEqual(args.command, "session")
        self.assertEqual(args.session_command, "record")
        self.assertEqual(args.output, "rec.json")
        self.assertEqual(args.lines, 50)
        self.assertTrue(args.styled)

    def test_session_record_output_prints_summary_not_full_recording(self):
        from pyherdr.cli import run_session

        args = build_parser().parse_args(["session", "record", "--output", "rec.json", "--lines", "20"])
        captured: dict = {}

        def fake_request(request):
            captured.update(request)
            return {
                "id": "cli",
                "result": {
                    "type": "session_recording",
                    "path": "rec.json",
                    "pane_count": 2,
                    "timeline_count": 4,
                    "recording": {"large": "omitted in CLI summary"},
                },
            }

        stdout = StringIO()
        with patch("pyherdr.cli.ensure_request", fake_request), redirect_stdout(stdout):
            exit_code = run_session(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["method"], "session.record")
        self.assertEqual(captured["params"], {"output": "rec.json", "lines": 20, "styled": False})
        printed = stdout.getvalue()
        self.assertIn('"path": "rec.json"', printed)
        self.assertIn('"pane_count": 2', printed)
        self.assertNotIn("omitted in CLI summary", printed)

    def test_session_replay_prints_recording_summary(self):
        from pyherdr.cli import run_session

        args = build_parser().parse_args(["session", "replay", "recording.json"])

        with patch(
            "pyherdr.cli.load_recording",
            return_value={"type": "session_recording", "workspaces": [], "timeline": []},
        ), patch(
            "pyherdr.cli.summarize_recording",
            return_value={"type": "recording_summary", "pane_count": 0},
        ):
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = run_session(args)

        self.assertEqual(exit_code, 0)
        self.assertIn('"recording_summary"', stdout.getvalue())

    def test_debug_bundle_parses_output(self):
        args = build_parser().parse_args(["debug", "bundle", "--output", "bundle.zip"])

        self.assertEqual(args.command, "debug")
        self.assertEqual(args.debug_command, "bundle")
        self.assertEqual(args.output, "bundle.zip")

    def test_remote_probe_parses_host(self):
        args = build_parser().parse_args(["remote", "probe", "buildbox", "--timeout", "3"])

        self.assertEqual(args.command, "remote")
        self.assertEqual(args.remote_command, "probe")
        self.assertEqual(args.host, "buildbox")
        self.assertEqual(args.timeout, 3)

    def test_plugin_validate_parses_manifest_path(self):
        args = build_parser().parse_args(["plugin", "validate", "plugin.json"])

        self.assertEqual(args.command, "plugin")
        self.assertEqual(args.plugin_command, "validate")
        self.assertEqual(args.manifest, "plugin.json")

    def test_demo_screenshot_rejects_unknown_view_before_rendering(self):
        with self.assertRaises(ValueError):
            render_demo_screenshot(Path("unused.svg"), view="missing")


if __name__ == "__main__":
    unittest.main()
