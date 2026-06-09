from __future__ import annotations

import queue
import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .detector import detect_agent_status
from .models import AgentStatus, AppState, Pane
from .runtime import CommandRunner
from .store import load_state, save_state

STATUS_COLORS = {
    AgentStatus.BLOCKED: "#d73a49",
    AgentStatus.WORKING: "#d29922",
    AgentStatus.DONE: "#2f81f7",
    AgentStatus.IDLE: "#2ea043",
    AgentStatus.UNKNOWN: "#6e7681",
}


class HerdrDashboard(tk.Tk):
    def __init__(self, state: AppState | None = None) -> None:
        super().__init__()
        self.title("PyHerdr")
        self.geometry("1180x760")
        self.minsize(900, 560)

        self.app_state = state or load_state()
        self.runner = CommandRunner()
        self.events: queue.Queue[tuple[str, str, object]] = queue.Queue()
        self.selected_pane_id: str | None = None
        self.tab_buttons: dict[str, ttk.Button] = {}

        self._configure_style()
        self._build_layout()
        self._bind_events()
        self.refresh_all()
        self.after(120, self._drain_events)

    def _configure_style(self) -> None:
        self.configure(bg="#0f1419")
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#0f1419", foreground="#d0d7de")
        style.configure("TFrame", background="#0f1419")
        style.configure("Sidebar.TFrame", background="#111820")
        style.configure("Panel.TFrame", background="#151b23")
        style.configure("TLabel", background="#0f1419", foreground="#d0d7de")
        style.configure("Muted.TLabel", foreground="#8b949e")
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"), foreground="#f0f6fc")
        style.configure("TButton", padding=(10, 6), background="#21262d", foreground="#f0f6fc")
        style.map("TButton", background=[("active", "#30363d")])
        style.configure("Treeview", background="#0d1117", foreground="#d0d7de", fieldbackground="#0d1117")
        style.configure("Treeview.Heading", background="#21262d", foreground="#f0f6fc")
        style.map("Treeview", background=[("selected", "#1f6feb")], foreground=[("selected", "#ffffff")])

    def _build_layout(self) -> None:
        root = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        root.pack(fill=tk.BOTH, expand=True)

        sidebar = ttk.Frame(root, style="Sidebar.TFrame", width=280)
        root.add(sidebar, weight=0)

        main = ttk.Frame(root, style="Panel.TFrame")
        root.add(main, weight=1)

        self._build_sidebar(sidebar)
        self._build_main(main)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="Sidebar.TFrame")
        header.pack(fill=tk.X, padx=12, pady=(14, 8))
        ttk.Label(header, text="PyHerdr", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(header, text="workspace dashboard", style="Muted.TLabel").pack(anchor=tk.W)

        actions = ttk.Frame(parent, style="Sidebar.TFrame")
        actions.pack(fill=tk.X, padx=12, pady=(0, 10))
        ttk.Button(actions, text="New workspace", command=self.new_workspace).pack(fill=tk.X, pady=3)
        ttk.Button(actions, text="New tab", command=self.new_tab).pack(fill=tk.X, pady=3)
        ttk.Button(actions, text="New pane", command=self.new_pane).pack(fill=tk.X, pady=3)

        columns = ("status", "cwd")
        self.workspace_tree = ttk.Treeview(parent, columns=columns, show="tree headings", height=18)
        self.workspace_tree.heading("#0", text="Workspace")
        self.workspace_tree.heading("status", text="State")
        self.workspace_tree.heading("cwd", text="Path")
        self.workspace_tree.column("#0", width=116, stretch=False)
        self.workspace_tree.column("status", width=74, stretch=False)
        self.workspace_tree.column("cwd", width=180)
        self.workspace_tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

    def _build_main(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style="Panel.TFrame")
        top.pack(fill=tk.X, padx=16, pady=(14, 10))
        self.title_label = ttk.Label(top, text="", style="Title.TLabel")
        self.title_label.pack(side=tk.LEFT)
        ttk.Button(top, text="Save", command=self.save).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(top, text="Choose cwd", command=self.choose_cwd).pack(side=tk.RIGHT)

        self.status_bar = ttk.Frame(parent, style="Panel.TFrame")
        self.status_bar.pack(fill=tk.X, padx=16, pady=(0, 10))

        self.tabs_bar = ttk.Frame(parent, style="Panel.TFrame")
        self.tabs_bar.pack(fill=tk.X, padx=16, pady=(0, 10))

        body = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        pane_panel = ttk.Frame(body, style="Panel.TFrame")
        body.add(pane_panel, weight=1)
        self._build_pane_panel(pane_panel)

        output_panel = ttk.Frame(body, style="Panel.TFrame")
        body.add(output_panel, weight=2)
        self._build_output_panel(output_panel)

    def _build_pane_panel(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent, style="Panel.TFrame")
        controls.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(controls, text="Command").pack(side=tk.LEFT)
        self.command_var = tk.StringVar(value="python --version")
        command_entry = ttk.Entry(controls, textvariable=self.command_var)
        command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(controls, text="Run", command=self.run_command).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(controls, text="Stop", command=self.stop_command).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(controls, text="Blocked", command=lambda: self.set_status(AgentStatus.BLOCKED)).pack(side=tk.LEFT)
        done_button = ttk.Button(controls, text="Done", command=lambda: self.set_status(AgentStatus.DONE))
        done_button.pack(side=tk.LEFT, padx=(6, 0))

        columns = ("title", "status", "command", "cwd")
        self.pane_tree = ttk.Treeview(parent, columns=columns, show="headings", height=8)
        for key, label, width in (
            ("title", "Pane", 140),
            ("status", "State", 90),
            ("command", "Command", 280),
            ("cwd", "Path", 360),
        ):
            self.pane_tree.heading(key, text=label)
            self.pane_tree.column(key, width=width, stretch=True)
        self.pane_tree.pack(fill=tk.BOTH, expand=True)

    def _build_output_panel(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="Panel.TFrame")
        header.pack(fill=tk.X)
        self.output_title = ttk.Label(header, text="Output", style="Title.TLabel")
        self.output_title.pack(side=tk.LEFT)
        ttk.Button(header, text="Clear", command=self.clear_output).pack(side=tk.RIGHT)

        self.output_text = tk.Text(
            parent,
            wrap=tk.WORD,
            bg="#0d1117",
            fg="#d0d7de",
            insertbackground="#f0f6fc",
            relief=tk.FLAT,
            padx=10,
            pady=10,
            font=("Cascadia Mono", 10),
        )
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    def _bind_events(self) -> None:
        self.workspace_tree.bind("<<TreeviewSelect>>", self._on_workspace_selected)
        self.pane_tree.bind("<<TreeviewSelect>>", self._on_pane_selected)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def refresh_all(self) -> None:
        self.refresh_workspaces()
        self.refresh_header()
        self.refresh_status_bar()
        self.refresh_tabs()
        self.refresh_panes()
        self.refresh_output()

    def refresh_workspaces(self) -> None:
        self.workspace_tree.delete(*self.workspace_tree.get_children())
        for workspace in self.app_state.workspaces:
            self.workspace_tree.insert(
                "",
                tk.END,
                iid=workspace.id,
                text=workspace.label,
                values=(workspace.status.value, workspace.cwd),
            )
        if self.app_state.focused_workspace_id:
            self.workspace_tree.selection_set(self.app_state.focused_workspace_id)

    def refresh_header(self) -> None:
        workspace = self.app_state.focused_workspace
        if workspace is None:
            self.title_label.configure(text="No workspace")
            return
        self.title_label.configure(text=f"{workspace.label}  |  {workspace.cwd}")

    def refresh_status_bar(self) -> None:
        for child in self.status_bar.winfo_children():
            child.destroy()
        counts = {status: 0 for status in AgentStatus}
        for pane in self._all_panes():
            counts[pane.status] += 1
        for status in (AgentStatus.BLOCKED, AgentStatus.WORKING, AgentStatus.DONE, AgentStatus.IDLE):
            label = tk.Label(
                self.status_bar,
                text=f"{status.value}: {counts[status]}",
                bg=STATUS_COLORS[status],
                fg="#ffffff",
                padx=12,
                pady=5,
            )
            label.pack(side=tk.LEFT, padx=(0, 8))

    def refresh_tabs(self) -> None:
        for child in self.tabs_bar.winfo_children():
            child.destroy()
        workspace = self.app_state.focused_workspace
        if workspace is None:
            return
        for tab in workspace.tabs:
            text = f"{tab.label} ({tab.status.value})"
            button = ttk.Button(self.tabs_bar, text=text, command=partial(self.focus_tab, tab.id))
            button.pack(side=tk.LEFT, padx=(0, 8))

    def refresh_panes(self) -> None:
        self.pane_tree.delete(*self.pane_tree.get_children())
        tab = self._focused_tab()
        if tab is None:
            return
        for pane in tab.panes:
            self.pane_tree.insert(
                "",
                tk.END,
                iid=pane.id,
                values=(pane.title, pane.status.value, pane.command, pane.cwd),
            )
        if tab.focused_pane_id:
            self.selected_pane_id = tab.focused_pane_id
            self.pane_tree.selection_set(tab.focused_pane_id)

    def refresh_output(self) -> None:
        pane = self._selected_pane()
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        if pane is None:
            self.output_title.configure(text="Output")
        else:
            self.output_title.configure(text=f"Output - {pane.title} [{pane.status.value}]")
            self.output_text.insert(tk.END, "\n".join(pane.output))
            self.output_text.see(tk.END)
            if pane.command:
                self.command_var.set(pane.command)
        self.output_text.configure(state=tk.DISABLED)

    def new_workspace(self) -> None:
        label = simpledialog.askstring("New workspace", "Workspace name:", parent=self)
        if label is None:
            return
        cwd = filedialog.askdirectory(title="Workspace folder") or str(Path.cwd())
        workspace = self.app_state.create_workspace(label, cwd)
        self.app_state.create_tab(workspace.id, "shell")
        self.refresh_all()

    def new_tab(self) -> None:
        workspace = self.app_state.focused_workspace
        if workspace is None:
            return
        label = simpledialog.askstring("New tab", "Tab name:", parent=self) or "shell"
        self.app_state.create_tab(workspace.id, label)
        self.refresh_all()

    def new_pane(self) -> None:
        workspace = self.app_state.focused_workspace
        tab = self._focused_tab()
        if workspace is None or tab is None:
            return
        title = simpledialog.askstring("New pane", "Pane title:", parent=self) or "pane"
        self.app_state.create_pane(workspace.id, tab.id, title)
        self.refresh_all()

    def choose_cwd(self) -> None:
        workspace = self.app_state.focused_workspace
        if workspace is None:
            return
        cwd = filedialog.askdirectory(title="Workspace folder", initialdir=workspace.cwd)
        if not cwd:
            return
        workspace.cwd = cwd
        for tab in workspace.tabs:
            for pane in tab.panes:
                pane.cwd = cwd
        self.refresh_all()

    def run_command(self) -> None:
        pane = self._selected_pane()
        if pane is None:
            messagebox.showinfo("No pane selected", "Select a pane before running a command.")
            return
        command = self.command_var.get().strip()
        if not command:
            return
        pane.command = command
        pane.status = AgentStatus.WORKING
        pane.append_output(f"$ {command}")
        started = self.runner.start(
            pane.id,
            command,
            pane.cwd,
            on_output=partial(self._enqueue, "output", pane.id),
            on_exit=partial(self._enqueue, "exit", pane.id),
        )
        if not started:
            messagebox.showwarning("Already running", "That pane already has a running command.")
        self.refresh_all()

    def stop_command(self) -> None:
        if self.selected_pane_id:
            self.runner.stop(self.selected_pane_id)

    def set_status(self, status: AgentStatus) -> None:
        pane = self._selected_pane()
        if pane is None:
            return
        pane.status = status
        self.refresh_all()

    def clear_output(self) -> None:
        pane = self._selected_pane()
        if pane is None:
            return
        pane.output.clear()
        self.refresh_output()

    def save(self) -> None:
        path = save_state(self.app_state)
        messagebox.showinfo("Saved", f"Session saved to {path}")

    def focus_tab(self, tab_id: str) -> None:
        workspace = self.app_state.focused_workspace
        if workspace is None:
            return
        workspace.focused_tab_id = tab_id
        tab = workspace.focused_tab
        self.selected_pane_id = tab.focused_pane_id if tab else None
        self.refresh_all()

    def on_close(self) -> None:
        save_state(self.app_state)
        self.runner.stop_all()
        self.destroy()

    def _on_workspace_selected(self, _event: object) -> None:
        selected = self.workspace_tree.selection()
        if not selected:
            return
        self.app_state.focused_workspace_id = selected[0]
        tab = self._focused_tab()
        self.selected_pane_id = tab.focused_pane_id if tab else None
        self.refresh_all()

    def _on_pane_selected(self, _event: object) -> None:
        selected = self.pane_tree.selection()
        if not selected:
            return
        self.selected_pane_id = selected[0]
        tab = self._focused_tab()
        if tab is not None:
            tab.focused_pane_id = self.selected_pane_id
        self.refresh_output()

    def _enqueue(self, kind: str, pane_id: str, payload: object) -> None:
        self.events.put((kind, pane_id, payload))

    def _drain_events(self) -> None:
        changed = False
        while True:
            try:
                kind, pane_id, payload = self.events.get_nowait()
            except queue.Empty:
                break
            pane = self.app_state.require_pane(pane_id)
            if kind == "output":
                pane.append_output(str(payload))
                pane.status = detect_agent_status("\n".join(pane.output))
            elif kind == "exit":
                if pane.status != AgentStatus.BLOCKED:
                    pane.status = AgentStatus.DONE if payload == 0 else AgentStatus.BLOCKED
                pane.append_output(f"[exit {payload}]")
            changed = True
        if changed:
            self.refresh_all()
        self.after(120, self._drain_events)

    def _focused_tab(self):
        workspace = self.app_state.focused_workspace
        return workspace.focused_tab if workspace else None

    def _selected_pane(self) -> Pane | None:
        if not self.selected_pane_id:
            tab = self._focused_tab()
            self.selected_pane_id = tab.focused_pane_id if tab else None
        if not self.selected_pane_id:
            return None
        try:
            return self.app_state.require_pane(self.selected_pane_id)
        except KeyError:
            return None

    def _all_panes(self) -> list[Pane]:
        panes: list[Pane] = []
        for workspace in self.app_state.workspaces:
            for tab in workspace.tabs:
                panes.extend(tab.panes)
        return panes


def main() -> None:
    app = HerdrDashboard()
    app.mainloop()
