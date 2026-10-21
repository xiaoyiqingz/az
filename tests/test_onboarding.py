import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.console import Console

from onboarding import ensure_env_configured
from onboarding.env_file import read_env_file, write_env_values
from onboarding.fields import missing_fields

COMPLETE_DEEPSEEK = {
    "AZ_MODEL_PROVIDER": "deepseek",
    "DEEPSEEK_MODEL_NAME": "deepseek-chat",
    "DEEPSEEK_API_KEY": "sk-test",
    "OBS_BACKEND": "",
    "USE_PLANNING_MODE": "true",
    "PLANNING_CACHE_TTL": "5m",
}


def _keys(values):
    return [field.key for field in missing_fields(values)]


def _answers(*values):
    """Build questionary prompt mocks that return the given answers in order."""
    answers = iter(values)

    def factory(*_args, **_kwargs):
        prompt = MagicMock()
        prompt.unsafe_ask.side_effect = lambda: next(answers)
        return prompt

    return factory


class TestMissingFields(unittest.TestCase):
    def test_empty_env_starts_with_model_provider(self):
        self.assertEqual(_keys({})[0], "AZ_MODEL_PROVIDER")

    def test_complete_deepseek_config_has_nothing_missing(self):
        self.assertEqual(_keys(COMPLETE_DEEPSEEK), [])

    def test_only_selected_provider_fields_are_required(self):
        values = {**COMPLETE_DEEPSEEK, "AZ_MODEL_PROVIDER": "qwen"}

        self.assertEqual(_keys(values), ["QWEN_BASE_URL", "QWEN_MODEL_NAME", "QWEN_API_KEY"])

    def test_empty_api_key_counts_as_missing(self):
        values = {**COMPLETE_DEEPSEEK, "DEEPSEEK_API_KEY": ""}

        self.assertEqual(_keys(values), ["DEEPSEEK_API_KEY"])

    def test_empty_obs_backend_means_disabled_but_key_must_exist(self):
        values = dict(COMPLETE_DEEPSEEK)
        del values["OBS_BACKEND"]

        self.assertEqual(_keys(values), ["OBS_BACKEND"])

    def test_langfuse_requires_its_credentials(self):
        values = {**COMPLETE_DEEPSEEK, "OBS_BACKEND": "langfuse"}

        self.assertEqual(
            _keys(values),
            ["LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
        )

    def test_planning_ttl_not_required_when_planning_disabled(self):
        values = {**COMPLETE_DEEPSEEK, "USE_PLANNING_MODE": "false"}
        del values["PLANNING_CACHE_TTL"]

        self.assertEqual(_keys(values), [])

    def test_invalid_values_are_reported(self):
        values = {
            **COMPLETE_DEEPSEEK,
            "AZ_MODEL_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": "localhost:11434",
            "OLLAMA_MODEL_NAME": "qwen3:8b",
        }

        self.assertEqual(_keys(values), ["OLLAMA_BASE_URL"])


class TestEnvFile(unittest.TestCase):
    def test_write_preserves_comments_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "home" / ".env"
            env_path.parent.mkdir()
            env_path.write_text("# keep me\nMYSQL_HOST=127.0.0.1\nDEEPSEEK_API_KEY=\n")
            env_path.chmod(0o640)

            write_env_values(env_path.parent, {"DEEPSEEK_API_KEY": "sk-new", "OBS_BACKEND": ""})

            content = env_path.read_text()
            self.assertIn("# keep me", content)
            self.assertEqual(
                read_env_file(env_path),
                {"MYSQL_HOST": "127.0.0.1", "DEEPSEEK_API_KEY": "sk-new", "OBS_BACKEND": ""},
            )
            self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o640)

    def test_new_env_uses_default_file_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_umask = os.umask(0o022)
            try:
                env_path = write_env_values(Path(temp_dir), {"K": "v"})
            finally:
                os.umask(old_umask)

            self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o644)

    def test_write_never_follows_symlink_outside_home(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            outside = Path(temp_dir) / "outside.env"
            home.mkdir()
            outside.write_text("X=1\n")
            outside.chmod(0o644)
            (home / ".env").symlink_to(outside)

            with self.assertRaises(SystemExit):
                write_env_values(home, {"K": "secret"})

            self.assertEqual(outside.read_text(), "X=1\n")
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o644)
            self.assertTrue((home / ".env").is_symlink())

    def test_write_only_touches_env_inside_home(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "new-home"

            written = write_env_values(home, {"K": "v"})

            self.assertEqual(written, home / ".env")
            self.assertEqual(sorted(p.name for p in Path(temp_dir).rglob("*")), [".env", "new-home"])

    def test_write_rejects_relative_home(self):
        with self.assertRaises(ValueError):
            write_env_values(Path("relative-home"), {"K": "v"})

    def test_read_ignores_process_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "from-shell"}):
                self.assertEqual(read_env_file(env_path), {})


