import tempfile
import unittest
from pathlib import Path

from pydantic_ai.messages import ModelRequest, UserPromptPart

from core.context.models import ConversationSummary, SessionMeta
from core.context.session_store import SessionStore


class TestSessionStore(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.az_home = Path(self.temp_dir.name)
        self.store = SessionStore(self.az_home, session_id="session-1")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_session_dir_uses_az_root(self):
        expected = self.az_home / "sessions" / "session-1"

        self.assertEqual(self.store.session_dir, expected)

    def test_round_trip_message_history(self):
        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]

        self.store.save_message_history(messages)
        loaded = self.store.load_message_history()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].parts[0].content, "hello")

    def test_round_trip_meta(self):
        meta = SessionMeta(
            session_id="session-1",
            conversation_id="conversation-1",
            project_path="/tmp/demo-project",
        )

        self.store.save_meta(meta)
        loaded = self.store.load_meta()

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.session_id, "session-1")
        self.assertEqual(loaded.conversation_id, "conversation-1")
        self.assertEqual(loaded.project_path, "/tmp/demo-project")

    def test_round_trip_summary(self):
        summary = ConversationSummary(
            session_id="session-1",
            conversation_id="conversation-1",
            summary_text="Earlier turns discussed context management.",
            turn_count_at_summary=4,
        )

        self.store.save_summary(summary)
        loaded = self.store.load_summary()

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.summary_text, summary.summary_text)
        self.assertEqual(loaded.turn_count_at_summary, 4)
