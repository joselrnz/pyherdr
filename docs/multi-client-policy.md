# Multi-Client Policy

Status: initial policy for WS-059.

## Default

PyHerdr should support many attached clients, but only one effective writer per
session action at a time. The server remains the source of truth and serializes
mutating API requests under its existing lock.

## Read-Only Clients

Read-only clients may call `state.get`, `events.snapshot`, `pane.read`,
`pane.capture`, `stats.get`, and replay/debug inspection commands. They must not
send pane input, resize panes, close tabs, or start commands.

## Single Writer

The default interactive TUI is a writer. Writer clients may mutate layout, focus,
tabs, panes, workspaces, and send terminal input. The server processes requests
in order so two clients cannot partially apply one mutation.

## Multi-Writer

Multi-writer use is allowed only by policy, not by accident. When more than one
writer is attached, user-facing clients should display that fact and avoid
silent focus stealing. Later work can add explicit leases, but the MVP policy is
serialized writes plus visible client count.

## Conflict Rules

Focus changes are last-write-wins. Pane input is ordered by arrival at the
server. Destructive operations should keep the same confirmation behavior used by
fan-out and future debug/export commands.
