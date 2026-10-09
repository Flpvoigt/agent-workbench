from __future__ import annotations

import queue
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from agent_workbench.models import AgentSession, RepositoryStatus
from agent_workbench.services import (
    discover_sessions,
    inspect_repository,
    list_codex_processes,
    load_repository_paths,
    open_folder,
    resume_session,
    save_repository_paths,
)


BG = "#101418"
PANEL = "#182027"
TEXT = "#e7edf2"
MUTED = "#93a4b1"
ACCENT = "#5ee6a8"
WARNING = "#ffcc66"


class AgentWorkbench(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Agent Workbench")
        self.geometry("1120x700")
        self.minsize(880, 560)
        self.configure(bg=BG)

        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="workbench")
        self._results: queue.Queue[tuple[str, object]] = queue.Queue()
        self._refreshing = False
        self._sessions: dict[str, AgentSession] = {}
        self._repositories: dict[str, RepositoryStatus] = {}
        self._repository_paths = load_repository_paths()

        self._configure_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_results)
        self.after(250, self.refresh)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22), foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Metric.TLabel", font=("Segoe UI Semibold", 20), foreground=ACCENT)
        style.configure("TButton", padding=(12, 7), background=PANEL, foreground=TEXT)
        style.map("TButton", background=[("active", "#26333d")])
        style.configure("Treeview", background=PANEL, foreground=TEXT, fieldbackground=PANEL, rowheight=28)
        style.configure("Treeview.Heading", background="#222d35", foreground=TEXT, font=("Segoe UI Semibold", 9))
        style.map("Treeview", background=[("selected", "#285840")], foreground=[("selected", "#ffffff")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(15, 8), background=PANEL, foreground=MUTED)
        style.map("TNotebook.Tab", background=[("selected", "#285840")], foreground=[("selected", "#ffffff")])

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(22, 18, 22, 10))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Agent Workbench", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Atualizar", command=self.refresh).pack(side=tk.RIGHT)

        metrics = ttk.Frame(self, style="Panel.TFrame", padding=16)
        metrics.pack(fill=tk.X, padx=22, pady=(0, 14))
        self.active_value = ttk.Label(metrics, text="0", style="Metric.TLabel")
        self.active_value.grid(row=0, column=0, sticky="w", padx=(0, 80))
        self.session_value = ttk.Label(metrics, text="0", style="Metric.TLabel")
        self.session_value.grid(row=0, column=1, sticky="w", padx=(0, 80))
        self.repo_value = ttk.Label(metrics, text="0", style="Metric.TLabel")
        self.repo_value.grid(row=0, column=2, sticky="w")
        ttk.Label(metrics, text="processos Codex", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(metrics, text="sessões locais", style="Muted.TLabel").grid(row=1, column=1, sticky="w")
        ttk.Label(metrics, text="repositórios", style="Muted.TLabel").grid(row=1, column=2, sticky="w")

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=22, pady=(0, 10))
        self._build_sessions_tab(notebook)
        self._build_repositories_tab(notebook)

        self.status = ttk.Label(self, text="Preparando…", style="Muted.TLabel", padding=(22, 4, 22, 12))
        self.status.pack(fill=tk.X)

    def _build_sessions_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Sessões")
        columns = ("state", "updated", "size", "summary")
        self.sessions_tree = ttk.Treeview(tab, columns=columns, show="headings")
        headings = {"state": "Estado", "updated": "Atualizada", "size": "Tamanho", "summary": "Resumo"}
        widths = {"state": 90, "updated": 145, "size": 90, "summary": 600}
        for column in columns:
            self.sessions_tree.heading(column, text=headings[column])
            self.sessions_tree.column(column, width=widths[column], anchor="w")
        self.sessions_tree.pack(fill=tk.BOTH, expand=True)
        buttons = ttk.Frame(tab, padding=(0, 10, 0, 0))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Retomar sessão", command=self._resume_selected).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Abrir localização", command=self._open_session_location).pack(side=tk.LEFT, padx=8)

    def _build_repositories_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Git e GitHub")
        columns = ("branch", "changes", "prs", "remote", "status")
        self.repos_tree = ttk.Treeview(tab, columns=columns, show="tree headings")
        self.repos_tree.heading("#0", text="Repositório")
        self.repos_tree.column("#0", width=180, anchor="w")
        labels = {"branch": "Branch", "changes": "Alterações", "prs": "PRs abertos", "remote": "Remote", "status": "Status"}
        widths = {"branch": 130, "changes": 90, "prs": 90, "remote": 410, "status": 180}
        for column in columns:
            self.repos_tree.heading(column, text=labels[column])
            self.repos_tree.column(column, width=widths[column], anchor="w")
        self.repos_tree.pack(fill=tk.BOTH, expand=True)
        buttons = ttk.Frame(tab, padding=(0, 10, 0, 0))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Adicionar repositório", command=self._add_repository).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Remover", command=self._remove_repository).pack(side=tk.LEFT, padx=8)
        ttk.Button(buttons, text="Abrir pasta", command=self._open_repository).pack(side=tk.LEFT)

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self.status.configure(text="Atualizando dados locais…")
        self._executor.submit(self._collect_data)

    def _collect_data(self) -> None:
        sessions = discover_sessions()
        processes = list_codex_processes()
        repositories = [inspect_repository(path) for path in self._repository_paths]
        self._results.put(("refresh", (sessions, processes, repositories)))

    def _drain_results(self) -> None:
        try:
            while True:
                kind, payload = self._results.get_nowait()
                if kind == "refresh":
                    sessions, processes, repositories = payload  # type: ignore[misc]
                    self._render(sessions, processes, repositories)
        except queue.Empty:
            pass
        self.after(100, self._drain_results)

    def _render(
        self,
        sessions: list[AgentSession],
        processes: list[object],
        repositories: list[RepositoryStatus],
    ) -> None:
        self._refreshing = False
        self._sessions = {item.session_id: item for item in sessions}
        self._repositories = {str(item.path): item for item in repositories}
        self.active_value.configure(text=str(len(processes)))
        self.session_value.configure(text=str(len(sessions)))
        self.repo_value.configure(text=str(len(repositories)))

        self.sessions_tree.delete(*self.sessions_tree.get_children())
        for item in sessions[:250]:
            state = "ATIVA" if item.active else "ociosa"
            size = self._format_size(item.size_bytes)
            summary = item.summary or item.session_id
            self.sessions_tree.insert(
                "",
                tk.END,
                iid=item.session_id,
                values=(state, item.modified_at.strftime("%d/%m/%Y %H:%M"), size, summary),
            )

        self.repos_tree.delete(*self.repos_tree.get_children())
        for item in repositories:
            status = item.error or ("Protegida por PR" if item.branch not in {"main", "master"} else "Na branch principal")
            prs = "—" if item.pull_requests is None else str(item.pull_requests)
            self.repos_tree.insert(
                "",
                tk.END,
                iid=str(item.path),
                text=item.name,
                values=(item.branch, item.dirty_files, prs, item.remote, status),
            )
        self.status.configure(text=f"Atualizado às {datetime.now():%H:%M:%S}. Atualização automática em 10 s.")
        self.after(10_000, self.refresh)

    @staticmethod
    def _format_size(value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    def _selected_session(self) -> AgentSession | None:
        selection = self.sessions_tree.selection()
        return self._sessions.get(selection[0]) if selection else None

    def _resume_selected(self) -> None:
        selected = self._selected_session()
        if not selected:
            messagebox.showinfo("Agent Workbench", "Selecione uma sessão.")
            return
        try:
            resume_session(selected.session_id)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Não foi possível retomar", str(exc))

    def _open_session_location(self) -> None:
        selected = self._selected_session()
        if selected:
            open_folder(selected.path.parent)

    def _add_repository(self) -> None:
        selected = filedialog.askdirectory(title="Selecione um repositório Git")
        if not selected:
            return
        path = Path(selected)
        if path not in self._repository_paths:
            self._repository_paths.append(path)
            save_repository_paths(self._repository_paths)
        self.refresh()

    def _selected_repository_path(self) -> Path | None:
        selection = self.repos_tree.selection()
        return Path(selection[0]) if selection else None

    def _remove_repository(self) -> None:
        selected = self._selected_repository_path()
        if selected is None:
            return
        self._repository_paths = [item for item in self._repository_paths if item.resolve() != selected.resolve()]
        save_repository_paths(self._repository_paths)
        self.refresh()

    def _open_repository(self) -> None:
        selected = self._selected_repository_path()
        if selected:
            open_folder(selected)

    def _on_close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()


def main() -> None:
    app = AgentWorkbench()
    app.mainloop()

