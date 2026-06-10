from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from .config import load_config
from .gui import main as dashboard_main
from .models import AgentStatus
from .server import (
    ServerInfo,
    ensure_request,
    ping,
    read_server_info,
    remove_server_info,
    request,
    run_foreground,
    start_background,
    stop_running,
)
from .session import DEFAULT_SESSION, list_session_names, session_runtime_dir
from .store import load_state
from .workspace_recents import load_workspace_recents, prune_workspace_recents
from .workspace_search import SearchRoot, row_to_dict, search_workspace_rows


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    if raw_args in (["--version"], ["-V"]):
        print(f"pyherdr {__version__}")
        return 0
    parser = build_parser()
    args = parser.parse_args(raw_args)

    if args.command in (None, "dashboard"):
        dashboard_main()
        return 0

    if args.command == "version":
        print(f"pyherdr {__version__}")
        return 0

    if args.command == "tui":
        from .presentation.tui import main as tui_main

        tui_main()
        return 0

    if args.command == "demo-screenshot":
        return run_demo_screenshot(args)
    if args.command == "status":
        return print_status()
    if args.command == "session":
        return run_session(args)
    if args.command == "notification":
        return run_notification(args)
    if args.command == "workflow":
        return run_workflow(args)
    if args.command == "schedule":
        return run_schedule(args)
    if args.command == "server":
        return run_server(args)
    if args.command == "api":
        return run_api(args)
    if args.command == "workspace":
        return run_workspace(args)
    if args.command == "worktree":
        return run_worktree(args)
    if args.command == "tab":
        return run_tab(args)
    if args.command == "pane":
        return run_pane(args)
    if args.command == "agent":
        return run_agent(args)
    if args.command == "wait":
        return run_wait(args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyherdr", description="Python Herdr fork")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("dashboard", help="launch desktop dashboard")
    sub.add_parser("tui", help="launch the live terminal UI (Textual)")
    demo_screenshot = sub.add_parser("demo-screenshot", help="render the Textual TUI with deterministic demo data")
    demo_screenshot.add_argument("--output", default="pyherdr-demo.svg", help="SVG file to write")
    demo_screenshot.add_argument("--width", type=int, default=132, help="terminal columns")
    demo_screenshot.add_argument("--height", type=int, default=38, help="terminal rows")
    demo_screenshot.add_argument(
        "--view",
        choices=["main", "workflow", "fanout", "workspace-picker", "workspace-search"],
        default="main",
        help="demo view to render",
    )
    sub.add_parser("version", help="print version")
    sub.add_parser("status", help="show Python server and saved session status")

    session = sub.add_parser("session", help="named session commands")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    session_sub.add_parser("list")
    session_attach = session_sub.add_parser("attach")
    session_attach.add_argument("name")
    session_stop = session_sub.add_parser("stop")
    session_stop.add_argument("name")
    session_delete = session_sub.add_parser("delete")
    session_delete.add_argument("name")

    notification = sub.add_parser("notification", help="show a notification")
    notification_sub = notification.add_subparsers(dest="notification_command", required=True)
    notification_show = notification_sub.add_parser("show")
    notification_show.add_argument("title")
    notification_show.add_argument("--body", default="")
    notification_show.add_argument(
        "--position",
        default="bottom-right",
        choices=["top-left", "top-right", "bottom-left", "bottom-right"],
    )
    notification_show.add_argument("--sound", default="none", choices=["none", "done", "request"])

    workflow = sub.add_parser("workflow", help="workflow graph and audit-log commands")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_event = workflow_sub.add_parser("event", help="append one workflow event")
    workflow_event.add_argument("kind")
    workflow_event.add_argument("--message", default="")
    workflow_event.add_argument("--source", default="")
    workflow_event.add_argument("--target", default="")
    workflow_event.add_argument("--worksite", default="")
    workflow_event.add_argument("--agent", default="")
    workflow_event.add_argument("--pane-id", default="")
    workflow_event.add_argument("--status", default="")
    workflow_event.add_argument("--artifact", action="append", default=[])
    workflow_event.add_argument(
        "--detail",
        action="append",
        default=[],
        help="key=value metadata; sensitive values are redacted",
    )
    workflow_log = workflow_sub.add_parser("log", help="print recent workflow events as JSON")
    workflow_log.add_argument("--limit", type=int, default=50)
    workflow_graph = workflow_sub.add_parser("graph", help="print workflow graph")
    workflow_graph.add_argument("--limit", type=int, default=100)
    workflow_graph.add_argument("--format", choices=["json", "mermaid", "svg"], default="json")
    workflow_graph.add_argument("--output", help="write graph to a file instead of stdout")

    schedule = sub.add_parser("schedule", help="cron-scheduled pane commands")
    schedule_sub = schedule.add_subparsers(dest="schedule_command", required=True)
    schedule_add = schedule_sub.add_parser("add")
    schedule_add.add_argument("--cron", required=True)
    schedule_add.add_argument("--pane", required=True)
    schedule_add.add_argument("command_parts", nargs=argparse.REMAINDER)
    schedule_sub.add_parser("list")
    schedule_remove = schedule_sub.add_parser("remove")
    schedule_remove.add_argument("id")
    schedule_run = schedule_sub.add_parser("run")
    schedule_run.add_argument("id")

    server = sub.add_parser("server", help="Python server process commands")
    server_sub = server.add_subparsers(dest="server_command", required=True)
    server_sub.add_parser("start")
    server_sub.add_parser("stop")
    server_sub.add_parser("status")
    server_run = server_sub.add_parser("run")
    server_run.add_argument("--host", default="127.0.0.1")
    server_run.add_argument("--port", type=int, default=0)

    api = sub.add_parser("api", help="dispatch one JSON API request")
    api.add_argument("request_json")

    workspace = sub.add_parser("workspace", help="workspace commands")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)
    workspace_sub.add_parser("list")
    workspace_get = workspace_sub.add_parser("get")
    workspace_get.add_argument("workspace_id")
    workspace_create = workspace_sub.add_parser("create")
    workspace_create.add_argument("--label", default="workspace")
    workspace_create.add_argument("--cwd", default=str(Path.cwd()))
    workspace_focus = workspace_sub.add_parser("focus")
    workspace_focus.add_argument("workspace_id")
    workspace_rename = workspace_sub.add_parser("rename")
    workspace_rename.add_argument("workspace_id")
    workspace_rename.add_argument("label")
    workspace_close = workspace_sub.add_parser("close")
    workspace_close.add_argument("workspace_id")
    workspace_recents = workspace_sub.add_parser("recents", help="show or prune recent workspace roots")
    workspace_recents.add_argument("--all", action="store_true", help="include stale roots")
    workspace_recents.add_argument("--json", action="store_true", help="print machine-readable JSON")
    workspace_recents.add_argument("--prune", action="store_true", help="remove stale roots from the recents file")
    workspace_search = workspace_sub.add_parser("search", help="search configured workspace roots")
    workspace_search.add_argument("query")
    workspace_search.add_argument("--json", action="store_true", help="print machine-readable JSON")
    workspace_search.add_argument(
        "--root",
        action="append",
        default=[],
        help="root directory to scan; repeat to scan several roots instead of configured roots",
    )
    workspace_search.add_argument("--max-depth", type=int, help="override workspace.search_max_depth")
    workspace_search.add_argument("--max-results", type=int, help="override workspace.search_max_results")
    workspace_search.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="directory name to skip; repeat to override workspace.search_ignore",
    )
    workspace_search.add_argument("--include-hidden", action="store_true", help="include hidden folders")

    worktree = sub.add_parser("worktree", help="git worktree commands")
    worktree_sub = worktree.add_subparsers(dest="worktree_command", required=True)
    worktree_list = worktree_sub.add_parser("list")
    worktree_list.add_argument("--cwd")
    worktree_create = worktree_sub.add_parser("create")
    worktree_create.add_argument("branch")
    worktree_create.add_argument("--base")
    worktree_create.add_argument("--path")
    worktree_create.add_argument("--label")
    worktree_create.add_argument("--cwd")
    worktree_open = worktree_sub.add_parser("open")
    worktree_open.add_argument("path")
    worktree_open.add_argument("--label")
    worktree_remove = worktree_sub.add_parser("remove")
    worktree_remove.add_argument("path")
    worktree_remove.add_argument("--force", action="store_true")

    tab = sub.add_parser("tab", help="tab commands")
    tab_sub = tab.add_subparsers(dest="tab_command", required=True)
    tab_sub.add_parser("list")
    tab_get = tab_sub.add_parser("get")
    tab_get.add_argument("tab_id")
    tab_get.add_argument("--workspace-id")
    tab_create = tab_sub.add_parser("create")
    tab_create.add_argument("--label", default="shell")
    tab_create.add_argument("--workspace-id")
    tab_focus = tab_sub.add_parser("focus")
    tab_focus.add_argument("tab_id")
    tab_focus.add_argument("--workspace-id")
    tab_rename = tab_sub.add_parser("rename")
    tab_rename.add_argument("tab_id")
    tab_rename.add_argument("label")
    tab_rename.add_argument("--workspace-id")
    tab_close = tab_sub.add_parser("close")
    tab_close.add_argument("tab_id")
    tab_close.add_argument("--workspace-id")
    tab_sync = tab_sub.add_parser("sync")
    tab_sync.add_argument("--tab-id")
    tab_sync.add_argument("--workspace-id")
    tab_sync.add_argument("--off", action="store_true")

    pane = sub.add_parser("pane", help="pane commands")
    pane_sub = pane.add_subparsers(dest="pane_command", required=True)
    pane_sub.add_parser("list")
    pane_get = pane_sub.add_parser("get")
    pane_get.add_argument("pane_id")
    pane_create = pane_sub.add_parser("create")
    pane_create.add_argument("--title", default="pane")
    pane_create.add_argument("--workspace-id")
    pane_create.add_argument("--tab-id")
    pane_read = pane_sub.add_parser("read")
    pane_read.add_argument("pane_id")
    pane_read.add_argument("--lines", type=int, default=80)
    pane_close = pane_sub.add_parser("close")
    pane_close.add_argument("pane_id")
    pane_run = pane_sub.add_parser("run")
    pane_run.add_argument("pane_id")
    pane_run.add_argument("command_parts", nargs=argparse.REMAINDER)
    pane_start = pane_sub.add_parser("start")
    pane_start.add_argument("pane_id")
    pane_start.add_argument("command_parts", nargs=argparse.REMAINDER)
    pane_send_text = pane_sub.add_parser("send-text")
    pane_send_text.add_argument("pane_id")
    pane_send_text.add_argument("text")
    pane_send_key = pane_sub.add_parser("send-key")
    pane_send_key.add_argument("pane_id")
    pane_send_key.add_argument("key", help="key name, e.g. enter, up, f5")
    pane_resize = pane_sub.add_parser("resize")
    pane_resize.add_argument("pane_id")
    pane_resize.add_argument("rows", type=int)
    pane_resize.add_argument("cols", type=int)
    pane_stop = pane_sub.add_parser("stop")
    pane_stop.add_argument("pane_id")
    pane_report = pane_sub.add_parser("report-agent")
    pane_report.add_argument("pane_id")
    pane_report.add_argument("--state", choices=[status.value for status in AgentStatus], required=True)
    pane_report.add_argument("--message", default="")
    pane_broadcast = pane_sub.add_parser("broadcast")
    pane_broadcast.add_argument("text")
    pane_broadcast.add_argument("--scope", default="all", choices=["all", "workspace", "tab"])
    pane_broadcast.add_argument("--no-enter", action="store_true")
    pane_fanout = pane_sub.add_parser("fanout", help="preview or send text to selected panes")
    pane_fanout.add_argument("command_parts", nargs=argparse.REMAINDER)
    pane_fanout.add_argument(
        "--target",
        action="append",
        default=[],
        help="all, session:NAME, workspace:ID, tab:ID, pane:ID, or agent:NAME",
    )
    pane_fanout.add_argument("--all", action="store_true", help="target every pane in the current session")
    pane_fanout.add_argument("--execute", action="store_true", help="send text after previewing targets")
    pane_fanout.add_argument(
        "--confirm-risky",
        action="store_true",
        help="allow executing destructive-looking commands after preview",
    )
    pane_fanout.add_argument("--no-enter", action="store_true", help="insert text without pressing Enter")

    agent = sub.add_parser("agent", help="agent commands (resolve by name or pane id)")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_sub.add_parser("list")
    agent_get = agent_sub.add_parser("get")
    agent_get.add_argument("target")
    agent_read = agent_sub.add_parser("read")
    agent_read.add_argument("target")
    agent_read.add_argument("--lines", type=int, default=80)
    agent_send = agent_sub.add_parser("send")
    agent_send.add_argument("target")
    agent_send.add_argument("text")
    agent_rename = agent_sub.add_parser("rename")
    agent_rename.add_argument("target")
    agent_rename.add_argument("name")
    agent_focus = agent_sub.add_parser("focus")
    agent_focus.add_argument("target")
    agent_start = agent_sub.add_parser("start")
    agent_start.add_argument("name")
    agent_start.add_argument("--cwd")
    agent_start.add_argument("--workspace-id")
    agent_start.add_argument("--tab-id")
    agent_start.add_argument("command_parts", nargs=argparse.REMAINDER)

    wait = sub.add_parser("wait", help="wait for pane output or agent status")
    wait_sub = wait.add_subparsers(dest="wait_command", required=True)
    wait_output = wait_sub.add_parser("output")
    wait_output.add_argument("pane_id")
    wait_output.add_argument("--match", required=True)
    wait_output.add_argument("--lines", type=int, default=200)
    wait_output.add_argument("--timeout", type=int, default=10000, help="milliseconds")
    wait_output.add_argument("--regex", action="store_true")
    wait_status = wait_sub.add_parser("agent-status")
    wait_status.add_argument("pane_id")
    wait_status.add_argument("--status", required=True, choices=[status.value for status in AgentStatus])
    wait_status.add_argument("--timeout", type=int, default=10000, help="milliseconds")

    return parser


