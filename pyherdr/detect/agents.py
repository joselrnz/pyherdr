"""Per-agent terminal-state detectors, ported from herdr src/detect/agents/*.

Each ``_detect_<agent>`` returns an `AgentStatus` of IDLE / WORKING / BLOCKED
(never DONE — "done" is a UI-layer, seen/unseen concept). `detect()` adds the
visible-blocker/idle/working confidence flags used for source arbitration.
"""

from __future__ import annotations

from ..domain.status import AgentStatus
from . import _common as c
from ._models import Agent, AgentDetection

IDLE = AgentStatus.IDLE
WORKING = AgentStatus.WORKING
BLOCKED = AgentStatus.BLOCKED
UNKNOWN = AgentStatus.UNKNOWN


# ---------------------------------------------------------------------------
# pi
# ---------------------------------------------------------------------------
def _detect_pi(content: str) -> AgentStatus:
    return WORKING if "Working..." in content else IDLE


# ---------------------------------------------------------------------------
# cline (defaults to working)
# ---------------------------------------------------------------------------
def _detect_cline(content: str) -> AgentStatus:
    lower = content.lower()
    if "let cline use this tool" in lower:
        return BLOCKED
    if ("[act mode]" in lower or "[plan mode]" in lower) and "yes" in lower:
        return BLOCKED
    if "cline is ready for your message" in lower:
        return IDLE
    return WORKING


# ---------------------------------------------------------------------------
# gemini
# ---------------------------------------------------------------------------
def _detect_gemini(content: str) -> AgentStatus:
    lower = content.lower()
    if "waiting for user confirmation" in lower:
        return BLOCKED
    if "│ Apply this change" in content or "│ Allow execution" in content or "│ Do you want to proceed" in content:
        return BLOCKED
    if c.has_confirmation_prompt(lower):
        return BLOCKED
    if "esc to cancel" in lower:
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# droid
# ---------------------------------------------------------------------------
def _detect_droid(content: str) -> AgentStatus:
    lower = content.lower()
    has_execute = "EXECUTE" in content
    has_selection_chrome = (
        "enter to select" in lower or "↑↓ to navigate" in lower or "esc to cancel" in lower
    )
    has_selection_options = "> yes, allow" in lower or "> no, cancel" in lower
    if has_execute and (has_selection_chrome or has_selection_options):
        return BLOCKED
    if has_selection_chrome and has_selection_options:
        return BLOCKED
    if c.has_braille_spinner(content) and "esc to stop" in lower:
        return WORKING
    if "esc to stop" in lower:
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# amp
# ---------------------------------------------------------------------------
def _detect_amp(content: str) -> AgentStatus:
    lower = content.lower()
    has_waiting = "waiting for approval" in lower
    has_header = (
        "invoke tool" in lower
        or "run this command?" in lower
        or "allow editing file:" in lower
        or "allow creating file:" in lower
        or "confirm tool call" in lower
    )
    has_actions = "approve" in lower and (
        "allow all for this session" in lower
        or "allow all for every session" in lower
        or "allow file for every session" in lower
        or "deny with feedback" in lower
    )
    if has_actions and (has_waiting or has_header):
        return BLOCKED
    if "esc to cancel" in lower:
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# grok
# ---------------------------------------------------------------------------
def _detect_grok(content: str) -> AgentStatus:
    lower = content.lower()
    if (
        "use ← → to choose permission whitelist scope" in lower
        or "yes, proceed" in lower
        or "no, reject" in lower
        or "ctrl+o:yolo" in lower
        or ":scope" in lower
    ):
        return BLOCKED
    if c.has_braille_spinner(content) and (
        "waiting" in lower or "run " in lower or "read " in lower or "search " in lower or "list " in lower
    ):
        return WORKING
    if "ctrl+c:cancel" in lower and "ctrl+enter:interject" in lower:
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# hermes
# ---------------------------------------------------------------------------
def _detect_hermes(content: str) -> AgentStatus:
    lower = content.lower()
    has_options = "allow once" in lower and "allow for this session" in lower and "deny" in lower
    has_controls = "enter to confirm" in lower or "↑/↓ to select" in lower or "show full command" in lower
    if ("dangerous command" in lower or has_options) and has_controls:
        return BLOCKED
    if "msg=interrupt" in lower or "ctrl+c cancel" in lower:
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# github_copilot
# ---------------------------------------------------------------------------
def _detect_github_copilot(content: str) -> AgentStatus:
    lower = content.lower()
    if "esc to cancel" in lower and (
        "enter to select" in lower or "enter to confirm" in lower or "enter to submit" in lower
    ):
        return BLOCKED
    if "esc to cancel" in lower or "esc cancel" in lower or "esc again to cancel" in lower:
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# opencode + kilo (kilo delegates to opencode)
# ---------------------------------------------------------------------------
def _opencode_question_prompt(content: str) -> bool:
    lower = content.lower()
    has_enter = "enter confirm" in lower or "enter submit" in lower or "enter toggle" in lower
    has_nav = "↑↓ select" in content or "⇆ tab" in content
    return "esc dismiss" in lower and has_enter and has_nav


