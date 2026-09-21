import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.document import Document

from ui.cli.input_handler import InputHandler, SlashCommandCompleter


class TestInputHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.az_home = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @patch("ui.cli.input_handler.PromptSession")
    def test_initialize_uses_az_session_dir(self, prompt_session_mock):
        handler = InputHandler(self.az_home, session_id="session-1")

        handler.initialize()

        expected_dir = self.az_home / "sessions" / "session-1"
        self.assertEqual(handler.session_dir, expected_dir)
        self.assertEqual(handler.history_file, expected_dir / "az_history")
        prompt_session_mock.assert_called_once()

    def test_slash_completer_lists_commands_for_a_slash_prefix(self):
        completions = list(
            SlashCommandCompleter().get_completions(Document("/"), None)
        )

        self.assertIn("/help", [completion.text for completion in completions])
        self.assertIn("/weather", [completion.text for completion in completions])

    def test_slash_completer_does_not_complete_normal_prompt_text(self):
        completions = list(
            SlashCommandCompleter().get_completions(Document("weather"), None)
        )

        self.assertEqual(completions, [])


if __name__ == "__main__":
    unittest.main()