def print_status() -> int:
    state = load_state()
    info = read_server_info()
    workspaces = len(state.workspaces)
    tabs = sum(len(workspace.tabs) for workspace in state.workspaces)
    panes = sum(len(tab.panes) for workspace in state.workspaces for tab in workspace.tabs)
    print(
        json.dumps(
            {
                "server": {
                    "running": ping(info),
                    "host": info.host if info else None,
                    "port": info.port if info else None,
                    "pid": info.pid if info else None,
                },
                "session": {"workspaces": workspaces, "tabs": tabs, "panes": panes},
            },
            indent=2,
        )
    )
    return 0


def run_demo_screenshot(args) -> int:
    from .demo_screenshot import render_demo_screenshot

    output = render_demo_screenshot(Path(args.output), width=args.width, height=args.height, view=args.view)
    print(output)
    return 0


def _command_from_parts(parts: list[str]) -> str:
    cleaned = list(parts)
    if cleaned and cleaned[0] == "--":
        cleaned = cleaned[1:]
    return " ".join(cleaned).strip()


def run_schedule(args) -> int:
    if args.schedule_command == "add":
        response = ensure_request(
            {
                "id": "cli",
                "method": "schedule.add",
                "params": {
                    "cron": args.cron,
                    "pane_id": args.pane,
                    "command": " ".join(args.command_parts).strip(),
                },
            }
        )
    elif args.schedule_command == "list":
        response = ensure_request({"id": "cli", "method": "schedule.list", "params": {}})
    elif args.schedule_command == "remove":
        response = ensure_request({"id": "cli", "method": "schedule.remove", "params": {"id": args.id}})
    elif args.schedule_command == "run":
        response = ensure_request({"id": "cli", "method": "schedule.run", "params": {"id": args.id}})
    else:
        return 2
    return print_response(response)


