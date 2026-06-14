def exporters():
    return [{"id": "markdown", "label": "Markdown summary", "extension": ".md"}]


def export(recording, output, exporter_id=""):
    panes = []
    for workspace in recording.get("workspaces", []):
        for tab in workspace.get("tabs", []):
            panes.extend(tab.get("panes", []))
    lines = ["# PyHerdr Plugin Scenario", ""]
    for pane in panes:
        lines.append(f"- {pane.get('title', 'pane')}: {pane.get('agent_status', 'unknown')}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"exporter": exporter_id or "markdown", "pane_count": len(panes)}
