# Docs Site Decision

Status: no separate generated docs site yet.

PyHerdr's public docs surface is currently:

- `README.md` for install, quickstart, core usage, comparison, and config.
- `docs/*.md` for focused policy and architecture notes.
- `CHANGELOG.md` once public release notes land.

This avoids adding MkDocs, Sphinx, Docusaurus, or another docs dependency before
the README, changelog, and release checklist stabilize. The repo should add a
generated site only when documentation grows beyond what GitHub/PyPI README plus
focused Markdown pages can carry.

Validation command:

```powershell
.\.venv\Scripts\python.exe -m tools.docs_site --check
```

The check verifies that the README and tracked docs pages exist, that the README
still includes the quickstart and comparison sections, and that the project does
not advertise a generated docs-site command without updating this decision.
