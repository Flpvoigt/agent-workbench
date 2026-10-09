from __future__ import annotations

import csv
import json
import os
import re
import subprocess
from collections import deque
from datetime import datetime, timedelta
from itertools import islice
from pathlib import Path
from typing import Any, Iterable

from agent_workbench.models import AgentSession, ProcessInfo, RepositoryStatus


CREATE_NEW_CONSOLE = 0x00000010 if os.name == "nt" else 0
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
SESSION_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
FILE_PATTERN = re.compile(
    r"(?i)(?:[a-z]:[\\/]|[./])?(?:[\w .@()-]+[\\/])*[\w.@()-]+\.(?:py|md|json|toml|ya?ml|js|jsx|ts|tsx|html|css|ps1|rs|go)"
)
IGNORED_PROMPT_PREFIXES = (
    "<environment_context",
    "<codex_internal_context",
    "# agents.md instructions",
)
TOOL_LABELS = {
    "apply_patch": "Editando arquivos",
    "exec_command": "Executando comando",
    "write_stdin": "Acompanhando processo",
    "web__run": "Consultando a web",
    "view_image": "Inspecionando imagem",
    "image_gen__imagegen": "Gerando imagem",
    "exec": "Operando ferramenta",
    "functions.exec": "Operando ferramenta",
}


def _run(args: list[str], cwd: Path | None = None, timeout: int = 8) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
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


def _tail_lines(path: Path, max_lines: int = 240, max_bytes: int = 262_144) -> list[str]:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - max_bytes))
            data = stream.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = data.splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]
    return lines[-max_lines:]


def _message_text(payload: dict[str, Any]) -> str:
    if payload.get("type") != "message" or payload.get("role") != "user":
        return ""
    value = _find_text(payload.get("content", ""))
    if value.casefold().startswith(IGNORED_PROMPT_PREFIXES):
        return ""
    return value


def _tool_name(payload: dict[str, Any]) -> str:
    if payload.get("type") not in {"function_call", "custom_tool_call"}:
        return ""
    return str(payload.get("name", ""))


def _activity_label(event_type: str, payload: dict[str, Any]) -> str:
    tool = _tool_name(payload)
    if tool:
        short_name = tool.rsplit("__", 1)[-1]
        return TOOL_LABELS.get(tool, TOOL_LABELS.get(short_name, f"Usando {short_name}"))
    if event_type == "event_msg":
        kind = str(payload.get("type", ""))
        return {
            "task_started": "Analisando tarefa",
            "turn_aborted": "Turno interrompido",
            "task_complete": "Tarefa concluída",
            "agent_message": "Preparando resposta",
        }.get(kind, "")
    if payload.get("type") == "message" and payload.get("role") == "assistant":
        return "Preparando resposta"
    return ""


def _recent_file_names(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("arguments", payload.get("input", ""))
    if not isinstance(raw, str):
        try:
            raw = json.dumps(raw, ensure_ascii=False)
        except TypeError:
            return []
    names: list[str] = []
    for match in FILE_PATTERN.findall(raw):
        name = re.split(r"[\\/]", match)[-1].strip()
        if name and name not in names:
            names.append(name)
    return names


def inspect_session(path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    title = ""
    last_activity = "Aguardando"
    files: deque[str] = deque(maxlen=5)
    event_count = 0

    head_lines: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            head_lines = list(islice(stream, 80))
    except OSError:
        pass

    tail_lines = _tail_lines(path)
    lines = head_lines + tail_lines
    seen: set[str] = set()
    for line in lines:
        fingerprint = line[:160]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_count += 1
        event_type = str(event.get("type", ""))
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if event_type == "session_meta" and not metadata:
            metadata = payload
        message = _message_text(payload)
        if message:
            title = message
        activity = _activity_label(event_type, payload)
        if activity:
            last_activity = activity
        for name in _recent_file_names(payload):
            if name in files:
                files.remove(name)
            files.append(name)

    cwd_value = metadata.get("cwd")
    cwd = Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else None
    project_name = cwd.name if cwd else "Sem projeto"
    if cwd:
        try:
            if cwd.resolve() == Path.home().resolve():
                project_name = "Sessão global"
        except OSError:
            pass
    return {
        "session_id": metadata.get("id") or metadata.get("session_id") or session_id_from_path(path),
        "summary": title or session_summary(path),
        "cwd": cwd,
        "project_name": project_name,
        "source": str(metadata.get("source") or metadata.get("originator") or "codex"),
        "event_count": event_count,
        "last_activity": last_activity,
        "recent_files": tuple(files),
    }


def session_id_from_path(path: Path) -> str:
    matches = SESSION_ID_PATTERN.findall(path.stem)
    return matches[-1] if matches else path.stem


def discover_sessions(
    sessions_dir: Path | None = None,
    *,
    active_window: timedelta = timedelta(minutes=2),
    now: datetime | None = None,
    limit: int = 50,
) -> list[AgentSession]:
    root = sessions_dir or Path.home() / ".codex" / "sessions"
    if not root.is_dir():
        return []
    current = now or datetime.now()
    candidates: list[tuple[Path, os.stat_result]] = []
    for path in root.rglob("*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        candidates.append((path, stat))
    candidates.sort(key=lambda item: item[1].st_mtime, reverse=True)

    sessions: list[AgentSession] = []
    for path, stat in candidates[: max(1, limit)]:
        modified = datetime.fromtimestamp(stat.st_mtime)
        details = inspect_session(path)
        sessions.append(
            AgentSession(
                session_id=str(details["session_id"]),
                path=path,
                modified_at=modified,
                size_bytes=stat.st_size,
                active=current - modified <= active_window,
                summary=str(details["summary"]),
                cwd=details["cwd"],
                project_name=str(details["project_name"]),
                source=str(details["source"]),
                event_count=int(details["event_count"]),
                last_activity=str(details["last_activity"]),
                recent_files=details["recent_files"],
            )
        )
    return sessions


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


def find_git_root(path: Path | None) -> Path | None:
    if path is None:
        return None
    candidate = path.expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for current in (candidate, *candidate.parents):
        if (current / ".git").exists():
            return current
    return None


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

