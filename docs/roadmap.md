# PyHerdr Roadmap

This is a public, user-facing snapshot of where PyHerdr is headed.
It focuses on product capabilities instead of implementation trackers.

## Available Now

- **Sidebar Fidelity** — sidebar shows workspace and agent context richly.
- **Tab Bar Fidelity** — tab bar supports overflow, close, new, rename.
- **Toast System** — in-TUI toasts show attention and completion.
- **Event Refresh** — output refresh is event-driven and coalesced.
- **Scrollback Viewport** — scrollback has deterministic viewport state.
- **Copy Selection** — user can select and yank text.
- **Clipboard Backends** — OSC52 and fallback clipboard are abstracted.
- **Launcher Presets** — common agent commands launch from picker.
- **Jump To Attention** — one command focuses next blocked or done agent.
- **Layout Templates** — users can save and reuse pane layouts.
- **Headless Server** — PyHerdr can run without TUI.
- **Session Recording** — pane or session events can be recorded.
- **Replay Viewer** — recording can be replayed or inspected.
- **Plugin Manifest** — plugins have a schema.
- **Detector Plugin** — third-party detector can add agent state support.
- **Launcher Plugin** — third-party launcher can add agent commands.
- **Theme Plugin** — themes can be distributed outside core.
- **Exporter Plugin** — recordings can export through plugins.
- **Plugin Safety** — plugin execution boundary is explicit.
- **API Coverage** — API contracts have regression tests.
- **Detector Coverage** — agent detectors have transcript coverage.
- **Release Smoke** — release candidate can install and launch.
- **Daily Driver Scenario** — one scripted scenario exercises daily agent work.
- **Multiplexer Scenario** — one scenario proves multiplexer fundamentals.
- **Polished Agent UX Scenario** — one scenario proves polished agent UX.
- **Remote Scenario** — one scenario proves remote workspace story.
- **Headless Scenario** — one scenario proves CI/headless story.
- **Documentation Truth Pass** — public docs do not promise missing behavior.

## Next

- **Pane Border Fidelity** — focused/unfocused pane borders match mode state.
- **Pane Swap** — shifted direction keys swap panes.
- **Mode Enum** — mode state is centralized.
- **Bottom Bars** — prefix, navigate, copy, resize bars render from one system.
- **Theme Tokens** — all parity theme tokens exist.
- **Dialog Primitives** — modals share shell/header/actions helpers.
- **Onboarding** — first-run screen teaches minimum controls.
- **URL Action** — ctrl-click URL opens or copies according to config.
- **Agent Status History** — status transitions are persisted in memory and API.
- **Notification Backends** — toast, bell, terminal, and OS notifications share interface.
- **Workspace Metadata** — workspace cards show branch, dirty, ahead/behind.
- **Listening Ports** — workspace sidebar can show ports started by panes.
- **Project Config** — .pyherdr.toml or equivalent config controls project commands.
- **Issue Templates** — users can file useful bugs and feature requests.
- **Security Policy** — users know how to report token/security issues.
- **Plugin Scenario** — one scenario proves extension story.
- **Recovery Scenario** — one scenario proves resilience.

## Later

- **PR Status Provider** — PR status can be supplied without hard-coding one host.
- **Web Dashboard Decision** — dashboard MVP scope is written down.
- **Dashboard Auth** — dashboard auth has a threat model.
- **User Research Notes** — feedback from real usage becomes roadmap input.
- **Accessibility Pass** — UI works with reasonable contrast and keyboard-only flows.
- **Narrow Terminal Pass** — UI remains usable in small terminals.
- **Large Workspace Pass** — UI handles many workspaces/tabs/panes.
- **Performance Baseline** — CPU and memory baseline is known.
- **Memory Leak Pass** — long-running sessions do not grow unbounded.
- **Windows Terminal Pass** — Windows terminal workflows are tested.
- **macOS Terminal Pass** — macOS terminal workflows are tested.
- **Linux Terminal Pass** — Linux terminal workflows are tested.
- **Workflow Graph And Audit Log MVP** — users can open a visual workflow/call-flow view with a detailed event log.
