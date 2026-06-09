import unittest

from pyherdr.detector import detect_agent_status
from pyherdr.models import AgentStatus


class DetectorTests(unittest.TestCase):
    def test_blocked_wins_over_working(self):
        status = detect_agent_status("running tests\napproval required: install dependency?")
        self.assertEqual(status, AgentStatus.BLOCKED)

    def test_detects_done(self):
        self.assertEqual(detect_agent_status("build succeeded"), AgentStatus.DONE)

    def test_empty_output_is_unknown(self):
        self.assertEqual(detect_agent_status(""), AgentStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