def run_notification(args) -> int:
    response = ensure_request(
        {
            "id": "cli",
            "method": "notification.show",
            "params": {
                "title": args.title,
                "body": args.body,
                "position": args.position,
                "sound": args.sound,
            },
        }
    )
    return print_response(response)


def run_workflow(args) -> int:
    from .workflow import (
        append_event,
        build_graph,
        event_to_dict,
        graph_to_mermaid,
        graph_to_svg,
        new_event,
        read_events,
    )

    if args.workflow_command == "event":
        details: dict[str, str] = {}
        for item in args.detail:
            if "=" not in item:
                print(f"invalid detail {item!r}; expected key=value", file=sys.stderr)
                return 2
            key, value = item.split("=", 1)
            details[key] = value
        event = new_event(
            args.kind,
            message=args.message,
            source=args.source,
            target=args.target,
            worksite=args.worksite,
            agent=args.agent,
            pane_id=args.pane_id,
            status=args.status,
            details=details,
            artifacts=args.artifact,
        )
        append_event(event)
        print(json.dumps({"event": event_to_dict(event)}, indent=2))
        return 0
    if args.workflow_command == "log":
        events = read_events(limit=args.limit)
        print(json.dumps({"events": [event_to_dict(event) for event in events]}, indent=2))
        return 0
    if args.workflow_command == "graph":
        graph = build_graph(read_events(limit=args.limit))
        if args.format == "mermaid":
            output = graph_to_mermaid(graph)
        elif args.format == "svg":
            output = graph_to_svg(graph)
        else:
            output = json.dumps(graph, indent=2)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output, encoding="utf-8")
            print(output_path)
        else:
            print(output)
        return 0
    return 2


