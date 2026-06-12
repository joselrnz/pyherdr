import unittest

from pyherdr.detect import (
    Agent,
    AgentStatus,
    detector_catalog,
    detector_catalog_table,
    get_detector_catalog_entry,
)
from pyherdr.detect.agents import _DETECTORS


class DetectorCatalogTests(unittest.TestCase):
    def test_catalog_covers_registered_named_detectors(self):
        entries = detector_catalog()

        self.assertEqual(tuple(entry.agent for entry in entries), tuple(Agent))
        self.assertEqual({entry.agent for entry in entries}, set(_DETECTORS))
        for entry in entries:
            with self.subTest(agent=entry.agent):
                self.assertEqual(entry.agent_name, entry.agent.value)
                self.assertEqual(entry.source_module, "pyherdr.detect.agents")
                self.assertEqual(entry.detector_function, _DETECTORS[entry.agent].__name__)
                self.assertTrue(entry.herdr_source.startswith("src/detect/agents/"))
                self.assertEqual(entry.herdr_function, "detect")
                self.assertNotIn(AgentStatus.DONE, entry.statuses)
                self.assertNotIn(AgentStatus.UNKNOWN, entry.statuses)
                self.assertEqual({signal.status for signal in entry.signals}, set(entry.statuses))

    def test_codex_catalog_entry_exposes_confidence_and_metadata(self):
        entry = get_detector_catalog_entry(Agent.CODEX)

        self.assertEqual(entry.agent_name, "codex")
        self.assertEqual(entry.detector_function, "_detect_codex")
        self.assertEqual(entry.herdr_source, "src/detect/agents/codex.rs")
        self.assertEqual(entry.statuses, (AgentStatus.BLOCKED, AgentStatus.WORKING, AgentStatus.IDLE))
        self.assertEqual(
            entry.confidence_fields,
            ("skip_state_update", "visible_blocker", "visible_idle", "visible_working"),
        )
        self.assertEqual(entry.metadata["confidence_blocker"], "codex_has_visible_blocker")
        self.assertEqual(entry.metadata["confidence_idle"], "codex_has_prompt")
        self.assertEqual(entry.metadata["confidence_working"], "codex_has_visible_working")
        self.assertEqual(entry.metadata["skip_state_update"], "codex_is_transcript_viewer")

    def test_detector_catalog_table_is_api_friendly(self):
        [codex] = [row for row in detector_catalog_table() if row["agent"] == "codex"]

        self.assertEqual(codex["source_function"], "pyherdr.detect.agents._detect_codex")
        self.assertEqual(codex["statuses"], ["blocked", "working", "idle"])
        self.assertEqual(
            codex["confidence_fields"],
            ["skip_state_update", "visible_blocker", "visible_idle", "visible_working"],
        )
        self.assertIn(
            {
                "status": "blocked",
                "name": "strong_blocked",
                "description": "permission or confirmation prompt visible in the current Codex screen",
            },
            codex["signals"],
        )


if __name__ == "__main__":
    unittest.main()
