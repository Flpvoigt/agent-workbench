from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from agent_workbench.services import (
    discover_sessions,
    load_repository_paths,
    save_repository_paths,
    session_id_from_path,
    session_summary,
)


class SessionDiscoveryTests(unittest.TestCase):
    def test_discovers_newest_session_and_extracts_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = root / "2026" / "session-123.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text(
                json.dumps({"message": {"content": "Criar painel desktop para acompanhar agents"}}) + "\n",
                encoding="utf-8",
            )
            now = datetime.now()

            result = discover_sessions(root, active_window=timedelta(minutes=5), now=now)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].session_id, "session-123")
            self.assertTrue(result[0].active)
            self.assertIn("painel desktop", result[0].summary)

    def test_invalid_json_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.jsonl"
            path.write_text("not-json\n", encoding="utf-8")
            self.assertEqual(session_summary(path), "")

    def test_extracts_uuid_from_rollout_filename(self) -> None:
        path = Path("rollout-2026-10-09T12-00-00-0199aa11-bb22-7c33-8d44-556677889900.jsonl")
        self.assertEqual(session_id_from_path(path), "0199aa11-bb22-7c33-8d44-556677889900")


class ConfigurationTests(unittest.TestCase):
    def test_repository_paths_round_trip_and_deduplicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            repository = root / "repo"
            repository.mkdir()

            save_repository_paths([repository, repository], config)
            result = load_repository_paths(config)

            self.assertEqual(result, [repository.resolve()])


if __name__ == "__main__":
    unittest.main()

