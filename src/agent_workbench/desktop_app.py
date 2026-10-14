from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

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


class WorkbenchApi:
    """Small, explicit bridge between the trusted local UI and Python services."""

    def __init__(self) -> None:
        self.window: Any = None
        self._lock = threading.RLock()
        self._repository_paths = load_repository_paths()
        self._sessions: dict[str, AgentSession] = {}
        self._repositories: dict[str, RepositoryStatus] = {}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
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
            self._sessions = {session.session_id: session for session in sessions}
            self._repositories = {str(repo.path): repo for repo in repositories}
            return {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "process_count": len(processes),
                "sessions": [self._session_payload(item, repositories) for item in sessions],
                "repositories": [self._repository_payload(item) for item in repositories],
            }

    def resume(self, session_id: str) -> dict[str, str]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"error": "Sessão não encontrada. Atualize o mapa e tente novamente."}
        try:
            resume_session(session.session_id)
        except (OSError, ValueError) as exc:
            return {"error": str(exc)}
        return {"ok": "Sessão aberta em uma nova janela."}

    def open_workspace(self, path: str) -> dict[str, str]:
        allowed = {str(repo.path) for repo in self._repositories.values()}
        allowed.update(
            str(session.cwd or session.path.parent) for session in self._sessions.values()
        )
        if path not in allowed:
            return {"error": "Workspace fora do mapa atual."}
        try:
            open_folder(Path(path))
        except OSError as exc:
            return {"error": str(exc)}
        return {"ok": "Workspace aberto."}

    def add_repository(self) -> dict[str, str]:
        if self.window is None:
            return {"error": "Janela ainda não está pronta."}
        try:
            import webview

            selected = self.window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=str(Path.home()),
            )
        except Exception as exc:  # pragma: no cover - native dialog failures vary by host
            return {"error": str(exc)}
        if not selected:
            return {"cancelled": "true"}
        path = Path(selected[0]).resolve()
        if path not in [item.resolve() for item in self._repository_paths]:
            self._repository_paths.append(path)
            save_repository_paths(self._repository_paths)
        return {"ok": "Repositório adicionado."}

    def remove_repository(self, path: str) -> dict[str, str]:
        selected = Path(path).resolve()
        self._repository_paths = [
            item for item in self._repository_paths if item.resolve() != selected
        ]
        save_repository_paths(self._repository_paths)
        return {"ok": "Repositório removido da lista fixa."}

    @staticmethod
    def _session_payload(
        session: AgentSession, repositories: list[RepositoryStatus]
    ) -> dict[str, Any]:
        repository = WorkbenchApi._repository_for(session, repositories)
        workspace = session.cwd or session.path.parent
        return {
            "id": session.session_id,
            "project": session.project_name,
            "summary": session.summary,
            "activity": session.last_activity,
            "active": session.active,
            "updated_at": session.modified_at.isoformat(timespec="seconds"),
            "updated_time": session.modified_at.strftime("%H:%M"),
            "cwd": str(session.cwd) if session.cwd else "",
            "workspace": str(workspace),
            "source": session.source,
            "event_count": session.event_count,
            "files": list(session.recent_files),
            "repository_path": str(repository.path) if repository else "",
        }

    @staticmethod
    def _repository_payload(repo: RepositoryStatus) -> dict[str, Any]:
        return {
            "path": str(repo.path),
            "name": repo.name,
            "branch": repo.branch,
            "dirty_files": repo.dirty_files,
            "remote": repo.remote,
            "pull_requests": repo.pull_requests,
            "error": repo.error,
        }

    @staticmethod
    def _repository_for(
        session: AgentSession, repositories: list[RepositoryStatus]
    ) -> RepositoryStatus | None:
        if session.cwd:
            session_path = str(session.cwd.resolve()).casefold()
            matches = [
                repo
                for repo in repositories
                if session_path == str(repo.path.resolve()).casefold()
                or session_path.startswith(str(repo.path.resolve()).casefold() + "\\")
            ]
            if matches:
                return max(matches, key=lambda repo: len(str(repo.path)))
        if not session.recent_files:
            return None
        common_folders = ("", "src", "src/agent_workbench", "tests", "scripts", ".github")
        scored: list[tuple[int, RepositoryStatus]] = []
        for repo in repositories:
            score = sum(
                1
                for name in session.recent_files
                if any((repo.path / folder / name).exists() for folder in common_folders)
            )
            if score:
                scored.append((score, repo))
        return max(scored, key=lambda item: item[0])[1] if scored else None


def main() -> None:
    try:
        import webview
    except ImportError as exc:  # pragma: no cover - depends on local installation
        raise SystemExit(
            "pywebview não está instalado. Execute: python -m pip install -e ."
        ) from exc

    api = WorkbenchApi()
    index_path = Path(__file__).parent / "web" / "index.html"
    window = webview.create_window(
        "Agent Workbench · Mission Control",
        url=str(index_path),
        js_api=api,
        width=1500,
        height=900,
        min_size=(1120, 680),
        background_color="#05070d",
    )
    api.window = window
    webview.start(debug=False, private_mode=False)
