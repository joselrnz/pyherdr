"""Reusable startup profile planning for panes, SSH connections, and workflows."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

from .config import Config, ConnectionConfig, ConnectionType, ProfilePaneConfig, WorkflowConfig


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
    parts = ["ssh"]
    if connection.port and connection.port != 22:
        parts.extend(["-p", str(connection.port)])
    if connection.key:
        parts.extend(["-i", connection.key])
    if connection.proxy_jump:
        parts.extend(["-J", connection.proxy_jump])
    parts.extend(connection.extra_args)
    target = f"{connection.user}@{connection.host}" if connection.user else connection.host
    parts.append(target)
    if remote_command:
        parts.append(remote_command)
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


def validate_startup_config(config: Config, *, profile_name: str | None = None) -> StartupValidation:
    errors: list[str] = []
    warnings: list[str] = []
    for name, connection in config.connections.items():
        if connection.type == ConnectionType.SSH and not connection.host:
            errors.append(f"connection {name} is ssh but has no host")
        if connection.password:
            errors.append(f"connection {name} uses unsupported password storage")

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
    panes = [
        {
            "name": pane.name,
            "connection": pane.connection,
            "command": build_pane_command(config, pane),
            "cwd": pane.cwd or profile.cwd,
            "position": pane.position,
            "tab": pane.tab,
        }
        for pane in profile.panes
    ]
    return {
        "type": "profile_plan",
        "profile": profile_name,
        "workspace": profile.workspace,
        "cwd": profile.cwd,
        "layout": profile.layout,
        "panes": panes,
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
