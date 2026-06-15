import json
import tempfile
import unittest
from pathlib import Path

from pyherdr.performance import (
    build_baseline,
    collect_baseline,
    render_baseline_report,
    write_baseline,
)


def _fake_request(payload):
    if payload["method"] == "stats.get":
        return {
            "id": payload["id"],
            "result": {
                "type": "stats",
                "available": True,
                "stats": {
                    "pane-1": {
                        "pid": 100,
                        "cpu_percent": 12.5,
                        "rss_bytes": 64 * 1024 * 1024,
                        "num_procs": 2,
                        "procs": [],
                        "warnings": [],
                    },
                    "pane-2": {
                        "pid": 200,
                        "cpu_percent": 3.0,
                        "rss_bytes": 32 * 1024 * 1024,
                        "num_procs": 1,
                        "procs": [],
                        "warnings": ["child process denied"],
                    },
                },
            },
        }
    if payload["method"] == "state.get":
        return {
            "id": payload["id"],
            "result": {
                "type": "state",
                "state": {
                    "workspaces": [
                        {
                            "label": "main",
                            "tabs": [
                                {
                                    "label": "agents",
                                    "panes": [
                                        {"pane_id": "pane-1", "title": "codex"},
                                        {"pane_id": "pane-2", "title": "tests"},
                                    ],
                                }
                            ],
                        }
                    ]
                },
            },
        }
    raise AssertionError(f"unexpected method {payload['method']}")


class PerformanceBaselineTests(unittest.TestCase):
    def test_collect_baseline_summarizes_cpu_ram_and_hot_panes(self):
        ticks = iter([0.0, 0.0, 0.0, 0.0])

        baseline = collect_baseline(
            _fake_request,
            scenario="unit",
            duration_seconds=0,
            interval_seconds=1,
            clock=lambda: next(ticks),
            sleep=lambda _seconds: None,
        )

        self.assertEqual(baseline["type"], "performance_baseline")
        self.assertEqual(baseline["scenario"], "unit")
        self.assertEqual(baseline["summary"]["samples"], 1)
        self.assertEqual(baseline["summary"]["cpu_percent"]["avg"], 15.5)
        self.assertEqual(baseline["summary"]["rss_bytes"]["max"], 96 * 1024 * 1024)
        self.assertEqual(baseline["summary"]["warning_count"], 1)
        self.assertEqual(baseline["samples"][0]["top_panes"][0]["label"], "main · agents · codex")

    def test_render_baseline_report_contains_dashboard_rows(self):
        baseline = build_baseline(
            "report",
            [
                {
                    "total_cpu_percent": 5.0,
                    "total_rss_bytes": 10 * 1024 * 1024,
                    "process_count": 2,
                    "pane_count": 1,
                    "warnings": [],
                    "top_panes": [
                        {
                            "label": "main · agents · codex",
                            "cpu_percent": 5.0,
                            "rss_bytes": 10 * 1024 * 1024,
                            "num_procs": 2,
                        }
                    ],
                }
            ],
            duration_seconds=0,
            interval_seconds=1,
        )

        report = render_baseline_report(baseline)

        self.assertIn("performance baseline · report", report)
        self.assertIn("CPU", report)
        self.assertIn("RAM", report)
        self.assertIn("main · agents · codex", report)

    def test_write_baseline_creates_json_file(self):
        baseline = build_baseline("save", [], duration_seconds=0, interval_seconds=1)
        with tempfile.TemporaryDirectory() as temp:
            path = write_baseline(Path(temp) / "nested" / "baseline.json", baseline)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["scenario"], "save")


if __name__ == "__main__":
    unittest.main()
