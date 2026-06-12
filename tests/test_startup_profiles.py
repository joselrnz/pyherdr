import unittest

from pyherdr.config import (
    Config,
    ConnectionConfig,
    ProfileConfig,
    ProfilePaneConfig,
    WorkflowConfig,
    WorkflowStepConfig,
)
from pyherdr.startup_profiles import build_pane_command, plan_profile, validate_startup_config


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
                    panes=[ProfilePaneConfig(name="prod", connection="prod", command="uptime")],
                )
            },
            workflows={"health": WorkflowConfig(profile="ops", steps=[WorkflowStepConfig(pane="prod", send="uptime")])},
        )

        plan = plan_profile(config, "ops", workflow_name="health")

        self.assertEqual(plan["workspace"], "ops")
        self.assertEqual(plan["layout"], "main-left")
        self.assertEqual(plan["panes"][0]["command"], "ssh ops@prod.example.com uptime")
        self.assertEqual(plan["workflow"]["steps"][0]["pane"], "prod")


if __name__ == "__main__":
    unittest.main()