def run_session(args) -> int:
    if args.session_command == "list":
        sessions = []
        for name in list_session_names():
            info = read_server_info(session_runtime_dir(name) / "server.json")
            sessions.append({"name": name, "running": ping(info) if info else False})
        print(json.dumps({"sessions": sessions}, indent=2))
        return 0
    if args.session_command == "attach":
        os.environ["PYHERDR_SESSION"] = args.name
        from .presentation.tui import main as tui_main

        tui_main()
        return 0
    if args.session_command == "stop":
        info = read_server_info(session_runtime_dir(args.name) / "server.json")
        stopped = False
        if info and ping(info):
            try:
                request(info, {"id": "cli", "method": "server.stop", "params": {}}, timeout=1.0)
                stopped = True
            except (OSError, ConnectionError, json.JSONDecodeError):
                stopped = False
        remove_server_info(session_runtime_dir(args.name) / "server.json")
        print(json.dumps({"stopped": stopped}, indent=2))
        return 0 if stopped else 1
    if args.session_command == "delete":
        if args.name == DEFAULT_SESSION:
            print("cannot delete the default session", file=sys.stderr)
            return 2
        info = read_server_info(session_runtime_dir(args.name) / "server.json")
        if info and ping(info):
            try:
                request(info, {"id": "cli", "method": "server.stop", "params": {}}, timeout=1.0)
            except (OSError, ConnectionError, json.JSONDecodeError):
                pass
        shutil.rmtree(session_runtime_dir(args.name), ignore_errors=True)
        print(json.dumps({"deleted": args.name}, indent=2))
        return 0
    return 2


