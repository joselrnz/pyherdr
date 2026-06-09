# PyHerdr Architecture

PyHerdr is being restructured as a Python-first port, not a pile of scripts.
The target architecture is layered and validation-heavy.

## Current Formal Tree

```text
pyherdr/
├── contracts/          # Pydantic API boundary schemas
│   ├── __init__.py
│   └── api.py
├── domain/             # Pydantic domain models and enums
│   ├── __init__.py
│   ├── models.py
│   └── status.py
├── api.py              # Request dispatcher
├── cli.py              # CLI adapter
├── detector.py         # Agent status heuristics
├── gui.py              # Tkinter dashboard
├── models.py           # Compatibility exports for domain models
├── platform_support.py # Cross-platform runtime paths/process flags
├── runtime/            # PTY terminal engine + legacy GUI command runner
│   ├── __init__.py
│   ├── command_runner.py # Legacy pipe-based runner used by the GUI
│   ├── keys.py         # Key-name to byte-sequence encoding
│   ├── pty_backend.py  # Cross-platform PTY (stdlib pty / pywinpty ConPTY)
│   ├── screen.py       # pyte screen model with scrollback
│   └── session.py      # TerminalSession + TerminalManager
├── server.py           # Python server process and JSON socket transport
└── store.py            # Pydantic JSON persistence
```

## Target Tree

```text
pyherdr/
├── app/                # Use-case services: workspace, tab, pane, agents
├── cli/                # CLI command groups
├── contracts/          # Pydantic API and persistence schemas
├── domain/             # Pydantic models, enums, value objects
├── infrastructure/     # Filesystem, platform, config, logging
├── integrations/       # Agent integration installers and adapters
├── presentation/       # TUI/GUI renderers
├── runtime/            # PTY/process/session runtime
├── server/             # Server/client transport and lifecycle
└── tools/              # Porting/inventory developer tooling
```

The current flat modules are compatibility wrappers or transitional modules.
New code should go into the target package area first, then the old flat import
path can re-export it until callers are migrated.

## Development Rules

- Use Pydantic v2 `BaseModel` for domain and API boundary objects.
- Use `StrEnum` for every semantic enum and give every enum a class docstring.
- Use `Field(default_factory=...)` for mutable defaults.
- Use `field_validator` or `model_validator` for normalization and invariants.
- Keep entity methods on entity classes when behavior belongs to the model.
- Use private helpers for normalization and low-level implementation details.
- Use `@property` plus setters only when callers need a Pythonic access pattern.
- Add docstrings to public classes, public methods, and non-obvious private helpers.
- Keep transport contracts separate from domain models.
- Preserve compatibility wrappers only temporarily and keep them thin.
- Add tests before adding or moving behavior.

## Pydantic Conventions

Domain models use:

```python
model_config = ConfigDict(validate_assignment=True, extra="forbid")
```

This means:

- assignments are validated after construction
- unknown fields are rejected
- JSON persistence is generated through `model_dump(mode="json")`
- loading uses `model_validate(...)`

## Current Priority

The next structural move is to split runtime/server modules into:

```text
runtime/processes.py
runtime/terminal.py
runtime/buffer.py
server/lifecycle.py
server/transport.py
server/client.py
```

That should happen alongside the PTY/terminal backend so the tree reflects real
runtime behavior rather than empty folders.
