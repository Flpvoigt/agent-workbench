from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

from agent_workbench.models import AgentSession, RepositoryStatus


CANVAS_BG = "#090D16"
GRID = "#121A28"
SURFACE = "#111A29"
SURFACE_ACTIVE = "#17243A"
BORDER = "#243249"
TEXT = "#F3F7FB"
MUTED = "#7F91A8"
PURPLE = "#8B6CFF"
CYAN = "#35D9C5"
GREEN = "#47E6A0"
YELLOW = "#F4C867"


@dataclass(slots=True)
class Flow:
    route: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]
    phase: float
    speed: float
    particle: int
    chip: tuple[int, int, float] | None = None
    reverse: bool = False


class AgentGraph(tk.Canvas):
    def __init__(self, master: tk.Misc, on_select: Callable[[str, object], None]) -> None:
        super().__init__(master, bg=CANVAS_BG, highlightthickness=0, bd=0, relief=tk.FLAT)
        self._on_select = on_select
        self._sessions: list[AgentSession] = []
        self._repositories: list[RepositoryStatus] = []
        self._flows: list[Flow] = []
        self._selected_key = ""
        self._animation_enabled = True
        self._render_job: str | None = None
        self.bind("<Configure>", self._schedule_render)
        self.after(32, self._animate)

    def set_data(self, sessions: list[AgentSession], repositories: list[RepositoryStatus]) -> None:
        self._sessions = sessions[:7]
        self._repositories = repositories[:5]
        self._schedule_render()

    def set_animation(self, enabled: bool) -> None:
        self._animation_enabled = enabled
        state = tk.NORMAL if enabled else tk.HIDDEN
        for flow in self._flows:
            self.itemconfigure(flow.particle, state=state)
            if flow.chip:
                for item in flow.chip[:2]:
                    self.itemconfigure(item, state=state)

    def _schedule_render(self, _event: tk.Event | None = None) -> None:
        if self._render_job:
            self.after_cancel(self._render_job)
        self._render_job = self.after(80, self._render)

    def _render(self) -> None:
        self._render_job = None
        self.delete("all")
        self._flows.clear()
        width = max(self.winfo_width(), 720)
        height = max(self.winfo_height(), 520)
        self._draw_grid(width, height)
        session_positions = self._vertical_positions(len(self._sessions), 120, height - 90)
        repo_positions = self._vertical_positions(len(self._repositories), 140, height - 100)
        session_nodes = {session.session_id: (160.0, y) for session, y in zip(self._sessions, session_positions)}
        repo_nodes = {str(repo.path): (width - 170.0, y) for repo, y in zip(self._repositories, repo_positions)}
        hub = (width * 0.52, height * 0.48)

        self._draw_caption(38, 42, "AGENTS", f"{len(self._sessions)} sessões recentes")
        self._draw_caption(width - 304, 42, "WORKSPACES", f"{len(self._repositories)} repositórios")
        for repo in self._repositories:
            self._draw_flow(hub, repo_nodes[str(repo.path)], CYAN, 0.0024, None)
        for index, session in enumerate(self._sessions):
            start = session_nodes[session.session_id]
            repo = self._repository_for(session)
            end = repo_nodes.get(str(repo.path), hub) if repo else hub
            file_name = session.recent_files[-1] if session.recent_files else None
            self._draw_flow(
                start,
                end,
                GREEN if session.active else PURPLE,
                0.0045 if session.active else 0.0017,
                file_name,
                reverse=index % 2 == 1,
            )
        self._draw_hub(*hub, sum(1 for session in self._sessions if session.active))
        for session in self._sessions:
            self._draw_session(*session_nodes[session.session_id], session)
        for repo in self._repositories:
            self._draw_repository(*repo_nodes[str(repo.path)], repo)
        if not self._sessions:
            self.create_text(width * 0.5, height * 0.68, text="Nenhuma sessão do Codex encontrada", fill=MUTED, font=("Segoe UI", 11))

    def _draw_grid(self, width: int, height: int) -> None:
        for x in range(24, width, 28):
            for y in range(24, height, 28):
                self.create_oval(x, y, x + 1, y + 1, fill=GRID, outline="")
        self.create_oval(width * 0.52 - 170, height * 0.48 - 170, width * 0.52 + 170, height * 0.48 + 170, outline="#101827", width=1)

    @staticmethod
    def _vertical_positions(count: int, top: float, bottom: float) -> list[float]:
        if count <= 0:
            return []
        if count == 1:
            return [(top + bottom) / 2]
        step = (bottom - top) / (count - 1)
        return [top + index * step for index in range(count)]

    def _draw_caption(self, x: float, y: float, title: str, subtitle: str) -> None:
        self.create_text(x, y, text=title, anchor="w", fill=MUTED, font=("Segoe UI Semibold", 9))
        self.create_text(x, y + 19, text=subtitle, anchor="w", fill="#52647C", font=("Segoe UI", 9))

    @staticmethod
    def _route(start: tuple[float, float], end: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
        distance = end[0] - start[0]
        return start, (start[0] + distance * 0.42, start[1]), (end[0] - distance * 0.42, end[1]), end

    def _draw_flow(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        color: str,
        speed: float,
        file_name: str | None,
        *,
        reverse: bool = False,
    ) -> None:
        route = self._route(start, end)
        points = [coordinate for point in route for coordinate in point]
        self.create_line(*points, smooth=True, splinesteps=24, fill="#243249", width=2, arrow=tk.LAST, arrowshape=(7, 8, 3))
        x, y = self._bezier(route, 0.0)
        particle = self.create_oval(x - 4, y - 4, x + 4, y + 4, fill=color, outline="")
        chip: tuple[int, int, float] | None = None
        if file_name:
            label = file_name[:18]
            chip_width = max(58.0, 9.0 + len(label) * 6.0)
            chip_bg = self._rounded_rect(x - chip_width / 2, y - 13, x + chip_width / 2, y + 13, 9, fill="#172338", outline="#30415D", width=1)
            chip_text = self.create_text(x, y, text=label, fill="#C9D5E5", font=("Cascadia Mono", 8))
            chip = (chip_bg, chip_text, chip_width)
            self.itemconfigure(particle, state=tk.HIDDEN)
        self._flows.append(Flow(route, (len(self._flows) * 0.17) % 1, speed, particle, chip, reverse))

    def _draw_hub(self, x: float, y: float, active_count: int) -> None:
        self.create_oval(x - 65, y - 65, x + 65, y + 65, outline="#263651", width=1)
        self.create_oval(x - 48, y - 48, x + 48, y + 48, fill="#101A2B", outline=PURPLE, width=2)
        self.create_oval(x - 8, y - 8, x + 8, y + 8, fill=CYAN, outline="")
        self.create_text(x, y + 23, text="CODEX", fill=TEXT, font=("Segoe UI Semibold", 11))
        self.create_text(x, y + 41, text=f"{active_count} em atividade", fill=MUTED, font=("Segoe UI", 8))

    def _draw_session(self, x: float, y: float, session: AgentSession) -> None:
        key = f"session:{session.session_id}"
        selected = self._selected_key == key
        tag = ("node", key)
        self._rounded_rect(x - 122, y - 35, x + 122, y + 35, 14, fill=SURFACE_ACTIVE if session.active else SURFACE, outline=GREEN if session.active else (PURPLE if selected else BORDER), width=2 if selected else 1, tags=tag)
        self.create_oval(x - 106, y - 8, x - 94, y + 4, fill=GREEN if session.active else MUTED, outline="", tags=tag)
        self.create_text(x - 84, y - 12, text=self._truncate(session.project_name, 22), anchor="w", fill=TEXT, font=("Segoe UI Semibold", 10), tags=tag)
        self.create_text(x - 84, y + 10, text=self._truncate(session.last_activity, 30), anchor="w", fill=MUTED, font=("Segoe UI", 9), tags=tag)
        self.create_text(x + 104, y - 11, text="LIVE" if session.active else "IDLE", anchor="e", fill=GREEN if session.active else "#56677E", font=("Cascadia Mono", 8), tags=tag)
        self.tag_bind(key, "<Button-1>", lambda _event, value=session: self._select("session", value))

    def _draw_repository(self, x: float, y: float, repo: RepositoryStatus) -> None:
        key = f"repo:{repo.path}"
        selected = self._selected_key == key
        tag = ("node", key)
        self._rounded_rect(x - 128, y - 39, x + 128, y + 39, 14, fill=SURFACE, outline=CYAN if selected else BORDER, width=2 if selected else 1, tags=tag)
        self.create_rectangle(x - 108, y - 8, x - 94, y + 8, fill=CYAN, outline="", tags=tag)
        self.create_text(x - 82, y - 13, text=self._truncate(repo.name, 22), anchor="w", fill=TEXT, font=("Segoe UI Semibold", 10), tags=tag)
        changes = f"{repo.dirty_files} alterações" if repo.dirty_files else "working tree limpa"
        self.create_text(x - 82, y + 11, text=f"{repo.branch}  ·  {changes}", anchor="w", fill=MUTED, font=("Segoe UI", 8), tags=tag)
        pr_text = "—" if repo.pull_requests is None else str(repo.pull_requests)
        self.create_text(x + 108, y, text=f"PR {pr_text}", anchor="e", fill=YELLOW if repo.pull_requests else "#56677E", font=("Cascadia Mono", 8), tags=tag)
        self.tag_bind(key, "<Button-1>", lambda _event, value=repo: self._select("repository", value))

    def _select(self, kind: str, value: object) -> None:
        self._selected_key = f"session:{value.session_id}" if kind == "session" else f"repo:{value.path}"  # type: ignore[attr-defined]
        self._on_select(kind, value)
        self._schedule_render()

    def _repository_for(self, session: AgentSession) -> RepositoryStatus | None:
        if not session.cwd:
            return None
        session_path = str(session.cwd.resolve()).casefold()
        matches = [repo for repo in self._repositories if session_path == str(repo.path.resolve()).casefold() or session_path.startswith(str(repo.path.resolve()).casefold() + "\\")]
        return max(matches, key=lambda repo: len(str(repo.path))) if matches else None

    def _animate(self) -> None:
        if self._animation_enabled:
            for flow in self._flows:
                flow.phase = (flow.phase + flow.speed) % 1.0
                progress = 1.0 - flow.phase if flow.reverse else flow.phase
                x, y = self._bezier(flow.route, progress)
                if flow.chip:
                    background, label, width = flow.chip
                    self.coords(background, x - width / 2, y - 13, x + width / 2, y + 13)
                    self.coords(label, x, y)
                else:
                    self.coords(flow.particle, x - 4, y - 4, x + 4, y + 4)
        self.after(32, self._animate)

    @staticmethod
    def _bezier(route: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]], progress: float) -> tuple[float, float]:
        p0, p1, p2, p3 = route
        inverse = 1.0 - progress
        x = inverse**3 * p0[0] + 3 * inverse**2 * progress * p1[0] + 3 * inverse * progress**2 * p2[0] + progress**3 * p3[0]
        y = inverse**3 * p0[1] + 3 * inverse**2 * progress * p1[1] + 3 * inverse * progress**2 * p2[1] + progress**3 * p3[1]
        return x, y

    def _rounded_rect(self, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs: object) -> int:
        points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius, x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2, x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
        return self.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    @staticmethod
    def _truncate(value: str, length: int) -> str:
        clean = " ".join(value.split())
        return clean if len(clean) <= length else clean[: length - 1] + "…"

