import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from pyherdr.cli import main
from pyherdr.worksites import (
    FORBIDDEN_PUBLIC_ROADMAP_TERMS,
    check_worksite_tracking,
    parse_worksites,
    public_roadmap_markdown,
    worksite_summary,
)

PLAN_SAMPLE = """
### WS-001 Done Thing
- [x] Outcome: completed work.
- Scope: tests.
- Owner: Codex.
- Linked PR: commit abc123.
- Validation: done.

### WS-002 Active Thing
- [ ] Outcome: active work.
- Scope: docs.
- Status: active.
- Owner: Cloud.
- Linked PR: https://github.com/example/repo/pull/2
- Validation: tracked.

### WS-003 Open Thing
- [ ] Outcome: future work.
- Scope: cli.
- Validation: later.
""".strip()


class WorksiteTrackerTests(unittest.TestCase):
    def test_parse_worksites_derives_status_and_metadata(self):
        worksites = parse_worksites(PLAN_SAMPLE)

        self.assertEqual([worksite.id for worksite in worksites], ["WS-001", "WS-002", "WS-003"])
        self.assertEqual(worksites[0].status, "done")
        self.assertEqual(worksites[1].status, "active")
        self.assertEqual(worksites[1].owner, "Cloud.")
        self.assertEqual(worksites[1].linked_pr, "https://github.com/example/repo/pull/2")
        self.assertEqual(worksites[2].status, "open")

    def test_active_worksite_requires_owner_and_link(self):
        plan = """
### WS-010 Active Missing Metadata
- [ ] Outcome: work in progress.
- Status: active.
- Validation: tracked.
""".strip()

        issues = check_worksite_tracking(parse_worksites(plan))

        self.assertEqual(
            [issue.message for issue in issues],
            ["active worksite is missing Owner", "active worksite is missing Linked PR"],
        )
        self.assertEqual({issue.worksite_id for issue in issues}, {"WS-010"})

    def test_summary_counts_statuses(self):
        summary = worksite_summary(parse_worksites(PLAN_SAMPLE))

        self.assertEqual(
            summary,
            {
                "total": 3,
                "done": 1,
                "active": 1,
                "blocked": 0,
                "open": 1,
                "unknown": 0,
                "issues": 0,
            },
        )

    def test_roadmap_check_cli_outputs_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "MEGA_PLAN.md"
            path.write_text(PLAN_SAMPLE, encoding="utf-8")
            out = StringIO()

            with redirect_stdout(out):
                exit_code = main(["roadmap", "check", "--plan", str(path), "--json"])

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["total"], 3)
        self.assertEqual(payload["summary"]["active"], 1)
        self.assertEqual(payload["issues"], [])
        self.assertEqual(payload["worksites"][1]["id"], "WS-002")

    def test_public_roadmap_is_sanitized_subset(self):
        plan = """
### WS-025 Sidebar Fidelity
- [x] Outcome: sidebar shows workspace and agent context richly.
- Scope: sidebar renderer.
- Validation: covered.

### WS-036 URL Action
- [ ] Outcome: ctrl-click URL opens or copies according to config.
- Scope: URL detection, mouse input.
- Validation: fixture identifies links.

### WS-102 Public Roadmap
- [ ] Outcome: public roadmap is a sanitized subset of MEGA_PLAN.md.
- Scope: README/docs.
- Validation: no local-only notes leak.

### WS-110 Documentation Truth Pass
- [x] Outcome: public docs do not promise missing behavior.
- Scope: README/docs/PyPI.
- Validation: feature claims map to completed work.
""".strip()

        public = public_roadmap_markdown(parse_worksites(plan))

        self.assertIn("# PyHerdr Roadmap", public)
        self.assertIn("Sidebar Fidelity", public)
        self.assertIn("URL Action", public)
        self.assertNotIn("WS-025", public)
        self.assertNotIn("MEGA_PLAN", public)
        for term in FORBIDDEN_PUBLIC_ROADMAP_TERMS:
            self.assertNotIn(term.lower(), public.lower())

    def test_roadmap_public_cli_writes_sanitized_doc(self):
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp) / "MEGA_PLAN.md"
            output = Path(temp) / "roadmap.md"
            plan.write_text(PLAN_SAMPLE, encoding="utf-8")
            out = StringIO()

            with redirect_stdout(out):
                exit_code = main(["roadmap", "public", "--plan", str(plan), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(out.getvalue().strip(), str(output))
            public = output.read_text(encoding="utf-8")

        self.assertIn("# PyHerdr Roadmap", public)
        self.assertNotIn("WS-001", public)
