from __future__ import annotations

import csv
import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from agent_workbench.models import AgentSession, ProcessInfo, RepositoryStatus


CREATE_NEW_CONSOLE = 0x00000010 if os.name == "nt" else 0
SESSION_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _run(args: list[str], cwd: Path | None = None, timeout: int = 8) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _find_text(value: Any) -> str:
    """Return a short human-readable text found in a JSON value."""
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned[:140] if len(cleaned) >= 12 else ""
    if isinstance(value, dict):
        preferred = ("title", "summary", "prompt", "text", "content", "message")
        for key in preferred:
            if key in value:
                result = _find_text(value[key])
                if result:
                    return result
        for child in value.values():
            result = _find_text(child)
            if result:
                return result
    if isinstance(value, list):
        for child in value:
            result = _find_text(child)
            if result:
                return result
    return ""


def session_summary(path: Path, max_lines: int = 40) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for index, line in enumerate(stream):
                if index >= max_lines:
                    break
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                result = _find_text(value)
                if result:
                    return result
    except OSError:
        return ""
    return ""


def session_id_from_path(path: Path) -> str:
    matches = SESSION_ID_PATTERN.findall(path.stem)
    return matches[-1] if matches else path.stem


def discover_sessions(
    sessions_dir: Path | None = None,
    *,
    active_window: timedelta = timedelta(minutes=2),
    now: datetime | None = None,
) -> list[AgentSession]:
    root = sessions_dir or Path.home() / ".codex" / "sessions"
    if not root.is_dir():
        return []
    current = now or datetime.now()
    sessions: list[AgentSession] = []
    for path in root.rglob("*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        modified = datetime.fromtimestamp(stat.st_mtime)
        sessions.append(
            AgentSession(
                session_id=session_id_from_path(path),
                path=path,
                modified_at=modified,
                size_bytes=stat.st_size,
                active=current - modified <= active_window,
                summary=session_summary(path),
            )
        )
    return sorted(sessions, key=lambda item: item.modified_at, reverse=True)


def list_codex_processes() -> list[ProcessInfo]:
    if os.name != "nt":
        return []
    code, output, _ = _run(["tasklist", "/FO", "CSV", "/NH"])
    if code != 0:
        return []
    processes: list[ProcessInfo] = []
    for row in csv.reader(output.splitlines()):
        if len(row) < 2:
            continue
        name = row[0]
        if "codex" not in name.casefold():
            continue
        try:
            pid = int(row[1])
        except ValueError:
            continue
        processes.append(ProcessInfo(name=name, pid=pid))
    return processes


def inspect_repository(path: Path) -> RepositoryStatus:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        return RepositoryStatus(path=resolved, name=resolved.name, error="Pasta não encontrada")

    code, branch, error = _run(["git", "branch", "--show-current"], resolved)
    if code != 0:
        return RepositoryStatus(
            path=resolved,
            name=resolved.name,
            error=error or "Não é um repositório Git",
        )

    _, status, _ = _run(["git", "status", "--porcelain"], resolved)
    _, remote, _ = _run(["git", "remote", "get-url", "origin"], resolved)
    pr_code, pr_output, _ = _run(
        ["gh", "pr", "list", "--state", "open", "--json", "number"], resolved
    )
    pull_requests: int | None = None
    if pr_code == 0:
        try:
            pull_requests = len(json.loads(pr_output))
        except (json.JSONDecodeError, TypeError):
            pull_requests = None

    return RepositoryStatus(
        path=resolved,
        name=resolved.name,
        branch=branch or "detached",
        dirty_files=len(status.splitlines()) if status else 0,
        remote=remote or "—",
        pull_requests=pull_requests,
    )


def resume_session(session_id: str) -> None:
    if not session_id.strip():
        raise ValueError("ID de sessão vazio")
    subprocess.Popen(
        ["codex", "resume", session_id],
        creationflags=CREATE_NEW_CONSOLE,
        close_fds=os.name != "nt",
    )


def open_folder(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if os.name == "nt":
        os.startfile(resolved)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(resolved)])


def config_path() -> Path:
    return Path.home() / ".agent-workbench" / "config.json"


def load_repository_paths(path: Path | None = None) -> list[Path]:
    target = path or config_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("repositories", []) if isinstance(data, dict) else []
    if not isinstance(values, list):
        return []
    unique: dict[str, Path] = {}
    for value in values:
        if isinstance(value, str) and value.strip():
            candidate = Path(value).expanduser()
            unique[str(candidate).casefold()] = candidate
    return list(unique.values())


def save_repository_paths(paths: Iterable[Path], path: Path | None = None) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = sorted({str(item.expanduser().resolve()) for item in paths})
    target.write_text(
        json.dumps({"repositories": normalized}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