def _opencode_interrupt_footer(content: str) -> bool:
    for line in content.splitlines():
        lower = line.lower()
        if ("esc interrupt" in lower or "esc again to interrupt" in lower) and "opencode" in lower:
            return True
    return False


def _opencode_progress_run(content: str) -> bool:
    for line in content.splitlines():
        run = 0
        for ch in line:
            if ch in ("■", "⬝"):
                run += 1
                if run >= 4:
                    return True
            else:
                run = 0
    return False


def _detect_opencode(content: str) -> AgentStatus:
    if "△ Permission required" in content or _opencode_question_prompt(content):
        return BLOCKED
    working = (
        c.has_interrupt_pattern(content.lower())
        or _opencode_interrupt_footer(content)
        or _opencode_progress_run(content)
    )
    return WORKING if working else IDLE


def _detect_kilo(content: str) -> AgentStatus:
    if "esc interrupt" in content.lower():
        return WORKING
    return _detect_opencode(content)


# ---------------------------------------------------------------------------
# cursor
# ---------------------------------------------------------------------------
def _cursor_status_word_is_active(rest: str) -> bool:
    return c.status_word_is_active(rest)


def cursor_has_spinner(content: str) -> bool:
    """Cursor status line: spinner glyph followed by a live "...ing" action."""
    for line in content.splitlines():
        trimmed = line.lstrip()
        if not trimmed:
            continue
        first = trimmed[0]
        rest = trimmed[1:].lstrip()
        if first in ("⬡", "⬢"):
            if _cursor_status_word_is_active(rest):
                return True
        elif c.is_braille(first):
            rest = rest.lstrip("".join(ch for ch in rest if c.is_braille(ch)))
            if _cursor_status_word_is_active(rest.lstrip()):
                return True
    return False


def _cursor_blocked_prompt(content: str, lower: str) -> bool:
    if "waiting for approval" in lower or "run this command?" in lower:
        return True
    if "(y) (enter)" in lower or "keep (n)" in lower or "skip (esc or n)" in lower:
        return True
    for line in content.splitlines():
        line_lower = line.strip().lower()
        if "(y)" in line_lower and (
            "allow" in line_lower
            or "run (once)" in line_lower
            or "→ run" in line_lower
            or line_lower.startswith("run ")
        ):
            return True
    return False


def _detect_cursor(content: str) -> AgentStatus:
    lower = content.lower()
    if _cursor_blocked_prompt(content, lower):
        return BLOCKED
    if "ctrl+c to stop" in lower:
        return WORKING
    if cursor_has_spinner(content):
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# antigravity
# ---------------------------------------------------------------------------
def _antigravity_spinner(content: str) -> bool:
    for line in content.splitlines():
        trimmed = line.lstrip()
        if not trimmed or not c.is_braille(trimmed[0]):
            continue
        rest = trimmed.lstrip("".join(ch for ch in trimmed if c.is_braille(ch))).lstrip()
        if c.status_word_is_active(rest):
            return True
    return False


def _antigravity_task_count(line: str) -> int | None:
    for marker in (" task(s)", " tasks", " task"):
        before, sep, _ = line.partition(marker)
        if not sep:
            continue
        words = before.split()
        if not words:
            continue
        raw = words[-1].strip("·")
        if raw.isdigit():
            return int(raw)
    return None


def _antigravity_background_tasks(content: str) -> bool:
    for line in c.bottom_non_empty_lines(content, 5):
        lower = line.strip().lower()
        if "/tasks" in lower:
            count = _antigravity_task_count(lower)
            if count is not None and count > 0:
                return True
    return False


