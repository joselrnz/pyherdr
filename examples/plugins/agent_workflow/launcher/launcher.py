def launchers():
    return [
        {
            "id": "walter-ssh",
            "label": "Walter SSH",
            "command": "ssh joselrnz@192.168.50.150",
            "description": "Open Walter over SSH without requiring PyHerdr on the remote host.",
            "agent": "shell",
        },
        {
            "id": "ollama-local",
            "label": "Ollama Local",
            "command": "ollama run llama3.1",
            "description": "Start a local Ollama model in a pane.",
            "agent": "ollama",
        },
        {
            "id": "codex-cli",
            "label": "Codex CLI",
            "command": "codex",
            "description": "Start the local Codex CLI when available.",
            "agent": "codex",
        },
        {
            "id": "claude-code",
            "label": "Claude Code",
            "command": "claudecode",
            "description": "Start Claude Code / Cloud Code when available.",
            "agent": "claude",
        },
    ]
