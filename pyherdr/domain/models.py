from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from .status import AgentStatus


class DomainModel(BaseModel):
    """Base class for mutable, validated PyHerdr domain models."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")


def most_urgent_status(statuses: Iterable[AgentStatus]) -> AgentStatus:
    """Return the highest-priority status from an iterable."""
    return max(statuses, key=lambda status: status.priority, default=AgentStatus.UNKNOWN)


class Pane(DomainModel):
    """A server-owned process surface inside a tab."""

    id: str
    title: str = "pane"
    cwd: str
    command: str = ""
    agent: str = ""
    output: list[str] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.IDLE
    custom_status: str = ""

    _default_output_limit: int = PrivateAttr(default=500)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        """Validate that pane ids are visible strings."""
        return _non_empty(value, "pane id")

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str) -> str:
        """Normalize user-visible pane titles."""
        return _label_or_default(value, "pane")

    @field_validator("cwd")
    @classmethod
    def _validate_cwd(cls, value: str) -> str:
        """Validate the pane working-directory label."""
        return _non_empty(value, "pane cwd")

    def append_output(self, text: str, max_lines: int | None = None) -> None:
        """Append captured output and keep the recent buffer bounded."""
        limit = max_lines or self._default_output_limit
        lines = text.splitlines() or [text]
        self.output.extend(line.rstrip() for line in lines)
        if len(self.output) > limit:
            del self.output[: len(self.output) - limit]

    def set_status(self, status: AgentStatus) -> None:
        """Set the pane status through assignment validation."""
        self.status = status


class Tab(DomainModel):
    """A named group of panes within one workspace."""

    id: str
    label: str
    panes: list[Pane] = Field(default_factory=list)
    focused_pane_id: str | None = None
    synchronized: bool = False
    layout: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        """Validate that tab ids are visible strings."""
        return _non_empty(value, "tab id")

    @field_validator("label")
    @classmethod
    def _normalize_label(cls, value: str) -> str:
        """Normalize user-visible tab labels."""
        return _label_or_default(value, "tab")

    @property
    def focused_pane(self) -> Pane | None:
        """Return the focused pane, defaulting to the first pane when needed."""
        if self.focused_pane_id is None and self.panes:
            self.focused_pane_id = self.panes[0].id
        return next((pane for pane in self.panes if pane.id == self.focused_pane_id), None)

    @focused_pane.setter
    def focused_pane(self, pane: Pane | None) -> None:
        """Focus a pane by assigning a pane object."""
        self.focused_pane_id = pane.id if pane else None

    @property
    def status(self) -> AgentStatus:
        """Return the rollup status for panes in this tab."""
        return most_urgent_status(pane.status for pane in self.panes)

    def focus_pane(self, pane_id: str) -> Pane:
        """Focus a pane by id and return it."""
        pane = next((candidate for candidate in self.panes if candidate.id == pane_id), None)
        if pane is None:
            raise KeyError(f"pane not found: {pane_id}")
        self.focused_pane_id = pane.id
        return pane


class Workspace(DomainModel):
    """A project-level container for tabs and panes."""

    id: str
    label: str
    cwd: str
    tabs: list[Tab] = Field(default_factory=list)
    focused_tab_id: str | None = None

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        """Validate that workspace ids are visible strings."""
        return _non_empty(value, "workspace id")

    @field_validator("label")
    @classmethod
    def _normalize_label(cls, value: str) -> str:
        """Normalize user-visible workspace labels."""
        return _label_or_default(value, "workspace")

    @field_validator("cwd")
    @classmethod
    def _validate_cwd(cls, value: str) -> str:
        """Validate the workspace path label."""
        return _non_empty(value, "workspace cwd")

    @property
    def focused_tab(self) -> Tab | None:
        """Return the focused tab, defaulting to the first tab when needed."""
        if self.focused_tab_id is None and self.tabs:
            self.focused_tab_id = self.tabs[0].id
        return next((tab for tab in self.tabs if tab.id == self.focused_tab_id), None)

    @focused_tab.setter
    def focused_tab(self, tab: Tab | None) -> None:
        """Focus a tab by assigning a tab object."""
        self.focused_tab_id = tab.id if tab else None

    @property
    def status(self) -> AgentStatus:
        """Return the rollup status for tabs in this workspace."""
        return most_urgent_status(tab.status for tab in self.tabs)

    def focus_tab(self, tab_id: str) -> Tab:
        """Focus a tab by id and return it."""
        tab = next((candidate for candidate in self.tabs if candidate.id == tab_id), None)
        if tab is None:
            raise KeyError(f"tab not found: {tab_id}")
        self.focused_tab_id = tab.id
        return tab


class Schedule(DomainModel):
    """A cron-scheduled command to run in a pane (a pyherdr extension)."""

    id: str
    cron: str
    pane_id: str
    command: str
    enabled: bool = True
    send_enter: bool = True


class AppState(DomainModel):
    """Mutable, persisted PyHerdr session state."""

    workspaces: list[Workspace] = Field(default_factory=list)
    focused_workspace_id: str | None = None
    next_pane_number: int = 1
    schedules: list[Schedule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _advance_pane_counter(self) -> AppState:
        """Keep the pane counter ahead of any existing id.

        Protects loaded or hand-edited sessions: if persisted panes already use
        numbers at or above ``next_pane_number`` (e.g. state saved before this
        counter existed), bump it so newly created panes never reuse an id.
        """
        highest = 0
        for workspace in self.workspaces:
            for tab in workspace.tabs:
                for pane in tab.panes:
                    suffix = pane.id.rsplit("-", 1)[-1]
                    if suffix.isdigit():
                        highest = max(highest, int(suffix))
        if self.next_pane_number <= highest:
            self.next_pane_number = highest + 1
        return self

    @classmethod
    def bootstrap(cls, cwd: str | None = None) -> AppState:
        """Create a default session with one workspace, tab, and pane."""
        state = cls()
        workspace = state.create_workspace("main", cwd or str(Path.cwd()))
        state.create_tab(workspace.id, "shell")
        return state

    @property
    def focused_workspace(self) -> Workspace | None:
        """Return the focused workspace, defaulting to the first one."""
        if self.focused_workspace_id is None and self.workspaces:
            self.focused_workspace_id = self.workspaces[0].id
        return next(
            (workspace for workspace in self.workspaces if workspace.id == self.focused_workspace_id),
            None,
        )

    @focused_workspace.setter
    def focused_workspace(self, workspace: Workspace | None) -> None:
        """Focus a workspace by assigning a workspace object."""
        self.focused_workspace_id = workspace.id if workspace else None

    def create_workspace(self, label: str, cwd: str) -> Workspace:
        """Create and focus a workspace."""
        workspace = Workspace(id=_short_id("ws"), label=label, cwd=cwd)
        self.workspaces.append(workspace)
        self.focused_workspace = workspace
        return workspace

    def create_tab(self, workspace_id: str, label: str) -> Tab:
        """Create and focus a tab in a workspace."""
        workspace = self.require_workspace(workspace_id)
        tab = Tab(id=_short_id("tab"), label=label)
        workspace.tabs.append(tab)
        workspace.focused_tab = tab
        self.create_pane(workspace.id, tab.id, title="pane")
        return tab

    def create_pane(self, workspace_id: str, tab_id: str, title: str = "pane") -> Pane:
        """Create and focus a pane in a tab.

        The pane id is ``"<workspace-ordinal>-<global-pane-number>"``. The pane
        number is drawn from a monotonic, persisted counter so ids stay unique
        and stable across tabs and survive workspace/tab closes, instead of
        being derived from list lengths (which collided across tabs).
        """
        workspace = self.require_workspace(workspace_id)
        tab = self.require_tab(workspace_id, tab_id)
        ordinal = self.workspaces.index(workspace) + 1
        pane = Pane(
            id=f"{ordinal}-{self.next_pane_number}",
            title=title,
            cwd=workspace.cwd,
        )
        self.next_pane_number += 1
        tab.panes.append(pane)
        tab.focused_pane = pane
        return pane

    def require_workspace(self, workspace_id: str) -> Workspace:
        """Return a workspace or raise `KeyError`."""
        for workspace in self.workspaces:
            if workspace.id == workspace_id:
                return workspace
        raise KeyError(f"workspace not found: {workspace_id}")

    def require_tab(self, workspace_id: str, tab_id: str) -> Tab:
        """Return a tab or raise `KeyError`."""
        workspace = self.require_workspace(workspace_id)
        for tab in workspace.tabs:
            if tab.id == tab_id:
                return tab
        raise KeyError(f"tab not found: {tab_id}")

    def require_pane(self, pane_id: str) -> Pane:
        """Return a pane or raise `KeyError`."""
        for workspace in self.workspaces:
            for tab in workspace.tabs:
                for pane in tab.panes:
                    if pane.id == pane_id:
                        return pane
        raise KeyError(f"pane not found: {pane_id}")

    def add_schedule(self, cron: str, pane_id: str, command: str) -> Schedule:
        """Create and store a cron schedule."""
        schedule = Schedule(id=_short_id("sch"), cron=cron, pane_id=pane_id, command=command)
        self.schedules.append(schedule)
        return schedule

    def remove_schedule(self, schedule_id: str) -> bool:
        """Remove a schedule by id; return whether one was removed."""
        before = len(self.schedules)
        self.schedules = [item for item in self.schedules if item.id != schedule_id]
        return len(self.schedules) != before


def _short_id(prefix: str) -> str:
    """Return a compact stable-enough id for local runtime entities."""
    return f"{prefix}_{uuid4().hex[:8]}"


def _non_empty(value: str, field_name: str) -> str:
    """Normalize and validate a required string value."""
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _label_or_default(value: str, default: str) -> str:
    """Normalize a label and fall back when it is blank."""
    normalized = str(value).strip()
    return normalized or default