def _detect_antigravity(content: str) -> AgentStatus:
    lower = content.lower()
    has_request = "requesting permission for:" in lower
    has_question = "do you want to proceed?" in lower
    has_controls = "tab amend" in lower and "edit command" in lower
    if has_request and (has_question or has_controls):
        return BLOCKED
    if _antigravity_spinner(content) or _antigravity_background_tasks(content):
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# kiro
# ---------------------------------------------------------------------------
def _kiro_tool_spinner(content: str) -> bool:
    for line in content.splitlines():
        trimmed = line.lstrip()
        if not trimmed or trimmed[0] not in ("◔", "◑", "◕", "●"):
            continue
        rest = trimmed[1:].lstrip()
        if rest and rest[0].isalpha():
            return True
    return False


def _kiro_tool_approval_prompt(lower: str) -> bool:
    has_request = "requires approval" in lower
    has_actions = (
        "yes, single permission" in lower
        or "trust, always allow" in lower
        or "no (tab to edit)" in lower
        or "esc to close" in lower
    )
    return has_request and has_actions


def _kiro_subagent_approval_prompt(lower: str) -> bool:
    has_request = ("tool approval" in lower or "tool approvals" in lower) and "pending from subagents" in lower
    has_actions = (
        "approve all pending" in lower
        or "configure individually" in lower
        or "exit (cancel subagents)" in lower
    )
    return has_request and has_actions


def _detect_kiro(content: str) -> AgentStatus:
    lower = content.lower()
    if _kiro_tool_approval_prompt(lower) or _kiro_subagent_approval_prompt(lower):
        return BLOCKED
    if "kiro is working" in lower or ("esc to cancel" in lower and _kiro_tool_spinner(content)):
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# qodercli
# ---------------------------------------------------------------------------
def _qodercli_idle_override(lower: str) -> bool:
    return (
        "press ctrl+c again to exit" in lower
        or "press ctrl+d again to exit" in lower
        or "press esc again to rewind" in lower
    )


def _qodercli_blocked_prompt(lower: str) -> bool:
    return (
        "waiting for user confirmation" in lower
        or "awaiting approval" in lower
        or "permission required" in lower
        or "allow once or always?" in lower
        or "asking user" in lower
        or "enter your response" in lower
        or "review your answers:" in lower
        or "shell awaiting input" in lower
    )


def _qodercli_spinner_row(content: str) -> bool:
    for line in content.splitlines():
        trimmed = line.lstrip()
        if not trimmed or not c.is_braille(trimmed[0]):
            continue
        rest = trimmed[1:]
        if rest.startswith(" ") and any(ch.isalpha() for ch in rest):
            return True
    return False


def _detect_qodercli(content: str) -> AgentStatus:
    lower = content.lower()
    if _qodercli_idle_override(lower):
        return IDLE
    if _qodercli_blocked_prompt(lower):
        return BLOCKED
    if "(esc to cancel," in lower or _qodercli_spinner_row(content):
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# kimi
# ---------------------------------------------------------------------------
_KIMI_MOONS = ("🌕", "🌖", "🌗", "🌘", "🌑", "🌒", "🌓", "🌔")


def kimi_working_status(content: str) -> bool:
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed in _KIMI_MOONS:
            return True
        if not trimmed or not c.is_braille(trimmed[0]):
            continue
        rest = trimmed.lstrip("".join(ch for ch in trimmed if c.is_braille(ch))).lstrip().lower()
        if rest.startswith("thinking...") or rest.startswith("working...") or rest.startswith("using "):
            return True
    return False


def _kimi_approval_title(lower: str) -> bool:
    if (
        "run this command?" in lower
        or "write this file?" in lower
        or "apply these edits?" in lower
        or "stop this task?" in lower
        or "ready to build with this plan?" in lower
    ):
        return True
    for line in lower.splitlines():
        trimmed = line.lstrip("▶ \t")
        if trimmed.startswith("approve ") and trimmed.endswith("?"):
            return True
    return False


def _kimi_numeric_choose_hint(lower: str) -> bool:
    return " choose" in lower and "1" in lower and "2" in lower


