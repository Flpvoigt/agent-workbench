from __future__ import annotations

import queue
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from agent_workbench.graph import BORDER, CYAN, GREEN, MUTED, PURPLE, SURFACE, TEXT, YELLOW, AgentGraph
from agent_workbench.models import AgentSession, RepositoryStatus
from agent_workbench.services import (
    discover_sessions,
    find_git_root,
    inspect_repository,
    list_codex_processes,
    load_repository_paths,
    open_folder,
    resume_session,
    save_repository_paths,
)


APP_BG = "#080B12"
HEADER_BG = "#0B101A"
SIDEBAR_BG = "#0D131F"
HOVER = "#1B2940"


class AgentWorkbench(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Agent Workbench · Live Operations")
        self.geometry("1380x820")
        self.minsize(1080, 680)
        self.configure(bg=APP_BG)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="workbench")
        self._results: queue.Queue[tuple[str, object]] = queue.Queue()
        self._refreshing = False
        self._sessions: list[AgentSession] = []
        self._repositories: list[RepositoryStatus] = []
        self._repository_paths = load_repository_paths()
        self._selected: tuple[str, object] | None = None
        self._animation_enabled = True
        self._has_data = False
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_results)
        self.after(250, self.refresh)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_rail()
        self._build_header()
        workspace = tk.Frame(self, bg=APP_BG)
        workspace.grid(row=1, column=1, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_rowconfigure(0, weight=1)
        self.graph = AgentGraph(workspace, self._select_node)
        self.graph.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=(8, 14))
        self._build_inspector(workspace)
        self._build_activity_bar()

    def _build_rail(self) -> None:
        rail = tk.Frame(self, bg=SIDEBAR_BG, width=72)
        rail.grid(row=0, column=0, rowspan=3, sticky="ns")
        rail.grid_propagate(False)
        logo = tk.Canvas(rail, width=42, height=42, bg=SIDEBAR_BG, highlightthickness=0)
        logo.pack(pady=(20, 34))
        logo.create_oval(6, 6, 36, 36, outline=PURPLE, width=2)
        logo.create_oval(17, 17, 25, 25, fill=CYAN, outline="")
        logo.create_line(8, 21, 17, 21, fill=PURPLE, width=2)
        logo.create_line(25, 21, 34, 21, fill=PURPLE, width=2)
        self._rail_button(rail, "⌁", "Mapa ao vivo", active=True)
        self._rail_button(rail, "↻", "Atualizar", command=self.refresh)
        self._rail_button(rail, "+", "Adicionar repositório", command=self._add_repository)
        tk.Frame(rail, bg=SIDEBAR_BG).pack(fill=tk.BOTH, expand=True)
        self._rail_button(rail, "?", "Sobre", command=self._show_about)

    def _rail_button(self, parent: tk.Misc, text: str, label: str, command: object | None = None, *, active: bool = False) -> None:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            font=("Segoe UI Semibold", 16),
            fg=TEXT if active else MUTED,
            bg="#17233A" if active else SIDEBAR_BG,
            activebackground=HOVER,
            activeforeground=TEXT,
            bd=0,
            relief=tk.FLAT,
            width=2,
            height=1,
            cursor="hand2",
        )
        button.pack(pady=7, ipadx=5, ipady=5)
        self._attach_tooltip(button, label)

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=HEADER_BG, height=78)
        header.grid(row=0, column=1, sticky="ew")
        header.grid_propagate(False)
        title_box = tk.Frame(header, bg=HEADER_BG)
        title_box.pack(side=tk.LEFT, padx=24, pady=14)
        tk.Label(title_box, text="LIVE AGENT MAP", fg=TEXT, bg=HEADER_BG, font=("Segoe UI Semibold", 15)).pack(anchor="w")
        tk.Label(title_box, text="Fluxo real de sessões, ferramentas e arquivos", fg=MUTED, bg=HEADER_BG, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        actions = tk.Frame(header, bg=HEADER_BG)
        actions.pack(side=tk.RIGHT, padx=22)
        self.live_label = tk.Label(actions, text="● sincronizando", fg=YELLOW, bg=HEADER_BG, font=("Cascadia Mono", 9))
        self.live_label.pack(side=tk.LEFT, padx=(0, 18))
        self.animation_button = self._button(actions, "Pausar fluxo", self._toggle_animation, ghost=True)
        self.animation_button.pack(side=tk.LEFT, padx=5)
        self._button(actions, "Atualizar", self.refresh, accent=True).pack(side=tk.LEFT, padx=5)

    def _build_inspector(self, workspace: tk.Frame) -> None:
        self.inspector = tk.Frame(workspace, bg=SIDEBAR_BG, width=310)
        self.inspector.grid(row=0, column=1, sticky="nsew", padx=(0, 14), pady=(8, 14))
        self.inspector.grid_propagate(False)
        self._show_overview()

    def _build_activity_bar(self) -> None:
        self.activity_bar = tk.Frame(self, bg=HEADER_BG, height=38)
        self.activity_bar.grid(row=2, column=1, sticky="ew")
        self.activity_bar.grid_propagate(False)
        tk.Label(self.activity_bar, text="EVENTO RECENTE", fg="#53667F", bg=HEADER_BG, font=("Segoe UI Semibold", 8)).pack(side=tk.LEFT, padx=(22, 14))
        self.activity_text = tk.Label(self.activity_bar, text="Aguardando dados…", fg=MUTED, bg=HEADER_BG, font=("Cascadia Mono", 8))
        self.activity_text.pack(side=tk.LEFT)
        self.updated_text = tk.Label(self.activity_bar, text="", fg="#53667F", bg=HEADER_BG, font=("Cascadia Mono", 8))
        self.updated_text.pack(side=tk.RIGHT, padx=22)

    def _button(self, parent: tk.Misc, text: str, command: object, *, accent: bool = False, ghost: bool = False) -> tk.Button:
        background = PURPLE if accent else (HEADER_BG if ghost else "#182338")
        return tk.Button(
            parent,
            text=text,
            command=command,
            fg="#FFFFFF" if accent else TEXT,
            bg=background,
            activebackground="#7155E8" if accent else HOVER,
            activeforeground="#FFFFFF",
            bd=0,
            relief=tk.FLAT,
            font=("Segoe UI Semibold", 9),
            padx=15,
            pady=8,
            cursor="hand2",
        )

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        if not self._has_data:
            self.live_label.configure(text="● sincronizando", fg=YELLOW)
        self._executor.submit(self._collect_data)

    def _collect_data(self) -> None:
        sessions = discover_sessions()
        processes = list_codex_processes()
        repo_paths: dict[str, Path] = {
            str(path.expanduser().resolve()).casefold(): path.expanduser().resolve()
            for path in self._repository_paths
        }
        for session in sessions[:30]:
            root = find_git_root(session.cwd)
            if root:
                repo_paths[str(root).casefold()] = root
        app_root = find_git_root(Path(__file__))
        if app_root:
            repo_paths[str(app_root).casefold()] = app_root
        repositories = [inspect_repository(path) for path in repo_paths.values()]
        repositories.sort(key=lambda repo: (bool(repo.error), repo.name.casefold()))
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

    def _render(self, sessions: list[AgentSession], processes: list[object], repositories: list[RepositoryStatus]) -> None:
        self._refreshing = False
        self._has_data = True
        self._sessions = sessions
        self._repositories = repositories
        self.graph.set_data(sessions, repositories)
        active = sum(1 for session in sessions if session.active)
        process_hint = f" · {len(processes)} processos" if processes else ""
        self.live_label.configure(text=f"● {active} agents ativos{process_hint}", fg=GREEN if active else MUTED)
        if sessions:
            latest = sessions[0]
            files = f" · {latest.recent_files[-1]}" if latest.recent_files else ""
            self.activity_text.configure(text=f"{latest.project_name}  →  {latest.last_activity}{files}")
        else:
            self.activity_text.configure(text="Nenhuma sessão encontrada em ~/.codex/sessions")
        self.updated_text.configure(text=f"SYNC {datetime.now():%H:%M:%S}")
        self._refresh_inspector_selection() if self._selected else self._show_overview()
        self.after(12_000, self.refresh)

    def _select_node(self, kind: str, value: object) -> None:
        self._selected = (kind, value)
        self._show_session(value) if kind == "session" else self._show_repository(value)  # type: ignore[arg-type]

    def _refresh_inspector_selection(self) -> None:
        kind, selected = self._selected or ("", None)
        if kind == "session" and isinstance(selected, AgentSession):
            current = next((item for item in self._sessions if item.session_id == selected.session_id), selected)
            self._selected = (kind, current)
            self._show_session(current)
        elif kind == "repository" and isinstance(selected, RepositoryStatus):
            current = next((item for item in self._repositories if item.path == selected.path), selected)
            self._selected = (kind, current)
            self._show_repository(current)

    def _clear_inspector(self) -> None:
        for child in self.inspector.winfo_children():
            child.destroy()

    def _inspector_heading(self, eyebrow: str, title: str, status: str, color: str) -> None:
        tk.Label(self.inspector, text=eyebrow, fg="#5D708A", bg=SIDEBAR_BG, font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=22, pady=(22, 5))
        tk.Label(self.inspector, text=title, fg=TEXT, bg=SIDEBAR_BG, font=("Segoe UI Semibold", 17), wraplength=260, justify=tk.LEFT).pack(anchor="w", padx=22)
        tk.Label(self.inspector, text=f"● {status}", fg=color, bg=SIDEBAR_BG, font=("Cascadia Mono", 8)).pack(anchor="w", padx=22, pady=(7, 18))
        tk.Frame(self.inspector, height=1, bg=BORDER).pack(fill=tk.X, padx=22)

    def _show_overview(self) -> None:
        self._clear_inspector()
        self._inspector_heading("OPERAÇÕES", "Selecione um nó", "mapa conectado", CYAN)
        self._fact("Como ler", "Agents ficam à esquerda. Repositórios ficam à direita. Arquivos recentes percorrem as conexões reais entre eles.")
        self._fact("Operação", "Clique em um agent para retomar a sessão ou abrir sua pasta. Clique em um repositório para inspecionar branch, alterações e PRs.")
        self._button(self.inspector, "+ Adicionar repositório", self._add_repository, accent=True).pack(fill=tk.X, padx=22, pady=(22, 8))

    def _show_session(self, session: AgentSession) -> None:
        self._clear_inspector()
        self._inspector_heading("AGENT", session.project_name, "em atividade" if session.active else "sessão ociosa", GREEN if session.active else MUTED)
        self._fact("Operação atual", session.last_activity)
        self._fact("Pedido recente", session.summary or "Sem resumo disponível")
        self._fact("Diretório", str(session.cwd or session.path.parent), mono=True)
        self._fact("Última atualização", session.modified_at.strftime("%d/%m/%Y às %H:%M:%S"))
        if session.recent_files:
            self._fact("Arquivos em trânsito", "\n".join(f"↳ {name}" for name in reversed(session.recent_files)), mono=True)
        self._button(self.inspector, "Retomar sessão", lambda: self._resume(session), accent=True).pack(fill=tk.X, padx=22, pady=(20, 8))
        self._button(self.inspector, "Abrir pasta", lambda: open_folder(session.cwd or session.path.parent)).pack(fill=tk.X, padx=22, pady=4)

    def _show_repository(self, repo: RepositoryStatus) -> None:
        self._clear_inspector()
        state = repo.error or ("alterações locais" if repo.dirty_files else "working tree limpa")
        color = "#FF6B7A" if repo.error else (YELLOW if repo.dirty_files else CYAN)
        self._inspector_heading("REPOSITÓRIO", repo.name, state, color)
        self._fact("Branch", repo.branch, mono=True)
        self._fact("Alterações locais", str(repo.dirty_files))
        self._fact("Pull requests abertos", "indisponível" if repo.pull_requests is None else str(repo.pull_requests))
        self._fact("Remote", repo.remote, mono=True)
        self._fact("Caminho", str(repo.path), mono=True)
        self._button(self.inspector, "Abrir pasta", lambda: open_folder(repo.path), accent=True).pack(fill=tk.X, padx=22, pady=(20, 8))
        self._button(self.inspector, "Remover do painel", lambda: self._remove_repository(repo.path)).pack(fill=tk.X, padx=22, pady=4)

    def _fact(self, label: str, value: str, *, mono: bool = False) -> None:
        box = tk.Frame(self.inspector, bg=SIDEBAR_BG)
        box.pack(fill=tk.X, padx=22, pady=(15, 0))
        tk.Label(box, text=label.upper(), fg="#5D708A", bg=SIDEBAR_BG, font=("Segoe UI Semibold", 8)).pack(anchor="w")
        tk.Label(box, text=value, fg="#C8D3E2", bg=SIDEBAR_BG, font=(("Cascadia Mono", 8) if mono else ("Segoe UI", 9)), wraplength=260, justify=tk.LEFT).pack(anchor="w", pady=(4, 0))

    def _resume(self, session: AgentSession) -> None:
        try:
            resume_session(session.session_id)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Não foi possível retomar", str(exc))

    def _add_repository(self) -> None:
        selected = filedialog.askdirectory(title="Adicionar repositório ao mapa")
        if not selected:
            return
        path = Path(selected).resolve()
        if path not in [item.resolve() for item in self._repository_paths]:
            self._repository_paths.append(path)
            save_repository_paths(self._repository_paths)
        self.refresh()

    def _remove_repository(self, selected: Path) -> None:
        self._repository_paths = [item for item in self._repository_paths if item.resolve() != selected.resolve()]
        save_repository_paths(self._repository_paths)
        self._selected = None
        self.refresh()

    def _toggle_animation(self) -> None:
        self._animation_enabled = not self._animation_enabled
        self.graph.set_animation(self._animation_enabled)
        self.animation_button.configure(text="Pausar fluxo" if self._animation_enabled else "Retomar fluxo")

    def _show_about(self) -> None:
        messagebox.showinfo("Agent Workbench", "Mapa operacional local do Codex.\n\nAs conexões representam sessões, diretórios e repositórios reais.")

    def _attach_tooltip(self, widget: tk.Widget, text: str) -> None:
        popup: tk.Toplevel | None = None

        def show(_event: tk.Event) -> None:
            nonlocal popup
            popup = tk.Toplevel(self)
            popup.overrideredirect(True)
            popup.configure(bg="#243249")
            popup.geometry(f"+{widget.winfo_rootx() + 58}+{widget.winfo_rooty() + 8}")
            tk.Label(popup, text=text, fg=TEXT, bg="#172338", font=("Segoe UI", 8), padx=9, pady=5).pack()

        def hide(_event: tk.Event) -> None:
            nonlocal popup
            if popup:
                popup.destroy()
                popup = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _on_close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()


def main() -> None:
    AgentWorkbench().mainloop()

