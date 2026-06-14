def detect(content):
    if "PYHERDR_PLUGIN_BLOCKED" in content:
        return {"state": "blocked", "visible_blocker": True}
    if "PYHERDR_PLUGIN_DONE" in content:
        return "done"
    if "PYHERDR_PLUGIN_WORKING" in content:
        return "working"
    return "idle"