def run_server(args) -> int:
    info: ServerInfo | None
    if args.server_command == "run":
        return run_foreground(args.host, args.port)
    if args.server_command == "start":
        info = start_background()
        shown = {key: value for key, value in info.to_dict().items() if key != "token"}
        print(json.dumps({"running": True, **shown}, indent=2))
        return 0
    if args.server_command == "stop":
        stopped = stop_running()
        print(json.dumps({"stopped": stopped}, indent=2))
        return 0 if stopped else 1
    if args.server_command == "status":
        info = read_server_info()
        running = ping(info)
        print(
            json.dumps(
                {
                    "running": running,
                    "host": info.host if info and running else None,
                    "port": info.port if info and running else None,
                    "pid": info.pid if info and running else None,
                },
                indent=2,
            )
        )
        return 0
    return 2


def run_api(args) -> int:
    try:
        request = json.loads(args.request_json)
    except json.JSONDecodeError as error:
        print(f"invalid JSON: {error}", file=sys.stderr)
        return 2
    return print_response(ensure_request(request))


def run_workspace(args) -> int:
    if args.workspace_command == "list":
        response = ensure_request({"id": "cli", "method": "workspace.list", "params": {}})
    elif args.workspace_command == "get":
        response = ensure_request(
            {
                "id": "cli",
                "method": "workspace.get",
                "params": {"workspace_id": args.workspace_id},
            }
        )
    elif args.workspace_command == "create":
        response = ensure_request(
            {
                "id": "cli",
                "method": "workspace.create",
                "params": {"label": args.label, "cwd": args.cwd},
            },
        )
    elif args.workspace_command == "focus":
        response = ensure_request(
            {
                "id": "cli",
                "method": "workspace.focus",
                "params": {"workspace_id": args.workspace_id},
            },
        )
    elif args.workspace_command == "rename":
        response = ensure_request(
            {
                "id": "cli",
                "method": "workspace.rename",
                "params": {"workspace_id": args.workspace_id, "label": args.label},
            }
        )
    elif args.workspace_command == "close":
        response = ensure_request(
            {
                "id": "cli",
                "method": "workspace.close",
                "params": {"workspace_id": args.workspace_id},
            }
        )
    elif args.workspace_command == "recents":
        return run_workspace_recents(args)
    elif args.workspace_command == "search":
        return run_workspace_search(args)
    else:
        return 2
    return print_response(response)


