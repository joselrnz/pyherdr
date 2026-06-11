# Web Dashboard Decision

Status: initial decision and threat model for WS-060 through WS-062.

## MVP Scope

The dashboard MVP is an observer-first view: workspace list, tabs, panes, agent
statuses, recent output summaries, workflow graph, and recording/debug artifact
links. Browser work must not block terminal work; every dashboard capability
should sit on top of existing API helpers first.

## Out Of Scope

The first dashboard pass does not replace the TUI, does not own terminal
rendering, and does not expose remote network access by default. Mutating actions
can arrive later after the read-only live view is stable.

## Dashboard Auth

The local token remains the first auth boundary. Remote bind is opt-in. Binding
outside localhost must require explicit configuration, clear CLI output, and a
threat-model note in the docs. Dashboard auth must never print the server token
or include it in debug bundles.

## Live Updates

Live updates start as an API event snapshot through `events.snapshot`. The event
shape covers workspace snapshots and agent status changes so a fake or browser
client can update without polling the full state forever. Later transports may
upgrade this to SSE or WebSocket, but the event contract should stay stable.

## Security Notes

Read-only dashboard mode is the default. Mutating dashboard mode should require
a separate setting and should reuse fan-out risk confirmation for multi-pane or
destructive commands.
