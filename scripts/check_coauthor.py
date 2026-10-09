from __future__ import annotations

import subprocess
import sys


REQUIRED_TRAILER = "Co-authored-by: GustavoLoes <gustavoloes7@gmail.com>"


def git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return completed.stdout


def commits_without_trailer(base: str) -> list[str]:
    commits = [
        item
        for item in git("rev-list", "--no-merges", f"{base}..HEAD").splitlines()
        if item
    ]
    missing: list[str] = []
    for commit in commits:
        message = git("show", "-s", "--format=%B", commit)
        if REQUIRED_TRAILER.casefold() not in message.casefold():
            missing.append(commit)
    return missing


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    try:
        missing = commits_without_trailer(base)
    except RuntimeError as exc:
        print(f"Erro ao verificar commits: {exc}", file=sys.stderr)
        return 2
    if missing:
        print("Os seguintes commits não registram Gustavo como coautor:", file=sys.stderr)
        for commit in missing:
            print(f"- {commit}", file=sys.stderr)
        print(f"Trailer obrigatório: {REQUIRED_TRAILER}", file=sys.stderr)
        return 1
    print("Todos os commits do PR registram Gustavo como coautor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