def run_workspace_recents(args) -> int:
    if args.prune:
        summary = prune_workspace_recents()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"removed {summary['removed']} stale recent workspace root(s); kept {summary['kept']}")
        return 0
    records = load_workspace_recents(include_stale=args.all)
    if args.json:
        print(json.dumps({"roots": records}, indent=2))
        return 0
    if not records:
        print("no recent workspace roots")
        return 0
    for record in records:
        suffix = " [stale]" if record["stale"] else ""
        print(f"{record['label']}\t{record['path']}{suffix}")
    return 0


def run_workspace_search(args) -> int:
    config = load_config()
    roots = _workspace_search_roots(args.root, config.workspace.search_roots)
    ignore_names = tuple(args.ignore) if args.ignore else tuple(config.workspace.search_ignore)
    max_depth = config.workspace.search_max_depth if args.max_depth is None else args.max_depth
    max_results = config.workspace.search_max_results if args.max_results is None else args.max_results
    include_hidden = bool(args.include_hidden or config.workspace.search_include_hidden)
    rows = search_workspace_rows(
        args.query,
        roots,
        max_depth=max(0, max_depth),
        max_results=max(1, max_results),
        ignore_names=ignore_names,
        include_hidden=include_hidden,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "query": args.query,
                    "roots": [root.__dict__ for root in roots],
                    "results": [row_to_dict(row) for row in rows],
                },
                indent=2,
            )
        )
        return 0
    if not rows:
        print("no matching workspace roots")
        return 0
    for row in rows:
        stale = " [stale]" if row.stale else ""
        print(f"{row.kind}\t{row.label}\t{row.path}{stale}")
    return 0


def _workspace_search_roots(cli_roots: list[str], configured_roots: list[str]) -> list[SearchRoot]:
    raw_roots = cli_roots or configured_roots
    roots: list[SearchRoot] = []
    if raw_roots:
        for raw_path in raw_roots:
            path = _expand_search_root(raw_path)
            if path:
                source = "cli" if cli_roots else "configured"
                roots.append(SearchRoot(path, label=_search_root_label(path), source=source))
    else:
        roots.append(SearchRoot(str(Path.cwd()), label="process cwd", source="current"))
        home = Path.home()
        for name in ("github", "code", "src", "work"):
            candidate = home / name
            if candidate.is_dir():
                roots.append(SearchRoot(str(candidate), label=name, source="configured"))
        for recent in load_workspace_recents():
            roots.append(SearchRoot(str(recent["path"]), label=str(recent["label"]), source="recent"))
    return _dedupe_search_roots(roots)


def _expand_search_root(path: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(path.strip()))
    return str(Path(expanded).resolve()) if expanded else ""


def _search_root_label(path: str) -> str:
    return Path(path).name or path


