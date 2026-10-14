from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

from agent_workbench.models import AgentSession, RepositoryStatus


BG = "#070B14"
SURFACE = "#101725"
SURFACE_RAISED = "#131C2C"
BORDER = "#25324A"
TEXT = "#F3F7FF"
MUTED = "#8FA3BF"
DIM = "#43516A"
GREEN = "#35E6B5"
PURPLE = "#8B5CF6"
CYAN = "#43CFF4"
YELLOW = "#F6C453"
RED = "#FF5D6C"


@dataclass(slots=True)
class TokenFlow:
    points: tuple[tuple[float, float], ...]
    phase: float
    speed: float
    items: tuple[int, int]
    width: float


class MissionGraph(tk.Canvas):
    def __init__(
        self,
        master: tk.Misc,
        on_select: Callable[[str, object], None],
        on_open: Callable[[str, object], None],
    ) -> None:
        super().__init__(master, bg=BG, highlightthickness=0, bd=0)
        self._on_select = on_select
        self._on_open = on_open
        self._sessions: list[AgentSession] = []
        self._repositories: list[RepositoryStatus] = []
        self._selected_key = ""
        self._animation_enabled = True
        self._flows: list[TokenFlow] = []
        self._render_job: str | None = None
        self._pulse = 0.0
        self._position_overrides: dict[str, tuple[float, float]] = {}
        self._node_positions: dict[str, tuple[float, float]] = {}
        self._drag_candidate: tuple[str, float, float, float, float] | None = None
        self._drag_active = False
        self.bind("<Configure>", self._schedule_render)
        self.bind("<B1-Motion>", self._drag_move)
        self.bind("<ButtonRelease-1>", self._drag_end)
        self.after(32, self._animate)

    def set_data(self, sessions: list[AgentSession], repositories: list[RepositoryStatus]) -> None:
        self._sessions = sessions
        self._repositories = repositories[:5]
        self._schedule_render()

    def focus(self, kind: str, value: object) -> None:
        self._selected_key = self._key(kind, value)
        self._schedule_render()

    def clear_focus(self) -> None:
        self._selected_key = ""
        self._schedule_render()

    def set_animation(self, enabled: bool) -> None:
        self._animation_enabled = enabled
        state = tk.NORMAL if enabled else tk.HIDDEN
        for flow in self._flows:
            for item in flow.items:
                self.itemconfigure(item, state=state)

    def _schedule_render(self, _event: tk.Event | None = None) -> None:
        if self._render_job:
            self.after_cancel(self._render_job)
        self._render_job = self.after(60, self._render)

    def _render(self) -> None:
        self._render_job = None
        self.delete("all")
        self._flows.clear()
        width = max(self.winfo_width(), 760)
        height = max(self.winfo_height(), 540)
        self._background(width, height)

        active = [session for session in self._sessions if session.active][:3]
        idle = [session for session in self._sessions if not session.active]
        displayed = active or self._sessions[:1]
        agent_positions = self._positions(len(displayed), 160, min(height - 180, 440))
        repo_positions = self._positions(len(self._repositories), 150, height - 115)
        agent_x = 176.0
        repo_x = width - 170.0
        hub = (width * 0.53, height * 0.50)
        trunk_x = width * 0.36
        branch_x = width * 0.70

        self._zone_label(34, 40, "AGENTS", f"{len(active)} ativos · {len(idle)} históricos")
        self._zone_label(hub[0] - 42, 40, "RUNTIME", "orquestração local")
        self._zone_label(width - 310, 40, "WORKSPACES", f"{len(self._repositories)} conectados")

        repo_nodes = {
            str(repo.path): self._position_overrides.get(f"repository:{repo.path}", (repo_x, y))
            for repo, y in zip(self._repositories, repo_positions)
        }
        agent_nodes = {
            session.session_id: self._position_overrides.get(
                f"session:{session.session_id}", (agent_x, y)
            )
            for session, y in zip(displayed, agent_positions)
        }
        history_position = self._position_overrides.get("history", (agent_x, height - 82))
        self._node_positions = {
            **{f"session:{key}": value for key, value in agent_nodes.items()},
            **{f"repository:{key}": value for key, value in repo_nodes.items()},
        }
        if idle:
            self._node_positions["history"] = history_position

        selected_session = self._selected_session()
        selected_repo = self._selected_repository()
        relevant_repo = self._repo_for(selected_session) if selected_session else selected_repo
        focus_active = bool(self._selected_key)

        for repo in self._repositories:
            endpoint = repo_nodes[str(repo.path)]
            related = not focus_active or repo == relevant_repo or repo == selected_repo
            color = CYAN if related else "#172237"
            self._path(
                (hub[0] + 36, hub[1]),
                (branch_x, hub[1]),
                (branch_x, endpoint[1]),
                (endpoint[0] - 142, endpoint[1]),
                color=color,
                width=2 if related else 1,
            )

        token_budget = 4
        for index, session in enumerate(displayed):
            start = agent_nodes[session.session_id]
            repo = self._repo_for(session)
            endpoint = repo_nodes.get(str(repo.path)) if repo else None
            related = not focus_active or session == selected_session or repo == relevant_repo
            line_color = GREEN if session.active and related else ("#384967" if related else "#141D2D")
            self._path(
                (start[0] + 138, start[1]),
                (trunk_x, start[1]),
                (trunk_x, hub[1]),
                (hub[0] - 36, hub[1]),
                color=line_color,
                width=3 if session.active and related else 1,
                glow=session.active and related,
            )
            if session.active and endpoint and session.recent_files and token_budget > 0:
                file_name = session.recent_files[-1]
                operation, color = self._operation(session.last_activity)
                route = (
                    (start[0] + 138, start[1]),
                    (trunk_x, start[1]),
                    (trunk_x, hub[1]),
                    (hub[0], hub[1]),
                    (branch_x, hub[1]),
                    (branch_x, endpoint[1]),
                    (endpoint[0] - 142, endpoint[1]),
                )
                self._token(route, f"{operation}  {file_name[:15]}", color, index)
                token_budget -= 1

        self._hub(*hub, len(active))
        for session in displayed:
            self._agent_card(*agent_nodes[session.session_id], session, self._repo_for(session))
        if idle:
            self._history_card(*history_position, idle)
        for repo in self._repositories:
            self._repo_card(*repo_nodes[str(repo.path)], repo)

        if not self._sessions:
            self.create_text(
                width * 0.5,
                height * 0.64,
                text="Nenhuma sessão local encontrada",
                fill=MUTED,
                font=("Segoe UI", 11),
            )

    def _background(self, width: int, height: int) -> None:
        for x in range(20, width, 30):
            for y in range(22, height, 30):
                self.create_oval(x, y, x + 1, y + 1, fill="#111A29", outline="")
        self.create_line(width * 0.28, 72, width * 0.28, height - 28, fill="#101827")
        self.create_line(width * 0.76, 72, width * 0.76, height - 28, fill="#101827")

    def _zone_label(self, x: float, y: float, title: str, subtitle: str) -> None:
        self.create_text(x, y, text=title, anchor="w", fill="#6680A2", font=("Segoe UI Semibold", 8))
        self.create_text(x, y + 18, text=subtitle, anchor="w", fill=DIM, font=("Segoe UI", 8))

    @staticmethod
    def _positions(count: int, top: float, bottom: float) -> list[float]:
        if count <= 0:
            return []
        if count == 1:
            return [(top + bottom) / 2]
        step = (bottom - top) / (count - 1)
        return [top + index * step for index in range(count)]

    def _path(self, *points: tuple[float, float], color: str, width: int, glow: bool = False) -> None:
        curve = self._smooth_points(points)
        coords = [value for point in curve for value in point]
        shadow = "#132E32" if glow else "#0C1422"
        self.create_line(
            *coords,
            fill=shadow,
            width=width + (6 if glow else 3),
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
        )
        if glow:
            self.create_line(
                *coords,
                fill="#1A4A48",
                width=width + 2,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )
        self.create_line(
            *coords,
            fill=color,
            width=width,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
        )

    def _token(self, points: tuple[tuple[float, float], ...], label: str, color: str, index: int) -> None:
        curve = self._smooth_points(points)
        x, y = curve[0]
        width = max(92.0, min(146.0, 24.0 + len(label) * 5.4))
        box = self._round_rect(
            x - width / 2,
            y - 13,
            x + width / 2,
            y + 13,
            8,
            fill="#111B2A",
            outline=color,
            width=1,
        )
        text = self.create_text(x, y, text=label, fill=TEXT, font=("Consolas", 8))
        self._flows.append(TokenFlow(curve, (index * 0.23) % 1.0, 0.005 + index * 0.0005, (box, text), width))

    def _hub(self, x: float, y: float, active_count: int) -> None:
        pulse = 5 + 3 * math.sin(self._pulse)
        self.create_oval(x - 51 - pulse, y - 51 - pulse, x + 51 + pulse, y + 51 + pulse, outline="#17313A", width=2)
        self.create_oval(x - 36, y - 36, x + 36, y + 36, fill="#0F1726", outline=GREEN if active_count else BORDER, width=2)
        self.create_oval(x - 6, y - 6, x + 6, y + 6, fill=GREEN if active_count else DIM, outline="")
        self.create_text(x, y + 19, text="RUNTIME", fill=TEXT, font=("Segoe UI Semibold", 9))
        self.create_text(x, y + 34, text=f"{active_count} LIVE", fill=GREEN if active_count else MUTED, font=("Consolas", 7))

    def _agent_card(self, x: float, y: float, session: AgentSession, repo: RepositoryStatus | None) -> None:
        key = f"session:{session.session_id}"
        selected = self._selected_key == key
        tag = ("node", key)
        outline = GREEN if session.active else (PURPLE if selected else BORDER)
        self._round_rect(x - 138, y - 49, x + 138, y + 49, 14, fill=SURFACE_RAISED if session.active else SURFACE, outline=outline, width=2 if selected or session.active else 1, tags=tag)
        self.create_line(x - 136, y - 46, x + 136, y - 46, fill="#1B2A40", width=1, tags=tag)
        self.create_oval(x - 119, y - 31, x - 109, y - 21, fill=GREEN if session.active else YELLOW, outline="", tags=tag)
        self.create_text(x - 99, y - 26, text="WORKING" if session.active else "WAITING", anchor="w", fill=GREEN if session.active else YELLOW, font=("Consolas", 8), tags=tag)
        self.create_text(x + 119, y - 26, text=session.modified_at.strftime("%H:%M"), anchor="e", fill=DIM, font=("Consolas", 8), tags=tag)
        self.create_text(x - 118, y, text=self._truncate(session.project_name, 25), anchor="w", fill=TEXT, font=("Segoe UI Semibold", 11), tags=tag)
        self.create_text(x - 118, y + 17, text=self._truncate(session.last_activity, 30), anchor="w", fill=MUTED, font=("Segoe UI", 8), tags=tag)
        file_name = session.recent_files[-1] if session.recent_files else "sem arquivo recente"
        destination = repo.name if repo else "runtime"
        self.create_text(x - 118, y + 34, text=self._truncate(f"{file_name} → {destination}", 38), anchor="w", fill="#6F85A3", font=("Consolas", 7), tags=tag)
        self.tag_bind(
            key,
            "<ButtonPress-1>",
            lambda event, value=session, node_key=key: self._drag_start(
                event, node_key, "session", value
            ),
        )
        self.tag_bind(key, "<Double-Button-1>", lambda _event, value=session: self._on_open("session", value))

    def _history_card(self, x: float, y: float, sessions: list[AgentSession]) -> None:
        key = "history"
        selected = self._selected_key == key
        tag = ("node", key)
        self._round_rect(x - 138, y - 31, x + 138, y + 31, 12, fill="#0D1420", outline=PURPLE if selected else BORDER, width=2 if selected else 1, tags=tag)
        self.create_text(x - 112, y - 7, text=f"SESSÕES ANTERIORES · {len(sessions)}", anchor="w", fill=MUTED, font=("Segoe UI Semibold", 9), tags=tag)
        self.create_text(x - 112, y + 13, text="Clique para inspecionar o histórico recente", anchor="w", fill=DIM, font=("Segoe UI", 8), tags=tag)
        self.create_text(x + 111, y, text="›", anchor="e", fill=PURPLE, font=("Segoe UI Semibold", 18), tags=tag)
        self.tag_bind(
            key,
            "<ButtonPress-1>",
            lambda event, value=tuple(sessions): self._drag_start(
                event, key, "history", value
            ),
        )

    def _repo_card(self, x: float, y: float, repo: RepositoryStatus) -> None:
        key = f"repository:{repo.path}"
        selected = self._selected_key == key
        tag = ("node", key)
        dirty = repo.dirty_files > 0
        self._round_rect(x - 142, y - 43, x + 142, y + 43, 14, fill=SURFACE, outline=CYAN if selected else BORDER, width=2 if selected else 1, tags=tag)
        self.create_line(x - 140, y - 40, x + 140, y - 40, fill="#1B2A40", width=1, tags=tag)
        self.create_rectangle(x - 121, y - 25, x - 111, y - 15, fill=CYAN, outline="", tags=tag)
        self.create_text(x - 99, y - 20, text=self._truncate(repo.name, 21), anchor="w", fill=TEXT, font=("Segoe UI Semibold", 10), tags=tag)
        badge = f"DIRTY · {repo.dirty_files}" if dirty else "CLEAN"
        self.create_text(x + 121, y - 20, text=badge, anchor="e", fill=PURPLE if dirty else GREEN, font=("Consolas", 8), tags=tag)
        self.create_text(x - 121, y + 8, text=self._truncate(repo.branch, 27), anchor="w", fill=MUTED, font=("Consolas", 8), tags=tag)
        pr_text = "PR —" if repo.pull_requests is None else f"{repo.pull_requests} PR ABERTOS"
        self.create_text(x - 121, y + 27, text=pr_text, anchor="w", fill=DIM, font=("Consolas", 7), tags=tag)
        self.tag_bind(
            key,
            "<ButtonPress-1>",
            lambda event, value=repo, node_key=key: self._drag_start(
                event, node_key, "repository", value
            ),
        )
        self.tag_bind(key, "<Double-Button-1>", lambda _event, value=repo: self._on_open("repository", value))

    def _drag_start(
        self,
        event: tk.Event,
        key: str,
        kind: str,
        value: object,
    ) -> None:
        center = self._node_positions.get(key)
        if center is None:
            return
        self._drag_candidate = (
            key,
            float(event.x),
            float(event.y),
            center[0] - float(event.x),
            center[1] - float(event.y),
        )
        self._drag_active = False
        self._select(kind, value)

    def _drag_move(self, event: tk.Event) -> None:
        if self._drag_candidate is None:
            return
        key, origin_x, origin_y, offset_x, offset_y = self._drag_candidate
        if not self._drag_active and math.hypot(event.x - origin_x, event.y - origin_y) < 5:
            return
        self._drag_active = True
        width = max(self.winfo_width(), 760)
        height = max(self.winfo_height(), 540)
        x = min(max(float(event.x) + offset_x, 150.0), width - 150.0)
        y = min(max(float(event.y) + offset_y, 104.0), height - 64.0)
        self._position_overrides[key] = (x, y)
        self._node_positions[key] = (x, y)
        if self._render_job:
            self.after_cancel(self._render_job)
        self._render_job = self.after_idle(self._render)

    def _drag_end(self, _event: tk.Event) -> None:
        self._drag_candidate = None
        self._drag_active = False

    def _select(self, kind: str, value: object) -> None:
        self._selected_key = self._key(kind, value)
        self._on_select(kind, value)
        self._schedule_render()

    @staticmethod
    def _smooth_points(
        points: tuple[tuple[float, float], ...], passes: int = 4
    ) -> tuple[tuple[float, float], ...]:
        """Round corners without overshooting so edges and tokens share one route."""
        if len(points) < 3:
            return points
        result = list(points)
        for _ in range(passes):
            rounded = [result[0]]
            for start, end in zip(result, result[1:]):
                rounded.append(
                    (0.75 * start[0] + 0.25 * end[0], 0.75 * start[1] + 0.25 * end[1])
                )
                rounded.append(
                    (0.25 * start[0] + 0.75 * end[0], 0.25 * start[1] + 0.75 * end[1])
                )
            rounded.append(result[-1])
            result = rounded
        return tuple(result)

    @staticmethod
    def _key(kind: str, value: object) -> str:
        if kind == "session":
            return f"session:{value.session_id}"  # type: ignore[attr-defined]
        if kind == "repository":
            return f"repository:{value.path}"  # type: ignore[attr-defined]
        return kind

    def _selected_session(self) -> AgentSession | None:
        if not self._selected_key.startswith("session:"):
            return None
        session_id = self._selected_key.removeprefix("session:")
        return next((item for item in self._sessions if item.session_id == session_id), None)

    def _selected_repository(self) -> RepositoryStatus | None:
        if not self._selected_key.startswith("repository:"):
            return None
        path = self._selected_key.removeprefix("repository:")
        return next((item for item in self._repositories if str(item.path) == path), None)

    def _repo_for(self, session: AgentSession | None) -> RepositoryStatus | None:
        if not session or not session.cwd:
            return None
        session_path = str(session.cwd.resolve()).casefold()
        matches = [
            repo
            for repo in self._repositories
            if session_path == str(repo.path.resolve()).casefold()
            or session_path.startswith(str(repo.path.resolve()).casefold() + "\\")
        ]
        if matches:
            return max(matches, key=lambda repo: len(str(repo.path)))
        if not session.recent_files:
            return None
        scored: list[tuple[int, RepositoryStatus]] = []
        common_folders = ("", "src", "src/agent_workbench", "tests", "scripts", ".github")
        for repo in self._repositories:
            score = 0
            for name in session.recent_files:
                if any((repo.path / folder / name).exists() for folder in common_folders):
                    score += 1
            if score:
                scored.append((score, repo))
        return max(scored, key=lambda item: item[0])[1] if scored else None

    @staticmethod
    def _operation(activity: str) -> tuple[str, str]:
        folded = activity.casefold()
        if "edit" in folded or "patch" in folded:
            return "WRITE", PURPLE
        if "gera" in folded or "cria" in folded:
            return "CREATE", GREEN
        if "erro" in folded or "falh" in folded:
            return "ERROR", RED
        return "READ", CYAN

    def _animate(self) -> None:
        self._pulse = (self._pulse + 0.08) % (math.pi * 2)
        if self._animation_enabled:
            for flow in self._flows:
                flow.phase = (flow.phase + flow.speed) % 1.0
                x, y = self._point_on_path(flow.points, flow.phase)
                box, label = flow.items
                self.coords(box, x - flow.width / 2, y - 13, x + flow.width / 2, y + 13)
                self.coords(label, x, y)
        self.after(32, self._animate)

    @staticmethod
    def _point_on_path(points: tuple[tuple[float, float], ...], progress: float) -> tuple[float, float]:
        lengths = [math.dist(start, end) for start, end in zip(points, points[1:])]
        total = sum(lengths) or 1.0
        target = progress * total
        covered = 0.0
        for index, length in enumerate(lengths):
            if covered + length >= target:
                local = (target - covered) / (length or 1.0)
                start, end = points[index], points[index + 1]
                return start[0] + (end[0] - start[0]) * local, start[1] + (end[1] - start[1]) * local
            covered += length
        return points[-1]

    def _round_rect(self, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs: object) -> int:
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    @staticmethod
    def _truncate(value: str, length: int) -> str:
        clean = " ".join(value.split())
        return clean if len(clean) <= length else clean[: length - 1] + "…"