def _kimi_current_approval_panel(content: str) -> bool:
    lower = content.lower()
    return (
        _kimi_approval_title(lower)
        and _kimi_numeric_choose_hint(lower)
        and "↵ confirm" in lower
        and ("approve" in lower or "reject" in lower or "revise" in lower)
    )


def _kimi_question_panel(content: str) -> bool:
    lower = content.lower()
    return (
        any(line.strip() == "question" for line in content.splitlines())
        and any(line.lstrip().startswith("? ") for line in content.splitlines())
        and "↑↓ select" in lower
        and ("↵ choose" in lower or "↵ toggle" in lower or "↵ save" in lower)
        and "esc cancel" in lower
    )


def kimi_has_visible_blocker(content: str) -> bool:
    return _kimi_current_approval_panel(content) or _kimi_question_panel(content)


def _kimi_blocked_prompt(content: str) -> bool:
    if kimi_has_visible_blocker(content):
        return True
    lower = content.lower()
    return (
        "requesting approval" in lower
        and ("approve once" in lower or "approve for this session" in lower)
        and "reject" in lower
        and ("1/2/3/4 choose" in lower or "↵ confirm" in lower)
    )


def _kimi_editor_top_border(line: str) -> bool:
    trimmed = line.strip()
    return (
        (trimmed.startswith("╭") and trimmed.endswith("╮")) or (trimmed.startswith("├") and trimmed.endswith("┤"))
    ) and "─" in trimmed


def _kimi_editor_bottom_border(line: str) -> bool:
    trimmed = line.strip()
    return trimmed.startswith("╰") and trimmed.endswith("╯") and "─" in trimmed


def _kimi_editor_prompt_line(line: str) -> bool:
    trimmed = line.lstrip()
    inner = trimmed[1:].lstrip() if trimmed.startswith("│") else trimmed
    return inner.startswith(">")


def _kimi_editor_prompt_box(content: str) -> bool:
    lines = content.splitlines()
    for top in range(len(lines)):
        if not _kimi_editor_top_border(lines[top]):
            continue
        saw_prompt = False
        for line in lines[top + 1 :]:
            if _kimi_editor_bottom_border(line):
                if saw_prompt:
                    return True
                break
            saw_prompt = saw_prompt or _kimi_editor_prompt_line(line)
    return False


def kimi_has_prompt_box(content: str) -> bool:
    return _kimi_editor_prompt_box(content) and "context: " in content.lower()


def _detect_kimi(content: str) -> AgentStatus:
    if _kimi_blocked_prompt(content):
        return BLOCKED
    if kimi_working_status(content):
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# claude
# ---------------------------------------------------------------------------
_CLAUDE_SPINNER = "·✱✲✳✴✵✶✷✸✹✺✻✼✽✾✿❀❁❂❃❇❈❉❊❋✢✣✤✥✦✧✨⊛⊕⊙◉◎◍⁂⁕※⍟☼★☆"


def _claude_prompt_box_top_border_index(lines: list[str]) -> int | None:
    border = 0
    for i in range(len(lines) - 1, -1, -1):
        if c.is_horizontal_rule(lines[i]):
            border += 1
            if border == 2:
                return i
    return None


def claude_has_prompt_box(content: str) -> bool:
    lines = content.splitlines()
    top = _claude_prompt_box_top_border_index(lines)
    if top is None:
        return False
    for line in lines[top + 1 :]:
        if c.is_horizontal_rule(line):
            break
        if line.lstrip().startswith("❯"):
            return True
    return False


def _claude_content_above_prompt_box(content: str) -> str:
    lines = content.splitlines()
    top = _claude_prompt_box_top_border_index(lines)
    if top is not None:
        return "\n".join(lines[:top])
    return content


def _claude_content_after_last_rule(content: str) -> str:
    lines = content.splitlines()
    last = -1
    for i, line in enumerate(lines):
        if c.is_horizontal_rule(line):
            last = i
    return "\n".join(lines[last + 1 :]) if last >= 0 else content


def _claude_has_live_blocked_form(content: str) -> bool:
    for line in _claude_content_after_last_rule(content).splitlines():
        lower = line.lower()
        if (
            "enter to select" in lower
            and "esc to cancel" in lower
            and (
                "tab/arrow keys to navigate" in lower
                or "arrow keys to navigate" in lower
                or "arrows to navigate" in lower
                or "↑/↓ to navigate" in lower
                or "↑↓ to navigate" in lower
            )
        ):
            return True
    return False


