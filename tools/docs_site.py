"""Validate the current docs-site decision.

Usage:
    python -m tools.docs_site --check
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
DOCS_DIR = ROOT / "docs"
DECISION = DOCS_DIR / "site-decision.md"


def check_docs_site(root: Path = ROOT) -> list[str]:
    readme = root / "README.md"
    changelog = root / "CHANGELOG.md"
    docs_dir = root / "docs"
    decision = docs_dir / "site-decision.md"
    errors: list[str] = []

    if not readme.exists():
        errors.append("README.md is missing")
    else:
        readme_text = readme.read_text(encoding="utf-8")
        for heading in ("## 🚀 Quick start", "## How PyHerdr Compares", "## 🧰 CLI"):
            if heading not in readme_text:
                errors.append(f"README.md is missing {heading!r}")

    if not changelog.exists():
        errors.append("CHANGELOG.md is missing")
    else:
        changelog_text = changelog.read_text(encoding="utf-8")
        if "# Changelog" not in changelog_text or "## Unreleased" not in changelog_text:
            errors.append("CHANGELOG.md must include a public changelog structure")

    if not decision.exists():
        errors.append("docs/site-decision.md is missing")
    else:
        decision_text = decision.read_text(encoding="utf-8").lower()
        if "no separate generated docs site yet" not in decision_text:
            errors.append("docs/site-decision.md must state the docs-site decision")
        if "tools.docs_site --check" not in decision_text:
            errors.append("docs/site-decision.md must document the validation command")

    tracked_docs = sorted(path for path in docs_dir.glob("*.md") if path.name != "site-decision.md")
    if not tracked_docs:
        errors.append("docs/ must include at least one focused Markdown page")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate PyHerdr docs-site decision")
    parser.add_argument("--check", action="store_true", help="validate the current README/docs Markdown surface")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("only --check is supported until a generated docs site is chosen")

    errors = check_docs_site()
    if errors:
        for error in errors:
            print(f"docs-site check failed: {error}")
        return 1
    print("docs-site check passed: README.md + docs/*.md remain the canonical docs surface")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