class TestEnsureEnvConfigured(unittest.TestCase):
    def setUp(self):
        # 向导界面输出到内存，避免污染测试输出。
        console_patch = patch("onboarding.wizard._console", Console(file=io.StringIO()))
        console_patch.start()
        self.addCleanup(console_patch.stop)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.az_home = Path(self.temp_dir.name)
        self.env_path = self.az_home / ".env"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_complete_env_does_not_prompt(self):
        write_env_values(self.az_home, COMPLETE_DEEPSEEK)

        with patch("onboarding.wizard.questionary") as questionary:
            ensure_env_configured(self.az_home)

        questionary.select.assert_not_called()

    def test_non_interactive_terminal_lists_missing_keys(self):
        with patch("onboarding.wizard._is_interactive", return_value=False):
            with self.assertRaises(SystemExit) as ctx:
                ensure_env_configured(self.az_home)

        self.assertIn("AZ_MODEL_PROVIDER", str(ctx.exception.code))
        self.assertFalse(self.env_path.exists())

    @patch("onboarding.wizard._is_interactive", return_value=True)
    def test_wizard_asks_in_order_and_writes_env(self, _interactive):
        with (
            patch("onboarding.wizard.questionary.print"),
            patch("onboarding.wizard.questionary.select", side_effect=_answers("mimo", "", "1h")),
            patch(
                "onboarding.wizard.questionary.text",
                side_effect=_answers("https://mimo.example/v1", "mimo-test"),
            ),
            patch("onboarding.wizard.questionary.password", side_effect=_answers("mimo-key")),
            patch("onboarding.wizard.questionary.confirm", side_effect=_answers(True)),
        ):
            ensure_env_configured(self.az_home)

        self.assertEqual(
            read_env_file(self.env_path),
            {
                "AZ_MODEL_PROVIDER": "mimo",
                "MIMO_BASE_URL": "https://mimo.example/v1",
                "MIMO_MODEL_NAME": "mimo-test",
                "MIMO_API_KEY": "mimo-key",
                "OBS_BACKEND": "",
                "USE_PLANNING_MODE": "true",
                "PLANNING_CACHE_TTL": "1h",
            },
        )

    @patch("onboarding.wizard._is_interactive", return_value=True)
    def test_only_missing_fields_are_asked(self, _interactive):
        values = dict(COMPLETE_DEEPSEEK)
        del values["DEEPSEEK_API_KEY"]
        write_env_values(self.az_home, values)

        with (
            patch("onboarding.wizard.questionary.print"),
            patch("onboarding.wizard.questionary.select") as select,
            patch("onboarding.wizard.questionary.password", side_effect=_answers("sk-added")),
        ):
            ensure_env_configured(self.az_home)

        select.assert_not_called()
        self.assertEqual(read_env_file(self.env_path)["DEEPSEEK_API_KEY"], "sk-added")

    @patch("onboarding.wizard._is_interactive", return_value=True)
    def test_reconfigure_keeps_secret_when_answer_is_empty(self, _interactive):
        write_env_values(self.az_home, COMPLETE_DEEPSEEK)

        with (
            patch("onboarding.wizard.questionary.print"),
            patch("onboarding.wizard.questionary.select", side_effect=_answers("deepseek", "", "5m")),
            patch("onboarding.wizard.questionary.text", side_effect=_answers("deepseek-chat")),
            patch("onboarding.wizard.questionary.password", side_effect=_answers("")),
            patch("onboarding.wizard.questionary.confirm", side_effect=_answers(True)),
        ):
            ensure_env_configured(self.az_home, reconfigure=True)

        self.assertEqual(read_env_file(self.env_path)["DEEPSEEK_API_KEY"], "sk-test")

    @patch("onboarding.wizard._is_interactive", return_value=True)
    def test_cancel_leaves_env_untouched(self, _interactive):
        def cancelled(*_args, **_kwargs):
            prompt = MagicMock()
            prompt.unsafe_ask.side_effect = KeyboardInterrupt
            return prompt

        with (
            patch("onboarding.wizard.questionary.print"),
            patch("onboarding.wizard.questionary.select", side_effect=cancelled),
        ):
            with self.assertRaises(SystemExit):
                ensure_env_configured(self.az_home)

        self.assertFalse(self.env_path.exists())


if __name__ == "__main__":
    unittest.main()