def _claude_spinner_activity(content: str) -> bool:
    for line in content.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        if trimmed[0] in _CLAUDE_SPINNER:
            rest = trimmed[1:]
            if rest.startswith(" ") and "…" in rest and any(ch.isalnum() for ch in rest):
                return True
    return False


def _claude_background_wait_line(line: str) -> bool:
    text = line.strip()
    if not (text.startswith("Waiting for ") or text.startswith("waiting for ")):
        if not text:
            return False
        if text[0].isalnum():
            return False
        text = text[1:].lstrip()
    lower = text.lower()
    if not lower.startswith("waiting for "):
        return False
    rest = lower[len("waiting for ") :]
    parts = rest.split(" ", 1)
    if len(parts) != 2:
        return False
    count, tail = parts
    if not count.isdigit() or int(count) == 0:
        return False
    return tail in ("background agent to finish", "background agents to finish")


def _claude_still_running_status_line(line: str) -> bool:
    words = line.lower().split()
    for index, word in enumerate(words):
        if not word.isdigit() or int(word) == 0:
            continue
        seg3 = words[index + 1 : index + 4]
        if seg3 in (["shell", "still", "running"], ["shells", "still", "running"]):
            return True
        seg4 = words[index + 1 : index + 5]
        if (
            len(seg4) == 4
            and seg4[0] == "local"
            and seg4[1] in ("agent", "agents")
            and seg4[2:] == ["still", "running"]
        ):
            return True
    return False


def _claude_running_status_line(above: str) -> bool:
    line = next((ln for ln in reversed(above.splitlines()) if ln.strip()), None)
    if line is None:
        return False
    return _claude_background_wait_line(line) or _claude_still_running_status_line(line)


def claude_has_working_chrome(content: str) -> bool:
    above = _claude_content_above_prompt_box(content)
    above_lower = above.lower()
    return (
        "esc to interrupt" in above_lower
        or "ctrl+c to interrupt" in above_lower
        or _claude_running_status_line(above)
        or _claude_spinner_activity(above)
    )


def _claude_yes_no_choice(content: str) -> bool:
    for line in content.splitlines():
        trimmed = line.strip().lstrip("❯").lstrip().lower()
        if (
            trimmed in ("yes", "no")
            or trimmed.startswith("1. yes")
            or trimmed.startswith("2. no")
            or trimmed.startswith("yes, and ")
            or trimmed.startswith("no, and tell claude")
        ):
            return True
    return False


def _claude_blocked_prompt(content: str, lower: str) -> bool:
    return (
        c.has_confirmation_prompt(lower)
        or "do you want to proceed?" in lower
        or "would you like to proceed?" in lower
        or "waiting for permission" in lower
        or "do you want to allow this connection?" in lower
        or "tab to amend" in lower
        or "ctrl+e to explain" in lower
        or "review your answers" in lower
        or "skip interview and plan immediately" in lower
        or (c.has_selection_prompt(content) and _claude_yes_no_choice(content))
    )


def claude_has_visible_blocker(content: str) -> bool:
    lower = content.lower()
    return _claude_has_live_blocked_form(content) or (
        "do you want to proceed?" in lower
        and _claude_yes_no_choice(content)
        and (
            "bash command" in lower
            or "bash(" in lower
            or "contains expansion" in lower
            or "tab to amend" in lower
            or "ctrl+e to explain" in lower
        )
    )


def claude_is_transcript_viewer(content: str) -> bool:
    bottom = c.bottom_non_empty_lines(content, 3)
    if not bottom:
        return False
    text = c.normalize_lines(bottom)
    last = bottom[-1].lower()
    tail = "ctrl+e" in last or "show all" in last or "collapse" in last or "verbose" in last
    return (
        "showing detailed transcript" in text
        and "ctrl+o to toggle" in text
        and ("ctrl+e to show all" in text or "ctrl+e to collapse" in text)
        and tail
    )


def _detect_claude(content: str) -> AgentStatus:
    lower = content.lower()
    if "⌕ Search…" in content:
        return IDLE
    if "ctrl+r to toggle" in lower:
        return IDLE
    if _claude_has_live_blocked_form(content):
        return BLOCKED
    if claude_has_working_chrome(content):
        return WORKING
    if not claude_has_prompt_box(content) and _claude_blocked_prompt(content, lower):
        return BLOCKED
    if claude_has_prompt_box(content):
        return IDLE
    return IDLE


