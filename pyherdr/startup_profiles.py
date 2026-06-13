"""Reusable startup profile planning for panes, SSH connections, and workflows."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

from .config import Config, ConnectionConfig, ConnectionType, ProfileConfig, ProfilePaneConfig, WorkflowConfig
from .layout import Direction, PaneNode, SplitNode, TileLayout, build_template_layout
from .remote import ssh_base_command, ssh_target


@dataclass(frozen=True)
class StartupValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def build_ssh_command(connection: ConnectionConfig, remote_command: str = "") -> str:
    if not connection.host:
        return ""
    parts = [*ssh_base_command(connection), ssh_target(connection)]
    command = remote_command
    if connection.remote_cwd and command:
        command = f"cd {shlex.quote(connection.remote_cwd)} && {command}"
    elif connection.remote_cwd:
        command = f"cd {shlex.quote(connection.remote_cwd)} && exec $SHELL -l"
    if command:
        parts.append(command)
    return " ".join(shlex.quote(part) for part in parts)


def build_pane_command(config: Config, pane: ProfilePaneConfig) -> str:
    if not pane.connection:
        return pane.command
    connection = config.connections.get(pane.connection)
    if connection is None:
        return pane.command
    if connection.type == ConnectionType.LOCAL:
        return pane.command
    return build_ssh_command(connection, pane.command)


def _pane_names_for_layout(profile: ProfileConfig) -> list[str]:
    panes = list(profile.panes)
    if not panes:
        return []
    if profile.layout in {"main-left", "main-top"}:
        preferred = ["left", "main", "right-top", "top", "right-bottom", "bottom"]
    elif profile.layout == "grid-2x2":
        preferred = ["top-left", "left-top", "top-right", "right-top", "bottom-left", "left-bottom", "bottom-right"]
    else:
        preferred = ["left", "top", "right", "bottom"]
    ordered: list[ProfilePaneConfig] = []
    remaining = panes.copy()
    for position in preferred:
        match = next((pane for pane in remaining if pane.position.lower() == position), None)
        if match is not None:
            ordered.append(match)
            remaining.remove(match)
    ordered.extend(remaining)
    return [pane.name for pane in ordered]


def build_profile_layout(profile: ProfileConfig) -> dict[str, Any]:
    pane_names = _pane_names_for_layout(profile)
    if not pane_names:
        return {}
    if len(pane_names) == 1:
        return TileLayout.single(pane_names[0]).to_dict()
    if profile.layout:
        try:
            return build_template_layout(profile.layout, pane_names).to_dict()
        except ValueError:
            pass
    positions = {pane.position.lower(): pane.name for pane in profile.panes if pane.position}
    if {"top", "bottom"}.issubset(positions):
        root = SplitNode(Direction.VERTICAL, 0.5, PaneNode(positions["top"]), PaneNode(positions["bottom"]))
        return TileLayout(root, positions["top"]).to_dict()
    if {"left", "right"}.issubset(positions):
        root = SplitNode(Direction.HORIZONTAL, 0.5, PaneNode(positions["left"]), PaneNode(positions["right"]))
        return TileLayout(root, positions["left"]).to_dict()
    return build_template_layout("columns-2" if len(pane_names) == 2 else "main-left", pane_names).to_dict()


def validate_startup_config(config: Config, *, profile_name: str | None = None) -> StartupValidation:
    errors: list[str] = []
    warnings: list[str] = []
    for name, connection in config.connections.items():
        if connection.type == ConnectionType.SSH and not connection.host:
            errors.append(f"connection {name} is ssh but has no host")
        if connection.password:
            errors.append(f"connection {name} uses unsupported password storage")
        if connection.connect_timeout < 1:
            errors.append(f"connection {name} connect_timeout must be positive")
        if connection.strict_host_key_checking and connection.strict_host_key_checking not in {
            "yes",
            "no",
            "accept-new",
        }:
            errors.append(f"connection {name} strict_host_key_checking must be yes, no, accept-new, or empty")
        if connection.server_alive_interval < 0:
            errors.append(f"connection {name} server_alive_interval cannot be negative")
        if connection.server_alive_count_max < 0:
            errors.append(f"connection {name} server_alive_count_max cannot be negative")

    selected_profiles = (
        {profile_name: config.profiles[profile_name]}
        if profile_name and profile_name in config.profiles
        else config.profiles
    )
    if profile_name and profile_name not in config.profiles:
        errors.append(f"profile {profile_name} does not exist")

    pane_names_by_profile: dict[str, set[str]] = {}
    for name, profile in selected_profiles.items():
        seen: set[str] = set()
        for pane in profile.panes:
            if pane.name in seen:
                errors.append(f"profile {name} has duplicate pane name {pane.name}")
            seen.add(pane.name)
            if pane.connection and pane.connection not in config.connections:
                errors.append(f"profile {name} pane {pane.name} references missing connection {pane.connection}")
            if not pane.connection and not pane.command:
                warnings.append(f"profile {name} pane {pane.name} has no command or connection")
            if pane.health_check and not pane.health_match:
                warnings.append(f"profile {name} pane {pane.name} has a health_check without health_match")
            if pane.health_timeout_ms < 1:
                errors.append(f"profile {name} pane {pane.name} health_timeout_ms must be positive")
        pane_names_by_profile[name] = seen

    for name, workflow in config.workflows.items():
        workflow_profile = workflow.profile
        if not workflow_profile:
            errors.append(f"workflow {name} has no profile")
            continue
        if workflow_profile not in config.profiles:
            errors.append(f"workflow {name} references missing profile {workflow_profile}")
            continue
        if profile_name and workflow_profile != profile_name:
            continue
        pane_names = pane_names_by_profile.get(workflow_profile)
        if pane_names is None:
            pane_names = {pane.name for pane in config.profiles[workflow_profile].panes}
        for step in workflow.steps:
            if step.pane not in pane_names:
                errors.append(f"workflow {name} step references missing pane {step.pane}")
            if not (step.send or step.command):
                warnings.append(f"workflow {name} step for pane {step.pane} has no send or command")

    return StartupValidation(ok=not errors, errors=errors, warnings=warnings)


def profile_inventory(config: Config) -> dict[str, Any]:
    return {
        "type": "profile_list",
        "connections": sorted(config.connections),
        "profiles": sorted(config.profiles),
        "workflows": sorted(config.workflows),
        "counts": {
            "connections": len(config.connections),
            "profiles": len(config.profiles),
            "workflows": len(config.workflows),
        },
    }


def plan_profile(config: Config, profile_name: str, *, workflow_name: str | None = None) -> dict[str, Any]:
    if profile_name not in config.profiles:
        raise ValueError(f"profile {profile_name} does not exist")
    validation = validate_startup_config(config, profile_name=profile_name)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    profile = config.profiles[profile_name]
    workflow: WorkflowConfig | None = None
    if workflow_name:
        workflow = config.workflows.get(workflow_name)
        if workflow is None:
            raise ValueError(f"workflow {workflow_name} does not exist")
        if workflow.profile != profile_name:
            raise ValueError(f"workflow {workflow_name} targets profile {workflow.profile}, not {profile_name}")
    panes: list[dict[str, Any]] = []
    for index, pane in enumerate(profile.panes):
        env = {**profile.env, **pane.env}
        health = None
        if pane.health_check:
            health = {
                "command": pane.health_check,
                "match": pane.health_match,
                "timeout_ms": pane.health_timeout_ms,
                "regex": pane.health_regex,
            }
        panes.append(
            {
                "name": pane.name,
                "connection": pane.connection,
                "command": build_pane_command(config, pane),
                "cwd": pane.cwd or profile.cwd,
                "position": pane.position,
                "tab": pane.tab,
                "env": env,
                "start_order": pane.start_order,
                "profile_index": index,
                "health": health,
            }
        )
    start_sequence = [
        pane["name"]
        for pane in sorted(
            panes,
            key=lambda pane: (int(pane["start_order"]) if pane["start_order"] else 0, int(pane["profile_index"])),
        )
    ]
    return {
        "type": "profile_plan",
        "profile": profile_name,
        "workspace": profile.workspace,
        "cwd": profile.cwd,
        "layout": profile.layout,
        "layout_tree": build_profile_layout(profile),
        "panes": panes,
        "start_sequence": start_sequence,
        "workflow": None
        if workflow is None
        else {
            "name": workflow_name,
            "steps": [
                {"pane": step.pane, "send": step.send, "command": step.command, "enter": step.enter}
                for step in workflow.steps
            ],
        },
    }
