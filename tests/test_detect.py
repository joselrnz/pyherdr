import unittest

from pyherdr.detect import (
    Agent,
    AgentStatus,
    detect,
    detect_state,
    identify_agent,
    identify_agent_in_command,
)

IDLE = AgentStatus.IDLE
WORKING = AgentStatus.WORKING
BLOCKED = AgentStatus.BLOCKED
UNKNOWN = AgentStatus.UNKNOWN


def claude_prompt_box(above: str) -> str:
    rule = "─" * 32
    return f"{above}\n{rule}\n❯ \n{rule}\n"


class IdentifyAgentTests(unittest.TestCase):
    def test_identifies_known_binaries(self):
        self.assertEqual(identify_agent("claude"), Agent.CLAUDE)
        self.assertEqual(identify_agent("claude.exe"), Agent.CLAUDE)
        self.assertEqual(identify_agent("cursor-agent"), Agent.CURSOR)
        self.assertEqual(identify_agent("Codex"), Agent.CODEX)

    def test_unknown_returns_none(self):
        self.assertIsNone(identify_agent("bash"))
        self.assertIsNone(identify_agent("python"))

    def test_identify_in_command_uses_basename(self):
        self.assertEqual(identify_agent_in_command("/usr/local/bin/codex --foo"), Agent.CODEX)
        self.assertEqual(identify_agent_in_command(r"C:\\tools\\claude.exe"), Agent.CLAUDE)
        self.assertIsNone(identify_agent_in_command("python -i"))

    def test_no_agent_is_unknown(self):
        self.assertEqual(detect_state(None, "anything"), UNKNOWN)


class SimpleAgentTests(unittest.TestCase):
    def test_pi(self):
        self.assertEqual(detect_state(Agent.PI, "Working..."), WORKING)
        self.assertEqual(detect_state(Agent.PI, "$ "), IDLE)

    def test_cline_defaults_to_working(self):
        self.assertEqual(detect_state(Agent.CLINE, "let cline use this tool"), BLOCKED)
        self.assertEqual(detect_state(Agent.CLINE, "Cline is ready for your message"), IDLE)
        self.assertEqual(detect_state(Agent.CLINE, "thinking"), WORKING)

    def test_gemini(self):
        self.assertEqual(detect_state(Agent.GEMINI, "Waiting for user confirmation"), BLOCKED)
        self.assertEqual(detect_state(Agent.GEMINI, "press esc to cancel"), WORKING)
        self.assertEqual(detect_state(Agent.GEMINI, "ready"), IDLE)

    def test_droid(self):
        self.assertEqual(detect_state(Agent.DROID, "EXECUTE\n> Yes, allow\nenter to select"), BLOCKED)
        self.assertEqual(detect_state(Agent.DROID, "⠋ Thinking...\nESC to stop"), WORKING)
        self.assertEqual(detect_state(Agent.DROID, "ready"), IDLE)

    def test_amp(self):
        blocked = "Run this command?\nApprove\nDeny with feedback\nWaiting for approval"
        self.assertEqual(detect_state(Agent.AMP, blocked), BLOCKED)
        self.assertEqual(detect_state(Agent.AMP, "Running tools... Esc to cancel"), WORKING)

    def test_grok(self):
        self.assertEqual(detect_state(Agent.GROK, "Yes, proceed\nNo, reject"), BLOCKED)
        self.assertEqual(detect_state(Agent.GROK, "⠋ Waiting… 1.8s"), WORKING)

    def test_hermes(self):
        blocked = "Dangerous command\nAllow once\nEnter to confirm"
        self.assertEqual(detect_state(Agent.HERMES, blocked), BLOCKED)
        self.assertEqual(detect_state(Agent.HERMES, "msg=interrupt"), WORKING)

    def test_github_copilot(self):
        self.assertEqual(detect_state(Agent.GITHUB_COPILOT, "esc to cancel\nenter to select"), BLOCKED)
        self.assertEqual(detect_state(Agent.GITHUB_COPILOT, "esc to cancel"), WORKING)

    def test_opencode_and_kilo(self):
        self.assertEqual(detect_state(Agent.OPENCODE, "△ Permission required"), BLOCKED)
        self.assertEqual(detect_state(Agent.OPENCODE, "press esc to interrupt"), WORKING)
        self.assertEqual(detect_state(Agent.KILO, "esc interrupt"), WORKING)

    def test_cursor(self):
        self.assertEqual(detect_state(Agent.CURSOR, "Waiting for approval"), BLOCKED)
        self.assertEqual(detect_state(Agent.CURSOR, "⬢ Generating something"), WORKING)
        self.assertEqual(detect_state(Agent.CURSOR, "ctrl+c to stop"), WORKING)

    def test_antigravity(self):
        blocked = "Requesting permission for:\nDo you want to proceed?"
        self.assertEqual(detect_state(Agent.ANTIGRAVITY, blocked), BLOCKED)
        self.assertEqual(detect_state(Agent.ANTIGRAVITY, "⠋ Thinking about it"), WORKING)

    def test_kiro(self):
        blocked = "This requires approval\nesc to close"
        self.assertEqual(detect_state(Agent.KIRO, blocked), BLOCKED)
        self.assertEqual(detect_state(Agent.KIRO, "Kiro is working"), WORKING)

    def test_qodercli(self):
        self.assertEqual(detect_state(Agent.QODERCLI, "Permission required"), BLOCKED)
        self.assertEqual(detect_state(Agent.QODERCLI, "loading (esc to cancel, ...)"), WORKING)
        self.assertEqual(detect_state(Agent.QODERCLI, "press esc again to rewind"), IDLE)

    def test_kimi(self):
        self.assertEqual(detect_state(Agent.KIMI, "🌕"), WORKING)
        blocked = "requesting approval\napprove once\nreject\n1/2/3/4 choose"
        self.assertEqual(detect_state(Agent.KIMI, blocked), BLOCKED)


class ClaudeTests(unittest.TestCase):
    def test_shell_still_running_is_working(self):
        content = claude_prompt_box("● Started.\n\n✻ Crunched for 7s · 1 shell still running")
        self.assertEqual(detect_state(Agent.CLAUDE, content), WORKING)

    def test_idle_prompt_box(self):
        self.assertEqual(detect_state(Agent.CLAUDE, claude_prompt_box("● Done.")), IDLE)

    def test_blocked_confirmation(self):
        content = "Do you want to proceed?\n❯ 1. Yes\n  2. No"
        detection = detect(Agent.CLAUDE, content)
        self.assertEqual(detection.state, BLOCKED)

    def test_esc_to_interrupt_is_working(self):
        content = claude_prompt_box("✻ Pondering… (esc to interrupt)")
        self.assertEqual(detect_state(Agent.CLAUDE, content), WORKING)


class CodexTests(unittest.TestCase):
    def test_working_status_marker(self):
        content = "• Ran git status --short\n  └ M src/detect.rs\n\n• Working (17s • esc to interrupt)\n\n› Implement"
        self.assertEqual(detect_state(Agent.CODEX, content), WORKING)

    def test_idle_prompt(self):
        self.assertEqual(detect_state(Agent.CODEX, "some output\n\n› "), IDLE)

    def test_strong_blocked(self):
        self.assertEqual(detect_state(Agent.CODEX, "allow command?"), BLOCKED)

    def test_visible_blocker_flag(self):
        detection = detect(Agent.CODEX, "press enter to confirm or esc to cancel")
        self.assertEqual(detection.state, BLOCKED)
        self.assertTrue(detection.visible_blocker)


if __name__ == "__main__":
    unittest.main()