# ---------------------------------------------------------------------------
# codex
# ---------------------------------------------------------------------------
def _codex_prompt_line(line: str) -> bool:
    return line == "›" or line.startswith("› ")


def _codex_block_marker_line(line: str) -> bool:
    return line.startswith("•") or line.startswith("■") or line.startswith("✗") or line.startswith("✓")


def _codex_status_detail_line(line: str) -> bool:
    return line.lstrip().startswith("└")


def _codex_queued_input_header(line: str) -> bool:
    trimmed = line.lstrip()
    if not trimmed.startswith("•"):
        return False
    lower = trimmed.lower()
    return lower.startswith("• queued follow-up inputs") or lower.startswith(
        "• messages to be submitted after next tool call"
    )


def _codex_working_status_line(line: str) -> bool:
    if _codex_queued_input_header(line):
        return True
    trimmed = line.lstrip()
    lower = trimmed.lower()
    return trimmed.startswith("•") and (
        "Working (" in trimmed
        or "Waiting for background terminal (" in trimmed
        or "reviewing approval request (" in lower
        or ("reviewing " in lower and " approval requests (" in lower)
        or "Booting MCP server:" in trimmed
    )


def _codex_live_working_line(line: str) -> bool:
    if _codex_queued_input_header(line):
        return True
    trimmed = line.lstrip()
    lower = trimmed.lower()
    return _codex_working_status_line(line) and (
        "Waiting for background terminal" in trimmed
        or "esc to interrupt" in lower
        or "esc…" in lower
        or "background terminal running" in lower
        or "/ps to view" in lower
        or "/stop to close" in lower
    )


def _codex_current_prompt_region(content: str) -> tuple[list[str], int] | None:
    lines = content.splitlines()
    prompt_index = None
    for i in range(len(lines) - 1, -1, -1):
        if _codex_prompt_line(lines[i]):
            prompt_index = i
            break
    if prompt_index is None:
        return None
    if any(_codex_block_marker_line(line) for line in lines[prompt_index + 1 :]):
        return None
    return lines, prompt_index


def codex_has_current_prompt(content: str) -> bool:
    return _codex_current_prompt_region(content) is not None


def _codex_last_block_marker_before_prompt(content: str) -> str | None:
    region = _codex_current_prompt_region(content)
    if region is None:
        return None
    lines, prompt_index = region
    for line in reversed(lines[:prompt_index]):
        if _codex_block_marker_line(line):
            return line
    return None


def _codex_working_status_at_prompt(content: str) -> bool:
    marker = _codex_last_block_marker_before_prompt(content)
    return marker is not None and _codex_working_status_line(marker)


def _codex_live_working_at_prompt(content: str) -> bool:
    marker = _codex_last_block_marker_before_prompt(content)
    return marker is not None and _codex_live_working_line(marker)


def _codex_working_header(content: str) -> bool:
    return any(_codex_working_status_line(line) for line in content.splitlines())


def _codex_strong_blocked(lower: str) -> bool:
    return (
        "press enter to confirm or esc to cancel" in lower
        or "enter to submit answer" in lower
        or "enter to submit all" in lower
        or "allow command?" in lower
    )


def _codex_weak_blocked(lower: str) -> bool:
    return "[y/n]" in lower or "yes (y)" in lower or c.has_confirmation_prompt(lower)


def _codex_visible_working_without_prompt(content: str) -> bool:
    recent = [line for line in reversed(content.splitlines()) if line.strip()]
    if not recent:
        return False
    last = recent[0]
    if _codex_live_working_line(last):
        return True
    if not _codex_status_detail_line(last):
        return False
    marker = next((line for line in recent[1:5] if _codex_block_marker_line(line)), None)
    return marker is not None and _codex_live_working_line(marker)


def codex_has_visible_blocker(content: str) -> bool:
    return _codex_strong_blocked(content.lower())


def codex_has_prompt(content: str) -> bool:
    return codex_has_current_prompt(content) or any(_codex_prompt_line(line) for line in content.splitlines())


