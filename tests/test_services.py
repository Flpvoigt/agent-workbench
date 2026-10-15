from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import agent_workbench.services as services
from agent_workbench.services import (
    discover_sessions,
    inspect_session,
    load_repository_paths,
    save_repository_paths,
    session_id_from_path,
    session_summary,
)


class SessionDiscoveryTests(unittest.TestCase):
    def test_zero_limit_returns_no_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "session.jsonl").write_text("{}\n", encoding="utf-8")

            self.assertEqual(discover_sessions(root, limit=0), [])

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

    def test_session_details_use_real_metadata_activity_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "rollout-0199aa11-bb22-7c33-8d44-556677889900.jsonl"
            events = [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "0199aa11-bb22-7c33-8d44-556677889900",
                        "cwd": str(root / "agent-workbench"),
                        "source": "cli",
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Redesenhe o mapa de agents"}],
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "name": "apply_patch",
                        "input": "*** Update File: src/agent_workbench/graph.py",
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

            details = inspect_session(path)

            self.assertEqual(details["project_name"], "agent-workbench")
            self.assertEqual(details["summary"], "Redesenhe o mapa de agents")
            self.assertEqual(details["last_activity"], "Editando arquivos")
            self.assertIn("graph.py", details["recent_files"])

    def test_distinct_events_with_a_long_common_prefix_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            common_prefix = "x" * 200
            events = [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "name": "apply_patch",
                        "input": f"{common_prefix} src/first.py",
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "name": "apply_patch",
                        "input": f"{common_prefix} src/second.py",
                    },
                },
            ]
            path.write_text(
                "\n".join(json.dumps(event) for event in events) + "\n",
                encoding="utf-8",
            )

            details = inspect_session(path)

            self.assertEqual(details["event_count"], 2)
            self.assertEqual(details["recent_files"], ("first.py", "second.py"))

    def test_tracks_common_source_script_and_data_file_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            events = [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": file_name,
                    },
                }
                for file_name in (
                    "src/Main.java",
                    "db/schema.sql",
                    "scripts/run.sh",
                    "data/report.csv",
                    "config/layout.xml",
                )
            ]
            path.write_text(
                "\n".join(json.dumps(event) for event in events) + "\n",
                encoding="utf-8",
            )

            details = inspect_session(path)

            self.assertEqual(
                details["recent_files"],
                ("Main.java", "schema.sql", "run.sh", "report.csv", "layout.xml"),
            )

    def test_tracks_common_build_and_configuration_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            events = [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": file_name,
                    },
                }
                for file_name in (
                    "Dockerfile",
                    ".env",
                    "config/app.ini",
                    "android/settings.gradle",
                    "poetry.lock",
                )
            ]
            path.write_text(
                "\n".join(json.dumps(event) for event in events) + "\n",
                encoding="utf-8",
            )

            details = inspect_session(path)

            self.assertEqual(
                details["recent_files"],
                ("Dockerfile", ".env", "app.ini", "settings.gradle", "poetry.lock"),
            )

    def test_tracks_common_document_and_image_files(self) -> None:
        payload = {
            "arguments": (
                "reports/summary.pdf docs/brief.docx data/metrics.xlsx "
                "slides/demo.pptx assets/diagram.svg images/screenshot.png "
                "images/photo.jpg images/preview.webp"
            )
        }

        self.assertEqual(
            services._recent_file_names(payload),
            [
                "summary.pdf",
                "brief.docx",
                "metrics.xlsx",
                "demo.pptx",
                "diagram.svg",
                "screenshot.png",
                "photo.jpg",
                "preview.webp",
            ],
        )


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


class CommandExecutionTests(unittest.TestCase):
    @patch("agent_workbench.services.subprocess.run")
    def test_background_commands_do_not_open_a_window(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "ok"
        run_mock.return_value.stderr = ""

        code, output, error = services._run(["git", "--version"])

        self.assertEqual((code, output, error), (0, "ok", ""))
        self.assertEqual(
            run_mock.call_args.kwargs["creationflags"],
            services.CREATE_NO_WINDOW,
        )


if __name__ == "__main__":
    unittest.main()

