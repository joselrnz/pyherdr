"""Notifications / toasts (ported from herdr `notification show` + ui toast).

Delivery follows the configured `[ui.toast]` mode: ``system`` attempts a native
OS notification, ``terminal`` prints to the server log, ``herdr`` is the in-app
toast (rendered by a client), and ``off`` suppresses it. The CLI always echoes
the notification in its JSON response regardless of delivery.
"""

from __future__ import annotations

import subprocess
import sys

from pydantic import BaseModel, ConfigDict

from .config import ToastDelivery


class Notification(BaseModel):
    """A user-facing notification."""

    model_config = ConfigDict(extra="ignore")

    title: str
    body: str = ""
    position: str = "bottom-right"
    sound: str = "none"  # none | done | request


def _system_notify(title: str, body: str) -> bool:
    """Best-effort native OS notification; return whether it was delivered."""
    try:
        if sys.platform == "darwin":
            script = f'display notification {_applescript_quote(body)} with title {_applescript_quote(title)}'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return True
        if sys.platform.startswith("linux"):
            subprocess.run(["notify-send", title, body], capture_output=True, timeout=5)
            return True
    except (OSError, subprocess.SubprocessError):
        return False
    return False


def _applescript_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def deliver(notification: Notification, delivery: ToastDelivery) -> str:
    """Deliver a notification per the configured mode; return the mode used."""
    text = notification.title if not notification.body else f"{notification.title} — {notification.body}"
    if delivery is ToastDelivery.OFF:
        return "off"
    if delivery is ToastDelivery.SYSTEM and _system_notify(notification.title, notification.body):
        return "system"
    if delivery in (ToastDelivery.TERMINAL, ToastDelivery.SYSTEM):
        print(f"🔔 {text}")
        return "terminal"
    return delivery.value  # herdr (in-app toast rendered by a client)