def codex_has_visible_working(content: str) -> bool:
    return _codex_live_working_at_prompt(content) or (
        not codex_has_current_prompt(content) and _codex_visible_working_without_prompt(content)
    )


def codex_is_transcript_viewer(content: str) -> bool:
    bottom = c.bottom_non_empty_lines(content, 3)
    if not bottom:
        return False
    text = c.normalize_lines(bottom)
    last = bottom[-1].lower()
    tail = (
        "q to quit" in last
        or "esc to edit" in last
        or "esc/← to edit" in last
        or "edit message" in last
    )
    edit_prev = "esc to edit prev" in text or "esc/← to edit prev" in text
    return (
        "↑/↓ to scroll" in text
        and "pgup/pgdn to page" in text
        and "home/end to jump" in text
        and "q to quit" in text
        and edit_prev
        and tail
    )


def _detect_codex(content: str) -> AgentStatus:
    lower = content.lower()
    if _codex_strong_blocked(lower):
        return BLOCKED
    if _codex_working_status_at_prompt(content):
        return WORKING
    if codex_has_current_prompt(content):
        return IDLE
    if _codex_weak_blocked(lower):
        return BLOCKED
    if c.has_interrupt_pattern(lower) or _codex_working_header(content):
        return WORKING
    return IDLE


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
_DETECTORS = {
    Agent.PI: _detect_pi,
    Agent.CLAUDE: _detect_claude,
    Agent.CODEX: _detect_codex,
    Agent.GEMINI: _detect_gemini,
    Agent.CURSOR: _detect_cursor,
    Agent.ANTIGRAVITY: _detect_antigravity,
    Agent.CLINE: _detect_cline,
    Agent.OPENCODE: _detect_opencode,
    Agent.GITHUB_COPILOT: _detect_github_copilot,
    Agent.KIMI: _detect_kimi,
    Agent.KIRO: _detect_kiro,
    Agent.DROID: _detect_droid,
    Agent.AMP: _detect_amp,
    Agent.GROK: _detect_grok,
    Agent.HERMES: _detect_hermes,
    Agent.KILO: _detect_kilo,
    Agent.QODERCLI: _detect_qodercli,
}


def should_skip_state_update(agent: Agent, content: str) -> bool:
    """Whether the current screen is a transcript viewer (skip state updates)."""
    if agent is Agent.CLAUDE:
        return claude_is_transcript_viewer(content)
    if agent is Agent.CODEX:
        return codex_is_transcript_viewer(content)
    return False


def _visible_blocker(agent: Agent, content: str, state: AgentStatus) -> bool:
    if state is not BLOCKED:
        return False
    if agent is Agent.CLAUDE:
        return claude_has_visible_blocker(content)
    if agent is Agent.CODEX:
        return codex_has_visible_blocker(content)
    if agent is Agent.KIMI:
        return kimi_has_visible_blocker(content)
    return False


def _visible_idle(agent: Agent, content: str, state: AgentStatus) -> bool:
    if state is not IDLE:
        return False
    if agent is Agent.CLAUDE:
        return claude_has_prompt_box(content)
    if agent is Agent.CODEX:
        return codex_has_prompt(content)
    if agent is Agent.KIMI:
        return kimi_has_prompt_box(content)
    return False


def _visible_working(agent: Agent, content: str, state: AgentStatus) -> bool:
    if state is not WORKING:
        return False
    if agent is Agent.CLAUDE:
        return claude_has_working_chrome(content)
    if agent is Agent.CODEX:
        return codex_has_visible_working(content)
    if agent is Agent.KIMI:
        return kimi_working_status(content)
    return False


def detect(agent: Agent | None, content: str) -> AgentDetection:
    """Detect agent state plus visible-chrome confidence flags."""
    if agent is None:
        return AgentDetection(state=UNKNOWN)
    state = _DETECTORS[agent](content)
    if should_skip_state_update(agent, content):
        return AgentDetection(state=state, skip_state_update=True)
    return AgentDetection(
        state=state,
        visible_blocker=_visible_blocker(agent, content, state),
        visible_idle=_visible_idle(agent, content, state),
        visible_working=_visible_working(agent, content, state),
    )


def detect_state(agent: Agent | None, content: str) -> AgentStatus:
    """Detect just the agent state (UNKNOWN when no agent is identified)."""
    return detect(agent, content).state
