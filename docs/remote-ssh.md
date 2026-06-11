# Remote SSH Design

Status: initial design for WS-056 through WS-058.

## Process Ownership

Remote panes are owned by the local PyHerdr server, not by the TUI client. The
local server opens the SSH control path, starts the remote command, captures
output, and exposes the pane through the same API as local panes. The TUI remains
a renderer and input client.

The domain model marks remote panes with `remote_host` and `remote_cwd`. Local
panes leave those fields empty. API records expose `location`, `remote_host`,
`remote_cwd`, and `display_cwd` so CLI, TUI, and future web views can label
remote execution clearly.

## Reconnect

Reconnect is server-centered. If a TUI disconnects, the local server keeps the
SSH-backed pane alive. If the SSH session drops, the pane remains in state with
its last output, remote metadata, and a blocked or idle status. Future reconnect
work should attempt a fresh probe before reattaching.

## Probe Before Pane

`pyherdr remote probe HOST` is the prerequisite check. It verifies that SSH can
reach the host in batch mode and that `pyherdr --version` is available remotely.
Failure messages must be actionable and must not hide the underlying SSH error.

## Not In This Slice

This design does not start remote panes yet. WS-057 provides the probe, and
WS-058 provides remote metadata and display rules so the execution path can land
without changing the pane contract later.