def _dedupe_search_roots(roots: list[SearchRoot]) -> list[SearchRoot]:
    deduped: list[SearchRoot] = []
    seen: set[str] = set()
    for root in roots:
        key = os.path.normcase(root.path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def run_worktree(args) -> int:
    if args.worktree_command == "list":
        response = ensure_request({"id": "cli", "method": "worktree.list", "params": {"cwd": args.cwd}})
    elif args.worktree_command == "create":
        response = ensure_request(
            {
                "id": "cli",
                "method": "worktree.create",
                "params": {
                    "branch": args.branch,
                    "base": args.base,
                    "path": args.path,
                    "label": args.label,
                    "cwd": args.cwd,
                },
            }
        )
    elif args.worktree_command == "open":
        response = ensure_request(
            {"id": "cli", "method": "worktree.open", "params": {"path": args.path, "label": args.label}}
        )
    elif args.worktree_command == "remove":
        response = ensure_request(
            {"id": "cli", "method": "worktree.remove", "params": {"path": args.path, "force": args.force}}
        )
    else:
        return 2
    return print_response(response)


def run_tab(args) -> int:
    if args.tab_command == "list":
        response = ensure_request({"id": "cli", "method": "tab.list", "params": {}})
    elif args.tab_command == "get":
        response = ensure_request(
            {
                "id": "cli",
                "method": "tab.get",
                "params": {"tab_id": args.tab_id, "workspace_id": args.workspace_id},
            }
        )
    elif args.tab_command == "create":
        response = ensure_request(
            {
                "id": "cli",
                "method": "tab.create",
                "params": {"label": args.label, "workspace_id": args.workspace_id},
            },
        )
    elif args.tab_command == "focus":
        response = ensure_request(
            {
                "id": "cli",
                "method": "tab.focus",
                "params": {"tab_id": args.tab_id, "workspace_id": args.workspace_id},
            },
        )
    elif args.tab_command == "rename":
        response = ensure_request(
            {
                "id": "cli",
                "method": "tab.rename",
                "params": {"tab_id": args.tab_id, "label": args.label, "workspace_id": args.workspace_id},
            }
        )
    elif args.tab_command == "close":
        response = ensure_request(
            {
                "id": "cli",
                "method": "tab.close",
                "params": {"tab_id": args.tab_id, "workspace_id": args.workspace_id},
            }
        )
    elif args.tab_command == "sync":
        response = ensure_request(
            {
                "id": "cli",
                "method": "tab.sync",
                "params": {"tab_id": args.tab_id, "workspace_id": args.workspace_id, "enabled": not args.off},
            }
        )
    else:
        return 2
    return print_response(response)


def run_pane(args) -> int:
    if args.pane_command == "list":
        response = ensure_request({"id": "cli", "method": "pane.list", "params": {}})
        return print_response(response)
    if args.pane_command == "get":
        response = ensure_request({"id": "cli", "method": "pane.get", "params": {"pane_id": args.pane_id}})
        return print_response(response)
    if args.pane_command == "create":
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.create",
                "params": {"title": args.title, "workspace_id": args.workspace_id, "tab_id": args.tab_id},
            }
        )
        return print_response(response)
    if args.pane_command == "read":
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.read",
                "params": {"pane_id": args.pane_id, "lines": args.lines},
            },
        )
        return print_response(response)
    if args.pane_command == "close":
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.close",
                "params": {"pane_id": args.pane_id},
            }
        )
        return print_response(response)
    if args.pane_command == "report-agent":
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.report_agent",
                "params": {"pane_id": args.pane_id, "state": args.state, "message": args.message},
            },
        )
        return print_response(response)
    if args.pane_command == "broadcast":
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.broadcast",
                "params": {"text": args.text, "scope": args.scope, "enter": not args.no_enter},
            }
        )
        return print_response(response)
    if args.pane_command == "fanout":
        command = _command_from_parts(args.command_parts)
        targets = (["all"] if args.all else []) + list(args.target)
        if not command:
            print("missing command", file=sys.stderr)
            return 2
        if not targets:
            print("missing target: pass --all or one or more --target selectors", file=sys.stderr)
            return 2
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.fanout",
                "params": {
                    "targets": targets,
                    "text": command,
                    "enter": not args.no_enter,
                    "dry_run": not args.execute,
                    "confirm_risky": args.confirm_risky,
                },
            }
        )
        return print_response(response)
    if args.pane_command == "run":
        command = " ".join(args.command_parts).strip()
        if not command:
            print("missing command", file=sys.stderr)
            return 2
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.run",
                "params": {"pane_id": args.pane_id, "command": command},
            }
        )
        return print_response(response)
    if args.pane_command == "start":
        command = " ".join(args.command_parts).strip()
        if not command:
            print("missing command", file=sys.stderr)
            return 2
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.start",
                "params": {"pane_id": args.pane_id, "command": command},
            }
        )
        return print_response(response)
    if args.pane_command == "send-text":
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.send_text",
                "params": {"pane_id": args.pane_id, "text": args.text},
            }
        )
        return print_response(response)
    if args.pane_command == "send-key":
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.send_key",
                "params": {"pane_id": args.pane_id, "key": args.key},
            }
        )
        return print_response(response)
    if args.pane_command == "resize":
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.resize",
                "params": {"pane_id": args.pane_id, "rows": args.rows, "cols": args.cols},
            }
        )
        return print_response(response)
    if args.pane_command == "stop":
        response = ensure_request(
            {
                "id": "cli",
                "method": "pane.stop",
                "params": {"pane_id": args.pane_id},
            }
        )
        return print_response(response)
    return 2


