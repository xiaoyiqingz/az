import tempfile
import unittest
from pathlib import Path

from pydantic_ai.messages import ModelRequest, UserPromptPart

from core.context.models import SessionMeta
from core.context.session_runtime import initialize_session_runtime
from core.context.session_store import SessionStore


class TestSessionRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.az_home = Path(self.temp_dir.name)
        self.cwd = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initialize_session_runtime_creates_meta_for_new_session(self):
        runtime = initialize_session_runtime(
            self.az_home,
            session_id="session-1",
            requested_project_path=str(self.cwd / "repo-a"),
            cwd=self.cwd,
        )

        saved_meta = runtime.session_store.load_meta()
        self.assertEqual(runtime.project_path, self.cwd / "repo-a")
        self.assertFalse(runtime.ignored_cli_project_path)
        self.assertEqual(runtime.conversation_id, "session-1")
        self.assertIsNotNone(saved_meta)
        assert saved_meta is not None
        self.assertEqual(saved_meta.project_path, str(self.cwd / "repo-a"))
        self.assertFalse(saved_meta.resumed)

    def test_initialize_session_runtime_marks_existing_history_as_resumed(self):
        store = SessionStore(self.az_home, session_id="session-1")
        store.save_message_history(
            [ModelRequest(parts=[UserPromptPart(content="hello")])]
        )

        runtime = initialize_session_runtime(
            self.az_home,
            session_id="session-1",
            requested_project_path=str(self.cwd / "repo-a"),
            cwd=self.cwd,
        )

        saved_meta = runtime.session_store.load_meta()
        self.assertEqual(len(runtime.all_messages), 1)
        self.assertIsNotNone(saved_meta)
        assert saved_meta is not None
        self.assertTrue(saved_meta.resumed)

    def test_initialize_session_runtime_strictly_restores_project_path(self):
        store = SessionStore(self.az_home, session_id="session-1")
        store.save_meta(
            SessionMeta(
                session_id="session-1",
                conversation_id="conversation-1",
                project_path=str(self.cwd / "repo-meta"),
            )
        )

        runtime = initialize_session_runtime(
            self.az_home,
            session_id="session-1",
            requested_project_path=str(self.cwd / "repo-cli"),
            cwd=self.cwd,
        )

        self.assertEqual(runtime.project_path, self.cwd / "repo-meta")
        self.assertTrue(runtime.ignored_cli_project_path)

    def test_initialize_session_runtime_backfills_missing_project_path(self):
        store = SessionStore(self.az_home, session_id="session-1")
        store.save_meta(
            SessionMeta(
                session_id="session-1",
                conversation_id="conversation-1",
            )
        )

        runtime = initialize_session_runtime(
            self.az_home,
            session_id="session-1",
            cwd=self.cwd,
        )

        saved_meta = runtime.session_store.load_meta()
        self.assertEqual(runtime.project_path, self.cwd)
        self.assertIsNotNone(saved_meta)
        assert saved_meta is not None
        self.assertEqual(saved_meta.project_path, str(self.cwd))


if __name__ == "__main__":
    unittest.main()
