<div align="center">

<!-- Banner: PNG via absolute raw URL so it renders on GitHub AND PyPI (relative paths / raw SVG don't render on PyPI). -->
<img src="https://raw.githubusercontent.com/joselrnz/pyherdr/main/assets/banner.png" alt="PyHerdr — herd your terminals · multi-agent multiplexer" width="820">

A terminal multiplexer for AI coding agents — a pure-Python port of herdr.

[![PyPI](https://img.shields.io/badge/pypi-v0.0.4-3775A9.svg)](https://pypi.org/project/pyherdr/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Lint: ruff](https://img.shields.io/badge/lint-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Types: mypy](https://img.shields.io/badge/types-mypy-blue.svg)](https://mypy-lang.org/)

</div>

---

PyHerdr runs many shells and AI coding agents side by side in one terminal —
workspaces, tabs, and split panes, each a real pseudo-terminal — with live
agent-status tracking from pane output and explicit reports, surfaced in a
mouse-and-keyboard [Textual](https://textual.textualize.io/) UI. A
token-authenticated background server owns the processes, so you can detach and
reattach without losing a session.

## ✨ Features

- **Workspaces · tabs · panes** — split panes in a binary tree (side-by-side or
  stacked), zoom, resize by dragging the divider, drag-free keyboard navigation.
- **Real terminals** — every pane is a live PTY (ConPTY on Windows via
  `pywinpty`, the stdlib `pty` on macOS/Linux) with scrollback.
- **Mouse *and* keyboard** — click tabs/panes, right-click for context menus, a
  clickable bottom action bar, plus a tmux-style `ctrl+b` prefix for everything.
- **Command palette** (`ctrl+b :`) — filter and run any action or your own
  configured commands.
- **Agent status** — working / blocked / done / idle rollups from rendered/read
  pane output and explicit reports, surfaced in the sidebar and tab bar.
- **Workflow audit log** — record events, inspect recent workflow details, and
  inspect a cycle-aware terminal call graph, plus export JSON, Mermaid source, or a rendered SVG graph.
- **📊 Resource monitor** — right-click a pane or workspace → *resource usage*,
  or open *Resource monitor* — a live task-manager of CPU% + RAM per process,
  biggest-first, for one pane, a whole workspace, or every session.
- **Themes** — Ocean Blue by default, plus many built-ins (Catppuccin, Tokyo
  Night, Gruvbox, One Dark, Solarized, Rosé Pine, Kanagawa, …) with live theme +
  accent switching.
- **Detach / reattach** — the background server keeps panes running; reopen the
  TUI to re-attach. Named sessions via `PYHERDR_SESSION`.
- **Client / server** — newline-delimited JSON over a token-authed local socket;
  a full CLI/API mirrors the UI. Plus cron-scheduled pane commands and git
  worktree helpers.

## Glossary

- **Fan-out:** send one command or text input to several panes at once. PyHerdr
  previews the target panes first, then sends only after explicit confirmation.
- **Pane:** one live terminal inside the TUI. A pane can run a shell, a test
  command, or an AI agent.
- **Workspace:** a project folder plus its tabs and panes.
- **TUI:** terminal user interface. PyHerdr's main UI runs inside a terminal
  rather than a native desktop window.
- **PTY:** pseudo-terminal. This is what makes each pane behave like a real
  interactive terminal.
- **Mega plan:** the internal roadmap that tracks larger product goals and
  implementation chunks.
- **WS / worksite:** a numbered roadmap task, such as `WS-122`. It is not a
  website; it means "worksite" in the plan.
- **Lane:** a group of related worksites in the mega plan, such as UI polish,
  multiplexing, workflow automation, or plugin work.

## 📦 Install

```bash
pip install pyherdr
```

Requires **Python 3.11+**. Runtime deps install automatically: `pydantic`,
`pyte`, `textual`, `psutil`, and `pywinpty` (Windows only).

## 🚀 Quick start

```bash
pyherdr tui        # launch the terminal UI
```

It starts the background server if needed, opens a workspace with a shell, and
drops you into the UI. From a source checkout, use `python -m pyherdr tui`
instead. Running bare `pyherdr` opens the legacy desktop dashboard.

## 🖥️ User Interface Layout

PyHerdr organizes your workspace into a clean, mouse-supported dashboard in your terminal:

```text
┌────────────────────────────────────────────────────────────┐
│ workspace: backend    ~/code/api    [main]                 │
├────────────────────────────────┬───────────────────────────┤
│ SPACES                         │ 1:server  2:tests   [+]   │
│   backend       running        │ +-------+-------+         │
│   frontend      idle           │ |1-1    |1-2    |         │
│                                │ |$ _    |logs   |         │
│ AGENTS                         │ |shell  |tests  |         │
│   codex    api       working   │ +-------+-------+         │
│   claude   frontend  idle      │                           │
├────────────────────────────────┴───────────────────────────┤
│ ? help    : palette    + tab    theme    detach    quit    │
└────────────────────────────────────────────────────────────┘
```

- **Sidebar (Left):** Manages active workspaces and shows agent status spinners. CPU/RAM is available in the Resource monitor.
- **Terminal Workspace (Right):** Houses your tabs and split terminal panes (stacked or side-by-side) running live processes.
- **Action Bar (Bottom):** Clickable button hotkeys to trigger standard actions without memorizing keyboard prefix chords.

### Reproduce the TUI screenshot

The screenshot-style demos are generated by the real Textual `PyHerdrTui`
renderer with a deterministic demo client. That means the chrome, layout,
themes, split panes, sidebar, tab bar, and footer are real UI output. The pane
text is seeded demo data; this command does not launch live agents.

```bash
python -m pyherdr demo-screenshot --output pyherdr-demo.svg
python -m pyherdr demo-screenshot --view workflow --output pyherdr-workflow.svg
python -m pyherdr demo-screenshot --view fanout --output pyherdr-fanout.svg
```

Open the SVG in a browser to inspect it. To test the live product with real PTY
panes and the background server, run:

```bash
python -m pyherdr tui
```

## ⌨️ Keybindings

Keys go to the focused pane. Press the **prefix `ctrl+b`**, then an action key:

| | Key | Action |
|---|---|---|
| **Panes** | `v` / `-` | split right / down |
| | `h` `j` `k` `l` | focus left / down / up / right |
| | `z` · `r` | zoom · resize mode (then `h/l/j/k`, `esc`) |
| | `m` · `x` | pane menu · close pane |
| | `pgup` / `pgdn` | scroll the pane's scrollback |
| **Tabs** | `c` · `n`/`p` · `1`–`9` | new · next/prev · jump to N |
| | `<` / `>` · `T` · `X` | move left/right · rename · close |
| **Workspaces** | `N` · `w` · `{` / `}` | new (folder picker) · next · move up/down |
| **Global** | `:` · `g` · `s` | command palette · jump to pane · theme |
| | `F` | command fan-out picker and preview |
| | `d` · `?` · `q` | detach · help · quit |

**Mouse:** click tabs/panes, drag a divider to resize, right-click panes, tabs,
or workspace rows for context menus (including *resource usage*). The bottom **action bar** has clickable
buttons for help, palette, new tab, split, terminal, stats, theme, detach, quit.
The new-workspace folder picker starts from the active workspace and includes
quick jumps for the workspace root, git repo root, process cwd, and home.

## 🧰 CLI

The UI is a client; everything it does is scriptable:

```bash
pyherdr status                         # server + session status
pyherdr workspace create --label api --cwd ~/code
pyherdr tab create --label tests
pyherdr pane create --title logs
pyherdr pane start 1-1 python -i
pyherdr pane send-text 1-1 "print('hi')\n"
pyherdr pane get 1-1                    # pane metadata incl. command + agent status
pyherdr pane fanout --target workspace:main -- pytest -q     # dry-run preview
pyherdr pane fanout --all --execute --no-enter -- git status  # send to every pane
pyherdr workflow event validation.ok --worksite WS-121 --message "tests passed"
pyherdr workflow graph --format mermaid  # workflow/call-flow graph export
pyherdr workflow graph --format svg --output workflow.svg  # browser-quality call graph
pyherdr schedule add --cron "*/5 * * * *" --pane 1-1 git fetch
pyherdr server stop
```

In the TUI, `ctrl+b` then `F` opens the command fan-out picker. Pick a target
group, type a command, press enter to preview resolved panes, then send.
Destructive-looking multi-pane commands are blocked unless the preview is
explicitly confirmed (`--confirm-risky` in the CLI; the TUI send button confirms
after preview).

The TUI workflow view shows a compact terminal call graph with response/cycle
markers. Mermaid output is source text for Mermaid-compatible renderers. For a
browser-quality diagram, export SVG and open it in a browser.

## 🗂️ Configuration & state

- Session state: `.pyherdr/session.json` (override with `PYHERDR_STATE_PATH`).
- Server runtime metadata: `.pyherdr/server.json` (override with `PYHERDR_RUNTIME_DIR`).
- Default shell: `PYHERDR_SHELL`, or `terminal.default_shell` in config; extra
  env injected into every pane via `terminal.env`.
- Named sessions: `PYHERDR_SESSION=<name>` isolates state + server per name.
- Workflow audit log: `.pyherdr/workflow.jsonl`; obvious tokens/secrets are
  redacted before events are stored.

The `.pyherdr/` folder holds the auth token and is git-ignored — never commit it.

## 🛠️ Development

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1   |   macOS/Linux:  source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Quality gate (all must pass — CI enforces the same):

```bash
python -m ruff check pyherdr tools tests
python -m mypy
python -m unittest discover -s tests
```

A pure-Python port of the Rust project herdr —
see [`ARCHITECTURE.md`](ARCHITECTURE.md) for the package structure.

## 🙏 Attribution & license

PyHerdr is a Python port/fork of **herdr**, released under the
**GNU AGPL-3.0-or-later** — the same copyleft terms. See [`LICENSE`](LICENSE) and
[`NOTICE`](NOTICE) for the original project's attribution.