def run_agent(args) -> int:
    if args.agent_command == "list":
        response = ensure_request({"id": "cli", "method": "agent.list", "params": {}})
    elif args.agent_command == "get":
        response = ensure_request({"id": "cli", "method": "agent.get", "params": {"target": args.target}})
    elif args.agent_command == "read":
        response = ensure_request(
            {"id": "cli", "method": "agent.read", "params": {"target": args.target, "lines": args.lines}}
        )
    elif args.agent_command == "send":
        response = ensure_request(
            {"id": "cli", "method": "agent.send", "params": {"target": args.target, "text": args.text}}
        )
    elif args.agent_command == "rename":
        response = ensure_request(
            {"id": "cli", "method": "agent.rename", "params": {"target": args.target, "name": args.name}}
        )
    elif args.agent_command == "focus":
        response = ensure_request({"id": "cli", "method": "agent.focus", "params": {"target": args.target}})
    elif args.agent_command == "start":
        response = ensure_request(
            {
                "id": "cli",
                "method": "agent.start",
                "params": {
                    "name": args.name,
                    "command": " ".join(args.command_parts).strip(),
                    "cwd": args.cwd,
                    "workspace_id": args.workspace_id,
                    "tab_id": args.tab_id,
                },
            }
        )
    else:
        return 2
    return print_response(response)


def run_wait(args) -> int:
    deadline = time.monotonic() + args.timeout / 1000.0
    if args.wait_command == "output":
        pattern = re.compile(args.match) if args.regex else None
        output = ""
        while time.monotonic() < deadline:
            response = ensure_request(
                {"id": "cli", "method": "pane.read", "params": {"pane_id": args.pane_id, "lines": args.lines}}
            )
            output = response.get("result", {}).get("output", "")
            matched = pattern.search(output) is not None if pattern else args.match in output
            if matched:
                print(json.dumps({"matched": True, "pane_id": args.pane_id}, indent=2))
                return 0
            time.sleep(0.2)
        print(json.dumps({"matched": False, "pane_id": args.pane_id}, indent=2))
        return 1
    if args.wait_command == "agent-status":
        status = None
        while time.monotonic() < deadline:
            response = ensure_request(
                {"id": "cli", "method": "pane.get", "params": {"pane_id": args.pane_id}}
            )
            status = response.get("result", {}).get("pane", {}).get("agent_status")
            if status == args.status:
                print(json.dumps({"reached": True, "status": status}, indent=2))
                return 0
            time.sleep(0.2)
        print(json.dumps({"reached": False, "status": status}, indent=2))
        return 1
    return 2


def print_response(response) -> int:
    print(json.dumps(response, indent=2))
    return 1 if "error" in response else 0


if __name__ == "__main__":
    raise SystemExit(main())
