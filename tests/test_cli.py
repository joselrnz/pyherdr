import json
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from pyherdr.cli import build_parser
from pyherdr.demo_gif import render_demo_gif
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

    def test_demo_gif_accepts_scripted_storyboard_options(self):
        args = build_parser().parse_args(
            [
                "demo-gif",
                "--output",
                "demo.gif",
                "--views",
                "main,workflow",
                "--duration-ms",
                "250",
            ]
        )

        self.assertEqual(args.command, "demo-gif")
        self.assertEqual(args.output, "demo.gif")
        self.assertEqual(args.views, "main,workflow")
        self.assertEqual(args.duration_ms, 250)

    def test_agent_focus_accepts_attention_target(self):
        args = build_parser().parse_args(["agent", "focus", "--attention"])

        self.assertEqual(args.command, "agent")
        self.assertEqual(args.agent_command, "focus")
        self.assertTrue(args.attention)
        self.assertIsNone(args.target)

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

    def test_demo_gif_renders_animated_product_state(self):
        import tempfile

        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            output = render_demo_gif(
                Path(tmp) / "demo.gif",
                width=480,
                height=270,
                duration_ms=80,
                views=("main", "workflow"),
            )
            data = output.read_bytes()
            with Image.open(output) as image:
                frame_count = image.n_frames
                size = image.size

        self.assertTrue(data.startswith(b"GIF89a"))
        self.assertIn(b"NETSCAPE2.0", data)
        self.assertEqual(frame_count, 2)
        self.assertEqual(size, (480, 270))

    def test_demo_gif_rejects_unknown_views(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unknown demo GIF view"):
                render_demo_gif(Path(tmp) / "demo.gif", views=("main", "missing"))

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

    def test_layout_templates_command_lists_builtin_templates(self):
        from pyherdr.cli import run_layout

        args = build_parser().parse_args(["layout", "templates"])

        def fake_request(request):
            return {
                "id": "cli",
                "result": {
                    "type": "layout_template_list",
                    "templates": [{"id": "grid-2x2", "label": "2x2 grid", "pane_count": 4}],
                },
            }

        stdout = StringIO()
        with patch("pyherdr.cli.ensure_request", fake_request), redirect_stdout(stdout):
            exit_code = run_layout(args)

        self.assertEqual(exit_code, 0)
        self.assertIn('"grid-2x2"', stdout.getvalue())

    def test_layout_apply_command_dispatches_template_request(self):
        from pyherdr.cli import run_layout

        args = build_parser().parse_args(
            ["layout", "apply", "grid-2x2", "--workspace-id", "ws_1", "--tab-id", "tab_1"]
        )
        captured: dict = {}

        def fake_request(request):
            captured.update(request)
            return {"id": "cli", "result": {"type": "layout_template_applied", "pane_count": 4}}

        stdout = StringIO()
        with patch("pyherdr.cli.ensure_request", fake_request), redirect_stdout(stdout):
            exit_code = run_layout(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["method"], "layout.template.apply")
        self.assertEqual(
            captured["params"],
            {"template": "grid-2x2", "workspace_id": "ws_1", "tab_id": "tab_1"},
        )
        self.assertIn('"layout_template_applied"', stdout.getvalue())

    def test_layout_export_command_writes_custom_layout_file(self):
        import tempfile

        from pyherdr.cli import run_layout

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "wide.json"
            args = build_parser().parse_args(
                ["layout", "export", "wide", "--output", str(output), "--workspace-id", "ws_1", "--tab-id", "tab_1"]
            )
            captured: dict = {}

            def fake_request(request):
                captured.update(request)
                return {
                    "id": "cli",
                    "result": {
                        "type": "layout_custom_exported",
                        "layout": {
                            "id": "wide",
                            "label": "wide",
                            "pane_count": 2,
                            "layout": {
                                "root": {"kind": "pane", "pane_id": "pane_1"},
                                "focus": "pane_1",
                            },
                        },
                    },
                }

            stdout = StringIO()
            with patch("pyherdr.cli.ensure_request", fake_request), redirect_stdout(stdout):
                exit_code = run_layout(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(captured["method"], "layout.custom.export")
            self.assertEqual(captured["params"], {"name": "wide", "workspace_id": "ws_1", "tab_id": "tab_1"})
            self.assertTrue(output.exists())
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["id"], "wide")
            self.assertEqual(json.loads(stdout.getvalue())["path"], str(output))

    def test_layout_import_command_dispatches_custom_layout(self):
        import tempfile

        from pyherdr.cli import run_layout

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "wide.json"
            source.write_text(
                json.dumps(
                    {
                        "id": "wide",
                        "label": "wide",
                        "pane_count": 1,
                        "layout": {"root": {"kind": "pane", "pane_id": "pane_1"}, "focus": "pane_1"},
                    }
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                ["layout", "import", str(source), "--workspace-id", "ws_1", "--tab-id", "tab_1"]
            )
            captured: dict = {}

            def fake_request(request):
                captured.update(request)
                return {"id": "cli", "result": {"type": "layout_custom_applied", "pane_count": 1}}

            stdout = StringIO()
            with patch("pyherdr.cli.ensure_request", fake_request), redirect_stdout(stdout):
                exit_code = run_layout(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(captured["method"], "layout.custom.apply")
            self.assertEqual(captured["params"]["workspace_id"], "ws_1")
            self.assertEqual(captured["params"]["tab_id"], "tab_1")
            self.assertEqual(captured["params"]["layout"]["id"], "wide")
            self.assertIn('"layout_custom_applied"', stdout.getvalue())

    def test_profile_commands_parse(self):
        args = build_parser().parse_args(["profile", "plan", "ops", "--workflow", "health"])

        self.assertEqual(args.command, "profile")
        self.assertEqual(args.profile_command, "plan")
        self.assertEqual(args.name, "ops")
        self.assertEqual(args.workflow, "health")
        attach = build_parser().parse_args(["profile", "attach", "ops"])
        stop = build_parser().parse_args(["profile", "stop", "ops"])

        self.assertEqual(attach.profile_command, "attach")
        self.assertEqual(stop.profile_command, "stop")

    def test_profile_attach_and_stop_use_profile_session_name(self):
        from pyherdr.cli import run_profile
        from pyherdr.config import Config

        attach_args = build_parser().parse_args(["profile", "attach", "ops/team"])
        stop_args = build_parser().parse_args(["profile", "stop", "ops/team"])
        stdout = StringIO()
        with (
            patch("pyherdr.cli.load_config", return_value=Config()),
            patch("pyherdr.cli._attach_session", return_value=0) as attach_session,
            redirect_stdout(stdout),
        ):
            self.assertEqual(run_profile(attach_args), 0)
        attach_session.assert_called_once_with("profile-ops-team")

        stdout = StringIO()
        with (
            patch("pyherdr.cli.load_config", return_value=Config()),
            patch("pyherdr.cli._stop_session", return_value=True) as stop_session,
            redirect_stdout(stdout),
        ):
            self.assertEqual(run_profile(stop_args), 0)

        stop_session.assert_called_once_with("profile-ops-team")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["session"], "profile-ops-team")
        self.assertTrue(payload["stopped"])

    def test_profile_list_prints_inventory_summary(self):
        from pyherdr.cli import run_profile
        from pyherdr.config import Config, ConnectionConfig, ProfileConfig

        args = build_parser().parse_args(["profile", "list"])
        config = Config(
            connections={"prod": ConnectionConfig(host="prod.example.com")},
            profiles={"ops": ProfileConfig()},
        )

        stdout = StringIO()
        with patch("pyherdr.cli.load_config", return_value=config), redirect_stdout(stdout):
            exit_code = run_profile(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["type"], "profile_list")
        self.assertEqual(payload["connections"], ["prod"])
        self.assertEqual(payload["profiles"], ["ops"])

    def test_profile_validate_returns_error_for_invalid_inventory(self):
        from pyherdr.cli import run_profile
        from pyherdr.config import Config, ConnectionConfig

        args = build_parser().parse_args(["profile", "validate"])
        config = Config(connections={"bad": ConnectionConfig(host="prod.example.com", password="secret")})

        stdout = StringIO()
        with patch("pyherdr.cli.load_config", return_value=config), redirect_stdout(stdout):
            exit_code = run_profile(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("unsupported password storage", payload["errors"][0])

    def test_profile_plan_prints_generated_commands(self):
        from pyherdr.cli import run_profile
        from pyherdr.config import Config, ConnectionConfig, ProfileConfig, ProfilePaneConfig

        args = build_parser().parse_args(["profile", "plan", "ops"])
        config = Config(
            connections={"prod": ConnectionConfig(host="prod.example.com", user="ops")},
            profiles={
                "ops": ProfileConfig(panes=[ProfilePaneConfig(name="prod", connection="prod", command="uptime")])
            },
        )

        stdout = StringIO()
        with patch("pyherdr.cli.load_config", return_value=config), redirect_stdout(stdout):
            exit_code = run_profile(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["type"], "profile_plan")
        self.assertEqual(payload["panes"][0]["command"], "ssh -o ConnectTimeout=10 ops@prod.example.com uptime")

    def test_profile_start_creates_and_starts_profile_panes(self):
        from pyherdr.cli import run_profile
        from pyherdr.config import (
            Config,
            ConnectionConfig,
            ProfileConfig,
            ProfilePaneConfig,
            WorkflowConfig,
            WorkflowStepConfig,
        )
        from pyherdr.server import ServerInfo

        args = build_parser().parse_args(["profile", "start", "ops", "--workflow", "health"])
        config = Config(
            connections={"prod": ConnectionConfig(host="prod.example.com", user="ops")},
            profiles={
                "ops": ProfileConfig(
                    workspace="ops",
                    cwd="C:/work",
                    layout="main-left",
                    env={"APP_ENV": "prod", "SHARED": "profile"},
                    panes=[
                        ProfilePaneConfig(name="local", position="left", command="pwsh", start_order=30),
                        ProfilePaneConfig(
                            name="prod",
                            position="right-top",
                            connection="prod",
                            command="uptime",
                            env={"HOST_ROLE": "api", "SHARED": "pane"},
                            start_order=10,
                            health_check="systemctl is-active app",
                            health_match="active",
                            health_timeout_ms=1000,
                        ),
                        ProfilePaneConfig(
                            name="logs",
                            position="right-bottom",
                            command="tail -f app.log",
                            start_order=20,
                        ),
                    ],
                )
            },
            workflows={
                "health": WorkflowConfig(
                    profile="ops",
                    steps=[
                        WorkflowStepConfig(pane="prod", send="systemctl status app"),
                        WorkflowStepConfig(pane="logs", command="grep ERROR app.log", enter=False),
                    ],
                )
            },
        )
        calls: list[dict] = []
        sessions_seen: list[str | None] = []
        restored_sessions: list[str | None] = []

        def fake_start_background() -> ServerInfo:
            sessions_seen.append(os.environ.get("PYHERDR_SESSION"))
            return ServerInfo("127.0.0.1", 1, 2, "state.json")

        def fake_request(_info: ServerInfo, payload: dict) -> dict:
            calls.append(payload)
            method = payload["method"]
            if method == "workspace.create":
                return {"result": {"workspace": {"workspace_id": "ws"}}}
            if method == "pane.list":
                return {"result": {"panes": [{"pane_id": "p1"}]}}
            if method == "pane.rename":
                return {
                    "result": {
                        "pane": {"pane_id": payload["params"]["pane_id"], "title": payload["params"]["title"]}
                    }
                }
            if method == "pane.create":
                title = payload["params"]["title"]
                return {"result": {"pane": {"pane_id": f"pane-{title}", "title": title}}}
            if method == "pane.start":
                return {"result": {"pane": {"pane_id": payload["params"]["pane_id"]}, "started": True}}
            if method == "pane.set_layout":
                return {"result": {"type": "pane_layout_set"}}
            if method == "pane.send_text":
                return {"result": {"type": "pane_text_sent"}}
            if method == "pane.send_key":
                return {"result": {"type": "pane_key_sent"}}
            if method == "pane.read":
                return {"result": {"output": "app active\n"}}
            raise AssertionError(method)

        stdout = StringIO()
        with (
            patch("pyherdr.cli.load_config", return_value=config),
            patch("pyherdr.cli.start_background", side_effect=fake_start_background),
            patch("pyherdr.cli.request", fake_request),
            patch.dict("os.environ", {"PYHERDR_SESSION": "before"}, clear=False),
            redirect_stdout(stdout),
        ):
            exit_code = run_profile(args)
            restored_sessions.append(os.environ.get("PYHERDR_SESSION"))

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["type"], "profile_start")
        self.assertEqual(payload["session"], "profile-ops")
        self.assertEqual(sessions_seen, ["profile-ops"])
        self.assertEqual(restored_sessions, ["before"])
        self.assertEqual([pane["name"] for pane in payload["panes"]], ["local", "prod", "logs"])
        start_commands = [call["params"]["command"] for call in calls if call["method"] == "pane.start"]
        self.assertEqual(
            start_commands,
            ["ssh -o ConnectTimeout=10 ops@prod.example.com uptime", "tail -f app.log", "pwsh"],
        )
        start_envs = [call["params"].get("env", {}) for call in calls if call["method"] == "pane.start"]
        self.assertEqual(
            start_envs,
            [
                {"APP_ENV": "prod", "SHARED": "pane", "HOST_ROLE": "api"},
                {"APP_ENV": "prod", "SHARED": "profile"},
                {"APP_ENV": "prod", "SHARED": "profile"},
            ],
        )
        layout_calls = [call for call in calls if call["method"] == "pane.set_layout"]
        self.assertEqual(len(layout_calls), 1)
        layout_root = layout_calls[0]["params"]["layout"]["root"]
        self.assertEqual(layout_root["first"]["pane_id"], "p1")
        self.assertEqual(layout_root["second"]["first"]["pane_id"], "pane-prod")
        self.assertEqual(layout_root["second"]["second"]["pane_id"], "pane-logs")
        sent_text = [
            (call["params"]["pane_id"], call["params"]["text"]) for call in calls if call["method"] == "pane.send_text"
        ]
        self.assertEqual(
            sent_text,
            [
                ("pane-prod", "systemctl is-active app"),
                ("pane-prod", "systemctl status app"),
                ("pane-logs", "grep ERROR app.log"),
            ],
        )
        sent_keys = [
            (call["params"]["pane_id"], call["params"]["key"]) for call in calls if call["method"] == "pane.send_key"
        ]
        self.assertEqual(sent_keys, [("pane-prod", "enter"), ("pane-prod", "enter")])
        self.assertEqual(
            payload["health_execution"]["checks"],
            [
                {
                    "pane": "prod",
                    "pane_id": "pane-prod",
                    "command": "systemctl is-active app",
                    "match": "active",
                    "regex": False,
                    "timeout_ms": 1000,
                    "matched": True,
                }
            ],
        )
        self.assertEqual(
            payload["workflow_execution"]["steps"],
            [
                {"pane": "prod", "pane_id": "pane-prod", "text": "systemctl status app", "enter": True},
                {"pane": "logs", "pane_id": "pane-logs", "text": "grep ERROR app.log", "enter": False},
            ],
        )

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

    def test_headless_init_parses_workspace_pane_and_command(self):
        args = build_parser().parse_args(
            [
                "headless",
                "init",
                "--workspace-label",
                "ci",
                "--cwd",
                "C:/repo",
                "--pane-title",
                "runner",
                "--",
                "python",
                "-m",
                "pytest",
            ]
        )

        self.assertEqual(args.command, "headless")
        self.assertEqual(args.headless_command, "init")
        self.assertEqual(args.workspace_label, "ci")
        self.assertEqual(args.cwd, "C:/repo")
        self.assertEqual(args.pane_title, "runner")
        self.assertEqual(args.command_parts, ["--", "python", "-m", "pytest"])

    def test_headless_init_creates_workspace_pane_and_starts_command(self):
        from pyherdr.cli import run_headless
        from pyherdr.server import ServerInfo

        info = ServerInfo("127.0.0.1", 4567, 123, "state.json", "secret-token")
        responses = [
            {
                "id": "headless",
                "result": {
                    "type": "workspace_created",
                    "workspace": {
                        "workspace_id": "ws_1",
                        "label": "ci",
                        "cwd": "C:/repo",
                        "status": "idle",
                        "focused_tab_id": "tab_1",
                    },
                },
            },
            {
                "id": "headless",
                "result": {
                    "type": "pane_list",
                    "panes": [
                        {
                            "pane_id": "1-1",
                            "workspace_id": "ws_1",
                            "tab_id": "tab_1",
                            "title": "pane",
                            "cwd": "C:/repo",
                        }
                    ],
                },
            },
            {
                "id": "headless",
                "result": {
                    "type": "pane_renamed",
                    "pane": {
                        "pane_id": "1-1",
                        "workspace_id": "ws_1",
                        "tab_id": "tab_1",
                        "title": "runner",
                        "cwd": "C:/repo",
                    },
                },
            },
            {
                "id": "headless",
                "result": {
                    "type": "pane_start",
                    "started": True,
                    "pane": {
                        "pane_id": "1-1",
                        "workspace_id": "ws_1",
                        "tab_id": "tab_1",
                        "title": "runner",
                        "cwd": "C:/repo",
                        "command": "python -m pytest",
                    },
                },
            },
        ]
        args = build_parser().parse_args(
            [
                "headless",
                "init",
                "--workspace-label",
                "ci",
                "--cwd",
                "C:/repo",
                "--pane-title",
                "runner",
                "--",
                "python",
                "-m",
                "pytest",
            ]
        )

        stdout = StringIO()
        with (
            patch("pyherdr.cli.start_background", return_value=info),
            patch("pyherdr.cli.request", side_effect=responses) as send,
            redirect_stdout(stdout),
        ):
            exit_code = run_headless(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["type"], "headless_init")
        self.assertEqual(payload["workspace"]["workspace_id"], "ws_1")
        self.assertEqual(payload["pane"]["title"], "runner")
        self.assertEqual(payload["started"]["started"], True)
        self.assertNotIn("secret-token", stdout.getvalue())
        self.assertEqual(
            [call.args[1]["method"] for call in send.call_args_list],
            ["workspace.create", "pane.list", "pane.rename", "pane.start"],
        )

    def test_headless_start_prints_redacted_server_info(self):
        from pyherdr.cli import run_headless
        from pyherdr.server import ServerInfo

        info = ServerInfo("127.0.0.1", 4567, 123, "state.json", "secret-token")
        args = build_parser().parse_args(["headless", "start"])

        stdout = StringIO()
        with patch("pyherdr.cli.start_background", return_value=info), redirect_stdout(stdout):
            exit_code = run_headless(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["type"], "headless_server")
        self.assertEqual(payload["port"], 4567)
        self.assertNotIn("secret-token", stdout.getvalue())

    def test_server_restart_parses(self):
        args = build_parser().parse_args(["server", "restart"])

        self.assertEqual(args.command, "server")
        self.assertEqual(args.server_command, "restart")

    def test_server_restart_stops_then_starts_and_redacts_token(self):
        from pyherdr.cli import run_server
        from pyherdr.server import ServerInfo

        info = ServerInfo("127.0.0.1", 4567, 123, "state.json", "secret-token")
        args = build_parser().parse_args(["server", "restart"])

        stdout = StringIO()
        with (
            patch("pyherdr.cli.stop_running", return_value=True) as stop,
            patch("pyherdr.cli.start_background", return_value=info) as start,
            redirect_stdout(stdout),
        ):
            exit_code = run_server(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["restarted"])
        self.assertTrue(payload["stopped"])
        self.assertEqual(payload["server"]["port"], 4567)
        self.assertNotIn("secret-token", stdout.getvalue())
        stop.assert_called_once_with()
        start.assert_called_once_with()

    def test_server_status_reports_stale_info_and_repair_hint(self):
        from pyherdr.cli import run_server
        from pyherdr.server import ServerInfo

        info = ServerInfo("127.0.0.1", 4567, 123, "state.json", "secret-token")
        args = build_parser().parse_args(["server", "status"])

        stdout = StringIO()
        with (
            patch("pyherdr.cli.read_server_info", return_value=info),
            patch("pyherdr.cli.ping", return_value=False),
            redirect_stdout(stdout),
        ):
            exit_code = run_server(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertFalse(payload["running"])
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["state_path"], "state.json")
        self.assertEqual(payload["repair"], "pyherdr server restart")
        self.assertNotIn("secret-token", stdout.getvalue())

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

        by_connection = build_parser().parse_args(["remote", "probe-connection", "prod"])
        self.assertEqual(by_connection.remote_command, "probe-connection")
        self.assertEqual(by_connection.name, "prod")

    def test_remote_probe_connection_uses_configured_connection(self):
        from pyherdr.cli import run_remote
        from pyherdr.config import Config, ConnectionConfig

        args = build_parser().parse_args(["remote", "probe-connection", "prod"])
        config = Config(connections={"prod": ConnectionConfig(host="prod.example.com", user="ops")})

        stdout = StringIO()
        with (
            patch("pyherdr.cli.load_config", return_value=config),
            patch(
                "pyherdr.cli.probe_connection",
                return_value={
                    "type": "remote_probe",
                    "connection": "prod",
                    "host": "prod.example.com",
                    "target": "ops@prod.example.com",
                    "ok": True,
                },
            ) as probe,
            redirect_stdout(stdout),
        ):
            exit_code = run_remote(args)

        self.assertEqual(exit_code, 0)
        probe.assert_called_once_with("prod", config.connections["prod"])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["connection"], "prod")
        self.assertTrue(payload["ok"])

    def test_profile_probe_runs_unique_profile_connections(self):
        from pyherdr.cli import run_profile
        from pyherdr.config import Config, ConnectionConfig, ProfileConfig, ProfilePaneConfig

        args = build_parser().parse_args(["profile", "probe", "ops"])
        config = Config(
            connections={
                "prod": ConnectionConfig(host="prod.example.com", user="ops"),
                "logs": ConnectionConfig(host="logs.example.com", user="ops"),
            },
            profiles={
                "ops": ProfileConfig(
                    panes=[
                        ProfilePaneConfig(name="api", connection="prod"),
                        ProfilePaneConfig(name="api-2", connection="prod"),
                        ProfilePaneConfig(name="logs", connection="logs"),
                        ProfilePaneConfig(name="local", command="pwsh"),
                    ]
                )
            },
        )

        def fake_probe(name, connection):
            return {"type": "remote_probe", "connection": name, "host": connection.host, "ok": name != "logs"}

        stdout = StringIO()
        with (
            patch("pyherdr.cli.load_config", return_value=config),
            patch("pyherdr.cli.probe_connection", side_effect=fake_probe) as probe,
            redirect_stdout(stdout),
        ):
            exit_code = run_profile(args)

        self.assertEqual(exit_code, 1)
        self.assertEqual([call.args[0] for call in probe.call_args_list], ["prod", "logs"])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["type"], "profile_probe")
        self.assertEqual(payload["profile"], "ops")
        self.assertFalse(payload["ok"])
        self.assertEqual([result["connection"] for result in payload["results"]], ["prod", "logs"])

    def test_profile_plan_can_include_probe_results(self):
        from pyherdr.cli import run_profile
        from pyherdr.config import Config, ConnectionConfig, ProfileConfig, ProfilePaneConfig

        args = build_parser().parse_args(["profile", "plan", "ops", "--probe"])
        config = Config(
            connections={"prod": ConnectionConfig(host="prod.example.com", user="ops")},
            profiles={"ops": ProfileConfig(panes=[ProfilePaneConfig(name="api", connection="prod")])},
        )

        stdout = StringIO()
        with (
            patch("pyherdr.cli.load_config", return_value=config),
            patch(
                "pyherdr.cli.probe_connection",
                return_value={"type": "remote_probe", "connection": "prod", "host": "prod.example.com", "ok": True},
            ) as probe,
            redirect_stdout(stdout),
        ):
            exit_code = run_profile(args)

        self.assertEqual(exit_code, 0)
        probe.assert_called_once_with("prod", config.connections["prod"])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["type"], "profile_plan")
        self.assertTrue(payload["probe_ok"])
        self.assertEqual(payload["probe_results"][0]["connection"], "prod")

    def test_plugin_validate_parses_manifest_path(self):
        args = build_parser().parse_args(["plugin", "validate", "plugin.json"])

        self.assertEqual(args.command, "plugin")
        self.assertEqual(args.plugin_command, "validate")
        self.assertEqual(args.manifest, "plugin.json")

    def test_plugin_validate_accepts_detector_test_input(self):
        args = build_parser().parse_args(["plugin", "validate", "plugin.json", "--test-input", "APPROVE"])

        self.assertEqual(args.test_input, "APPROVE")

    def test_plugin_validate_accepts_launcher_listing(self):
        args = build_parser().parse_args(["plugin", "validate", "plugin.json", "--list-launchers"])

        self.assertTrue(args.list_launchers)

    def test_plugin_validate_accepts_theme_listing(self):
        args = build_parser().parse_args(["plugin", "validate", "plugin.json", "--list-themes"])

        self.assertTrue(args.list_themes)

    def test_plugin_validate_accepts_exporter_listing(self):
        args = build_parser().parse_args(["plugin", "validate", "plugin.json", "--list-exporters"])

        self.assertTrue(args.list_exporters)

    def test_plugin_export_parses_manifest_recording_and_output(self):
        args = build_parser().parse_args(
            ["plugin", "export", "plugin.json", "recording.json", "--output", "recording.txt", "--exporter", "text"]
        )

        self.assertEqual(args.command, "plugin")
        self.assertEqual(args.plugin_command, "export")
        self.assertEqual(args.manifest, "plugin.json")
        self.assertEqual(args.recording, "recording.json")
        self.assertEqual(args.output, "recording.txt")
        self.assertEqual(args.exporter, "text")

    def test_plugin_validate_runs_detector_smoke_test(self):
        import tempfile

        from pyherdr.cli import run_plugin

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "detector.py").write_text(
                "def detect(content):\n"
                "    return {'state': 'blocked', 'visible_blocker': True} if 'APPROVE' in content else 'idle'\n",
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
                    }
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args(["plugin", "validate", str(manifest), "--test-input", "APPROVE"])
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = run_plugin(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["detector_test"]["state"], "blocked")
        self.assertTrue(payload["detector_test"]["visible_blocker"])
        self.assertEqual(payload["safety"]["execution"], "in_process")
        self.assertFalse(payload["safety"]["isolated"])
        self.assertIn("same Python process", payload["safety"]["policy"])

    def test_plugin_validate_lists_launcher_plugin_records(self):
        import tempfile

        from pyherdr.cli import run_plugin

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "launcher.py").write_text(
                "def launchers():\n"
                "    return [{'id': 'ops-shell', 'label': 'Ops Shell', 'command': 'ssh ops@example.com'}]\n",
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
            args = build_parser().parse_args(["plugin", "validate", str(manifest), "--list-launchers"])
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = run_plugin(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["launchers"][0]["id"], "ops-shell")
        self.assertEqual(payload["launchers"][0]["command"], "ssh ops@example.com")

    def test_plugin_validate_lists_theme_plugin_records(self):
        import tempfile

        from pyherdr.cli import run_plugin

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "theme.py").write_text(
                "def themes():\n"
                "    return {'ops-dark': {\n"
                "        'accent': '#00ffff', 'panel_bg': '#101820', 'surface0': '#17232d',\n"
                "        'surface1': '#20313d', 'surface_dim': '#0b1117', 'overlay0': '#5d7788',\n"
                "        'overlay1': '#7894a7', 'text': '#e8f7ff', 'subtext0': '#a8c4d4',\n"
                "        'mauve': '#c4a7ff', 'green': '#70e08d', 'yellow': '#ffd166',\n"
                "        'red': '#ff6b8a', 'blue': '#5abfff', 'teal': '#2dd4bf', 'peach': '#ffb86b',\n"
                "    }}\n",
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
            args = build_parser().parse_args(["plugin", "validate", str(manifest), "--list-themes"])
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = run_plugin(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["themes"][0]["name"], "ops-dark")
        self.assertEqual(payload["themes"][0]["palette"]["accent"], "#00ffff")

    def test_plugin_validate_lists_exporter_plugin_records(self):
        import tempfile

        from pyherdr.cli import run_plugin

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "exporter.py").write_text(
                "def exporters():\n"
                "    return [{'id': 'text', 'label': 'Plain text', 'extension': '.txt'}]\n"
                "\n"
                "def export(recording, output, exporter_id=''):\n"
                "    output.write_text('unused', encoding='utf-8')\n",
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
            args = build_parser().parse_args(["plugin", "validate", str(manifest), "--list-exporters"])
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = run_plugin(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["exporters"][0]["id"], "text")
        self.assertEqual(payload["exporters"][0]["extension"], ".txt")

    def test_plugin_export_writes_recording_through_exporter(self):
        import tempfile

        from pyherdr.cli import run_plugin

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            recording = root / "recording.json"
            recording.write_text(
                json.dumps(
                    {
                        "type": "session_recording",
                        "workspaces": [{"tabs": [{"panes": [{"title": "api"}, {"title": "logs"}]}]}],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "recording.txt"
            args = build_parser().parse_args(
                ["plugin", "export", str(manifest), str(recording), "--output", str(output), "--exporter", "text"]
            )
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = run_plugin(args)
            exported_text = output.read_text(encoding="utf-8")

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["exporter"], "text")
        self.assertEqual(payload["pane_count"], 2)
        self.assertEqual(exported_text, "api\nlogs")

    def test_demo_screenshot_rejects_unknown_view_before_rendering(self):
        with self.assertRaises(ValueError):
            render_demo_screenshot(Path("unused.svg"), view="missing")


if __name__ == "__main__":
    unittest.main()
