import unittest

from pyherdr.config import (
    Config,
    ConnectionConfig,
    ProfileConfig,
    ProfilePaneConfig,
    WorkflowConfig,
    WorkflowStepConfig,
)
from pyherdr.layout import Rect, TileLayout
from pyherdr.startup_profiles import build_pane_command, build_profile_layout, plan_profile, validate_startup_config


class StartupProfileTests(unittest.TestCase):
    def test_build_pane_command_generates_interactive_ssh_command(self):
        config = Config(connections={"prod": ConnectionConfig(host="prod.example.com", user="jose", port=2222)})
        pane = ProfilePaneConfig(name="prod", connection="prod")

        self.assertEqual(build_pane_command(config, pane), "ssh -p 2222 jose@prod.example.com")

    def test_build_pane_command_adds_key_and_remote_command(self):
        config = Config(connections={"logs": ConnectionConfig(host="logs.example.com", key="~/.ssh/logs")})
        pane = ProfilePaneConfig(name="logs", connection="logs", command="journalctl -f")

        self.assertEqual(build_pane_command(config, pane), "ssh -i '~/.ssh/logs' logs.example.com 'journalctl -f'")

    def test_validate_startup_config_catches_bad_references_and_passwords(self):
        config = Config(
            connections={"bad": ConnectionConfig(host="prod.example.com", password="secret")},
            profiles={
                "ops": ProfileConfig(
                    panes=[
                        ProfilePaneConfig(name="prod", connection="missing"),
                        ProfilePaneConfig(name="prod", command="uptime"),
                    ]
                )
            },
            workflows={
                "health": WorkflowConfig(profile="ops", steps=[WorkflowStepConfig(pane="ghost", send="uptime")])
            },
        )

        result = validate_startup_config(config)

        self.assertFalse(result.ok)
        self.assertIn("connection bad uses unsupported password storage", result.errors)
        self.assertIn("profile ops pane prod references missing connection missing", result.errors)
        self.assertIn("profile ops has duplicate pane name prod", result.errors)
        self.assertIn("workflow health step references missing pane ghost", result.errors)

    def test_plan_profile_expands_connection_references_without_duplication(self):
        config = Config(
            connections={"prod": ConnectionConfig(host="prod.example.com", user="ops")},
            profiles={
                "ops": ProfileConfig(
                    workspace="ops",
                    layout="main-left",
                    env={"APP_ENV": "prod", "REGION": "us"},
                    panes=[
                        ProfilePaneConfig(
                            name="prod",
                            connection="prod",
                            command="uptime",
                            env={"REGION": "eu"},
                            start_order=20,
                        ),
                        ProfilePaneConfig(name="local", command="pwsh", start_order=10),
                    ],
                )
            },
            workflows={"health": WorkflowConfig(profile="ops", steps=[WorkflowStepConfig(pane="prod", send="uptime")])},
        )

        plan = plan_profile(config, "ops", workflow_name="health")

        self.assertEqual(plan["workspace"], "ops")
        self.assertEqual(plan["layout"], "main-left")
        self.assertEqual(plan["panes"][0]["command"], "ssh ops@prod.example.com uptime")
        self.assertEqual(plan["panes"][0]["env"], {"APP_ENV": "prod", "REGION": "eu"})
        self.assertEqual(plan["panes"][1]["env"], {"APP_ENV": "prod", "REGION": "us"})
        self.assertEqual(plan["start_sequence"], ["local", "prod"])
        self.assertEqual(plan["workflow"]["steps"][0]["pane"], "prod")

    def test_build_profile_layout_uses_template_when_available(self):
        config = Config(
            profiles={
                "ops": ProfileConfig(
                    layout="main-left",
                    panes=[
                        ProfilePaneConfig(name="local", position="left"),
                        ProfilePaneConfig(name="logs", position="right-top"),
                        ProfilePaneConfig(name="db", position="right-bottom"),
                    ],
                )
            }
        )

        layout_data = build_profile_layout(config.profiles["ops"])
        layout = TileLayout.from_dict(layout_data)

        self.assertEqual(layout.pane_ids(), ["local", "logs", "db"])
        self.assertEqual(
            [(pane.pane_id, pane.rect) for pane in layout.panes(Rect(0, 0, 100, 40))],
            [
                ("local", Rect(0, 0, 65, 40)),
                ("logs", Rect(65, 0, 35, 20)),
                ("db", Rect(65, 20, 35, 20)),
            ],
        )

    def test_build_profile_layout_uses_position_hints_without_template(self):
        profile = ProfileConfig(
            panes=[
                ProfilePaneConfig(name="top", position="top"),
                ProfilePaneConfig(name="bottom", position="bottom"),
            ]
        )

        layout_data = build_profile_layout(profile)
        layout = TileLayout.from_dict(layout_data)

        self.assertEqual(
            [(pane.pane_id, pane.rect) for pane in layout.panes(Rect(0, 0, 80, 20))],
            [("top", Rect(0, 0, 80, 10)), ("bottom", Rect(0, 10, 80, 10))],
        )


if __name__ == "__main__":
    unittest.main()
