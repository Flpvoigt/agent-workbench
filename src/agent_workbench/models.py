from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentSession:
    session_id: str
    path: Path
    modified_at: datetime
    size_bytes: int
    active: bool
    summary: str = ""
    cwd: Path | None = None
    project_name: str = "Sem projeto"
    source: str = "codex"
    event_count: int = 0
    last_activity: str = "Aguardando"
    recent_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryStatus:
    path: Path
    name: str
    branch: str = "—"
    dirty_files: int = 0
    remote: str = "—"
    pull_requests: int | None = None
    error: str = ""


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    name: str
    pid: int

