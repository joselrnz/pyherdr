# Changelog

All notable user-facing changes to PyHerdr are documented here.

PyHerdr is still alpha software. Entries focus on behavior users can install,
run, configure, or rely on, not internal porting status.

## Unreleased

### Added

- Public docs decision: README plus focused `docs/*.md` pages are the canonical
  docs surface until a generated docs site is justified.
- Scripted `pyherdr demo-gif` command for repeatable animated release media
  generated from deterministic PyHerdr demo state.
- Balanced README comparison for tmux, Zellij, and cmux-class agent terminals.
- Clear package metadata for PyPI, including OS compatibility, Python support,
  project links, and typed package marker.

## 0.0.4 - 2026-06-13

### Added

- Terminal-native Textual UI with workspaces, tabs, split panes, mouse support,
  command palette, theme switching, and detachable sessions.
- Agent-aware workflows: status detection, attention navigation, workflow audit
  events, workflow graph export, and resource monitoring.
- Terminal automation commands for pane capture, session recording, replay,
  debug bundles, fan-out, scheduled commands, and workspace search.
- Startup profiles for repeatable local and SSH pane layouts, reusable
  connections, workflows, health checks, and profile attach/stop commands.
- Plugin foundations for detector, launcher, theme, and recording exporter
  manifests.

### Changed

- Terminal input and refresh paths now avoid high-frequency workflow logging and
  keep typing responsive while visible panes update from output changes.
- Pane rendering preserves styled terminal cells, scrollback position, cursor
  visibility, alt-screen/mouse-reporting metadata, and bottom-follow behavior in
  split layouts.
- Sidebar, tab bar, pane separator, and workspace picker surfaces now expose
  more of the current workspace, agent, and repository context.

### Security

- Plugin manifests now declare the current `in_process` execution boundary.
  Plugins are trusted local Python code; subprocess isolation is not active yet.
