import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import load_settings
from onboarding import ensure_provider_configured
from onboarding.env_file import read_env_file, write_env_values
from onboarding.fields import missing_provider_fields
from ui.cli.model_command import handle_model_command, is_model_command

BASE_ENV = {
    "AZ_MODEL_PROVIDER": "deepseek",
    "DEEPSEEK_MODEL_NAME": "deepseek-chat",
    "DEEPSEEK_API_KEY": "sk-ds",
    "OBS_BACKEND": "",
    "USE_PLANNING_MODE": "false",
}


def _async_answers(*values):
    answers = iter(values)

    def factory(*_args, **_kwargs):
        prompt = MagicMock()
        prompt.unsafe_ask_async = AsyncMock(side_effect=lambda: next(answers))
        return prompt

    return factory


class TestMissingProviderFields(unittest.TestCase):
    def test_reports_only_fields_of_requested_provider(self):
        keys = [f.key for f in missing_provider_fields(BASE_ENV, "qwen")]

        self.assertEqual(keys, ["QWEN_BASE_URL", "QWEN_MODEL_NAME", "QWEN_API_KEY"])

    def test_configured_provider_has_nothing_missing(self):
        self.assertEqual(missing_provider_fields(BASE_ENV, "deepseek"), [])


class TestModelCommand(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.az_home = Path(self.temp_dir.name)
        write_env_values(self.az_home, BASE_ENV)
        self.env_patch = patch.dict(os.environ, {"AZ_HOME": str(self.az_home)}, clear=True)
        self.env_patch.start()
        settings = load_settings({**BASE_ENV, "AZ_HOME": str(self.az_home)})
        self.session = SimpleNamespace(
            deps=SimpleNamespace(settings=settings),
            switch_model=MagicMock(side_effect=self._switch),
        )
        self.switched_settings = None

    def tearDown(self):
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _switch(self, settings):
        self.switched_settings = settings
        return SimpleNamespace(model_name=getattr(settings.models, settings.models.provider).model_name)

    def _run(self, user_input):
        return asyncio.run(handle_model_command(self.session, user_input))

    def test_is_model_command(self):
        self.assertTrue(is_model_command("/model"))
        self.assertTrue(is_model_command("  /MODEL qwen "))
        self.assertFalse(is_model_command("/modelx"))
        self.assertFalse(is_model_command("tell me about /model"))

    def test_switch_to_configured_provider_does_not_prompt(self):
        write_env_values(
            self.az_home,
            {"MIMO_BASE_URL": "https://mimo.example/v1", "MIMO_MODEL_NAME": "mimo-x", "MIMO_API_KEY": "k"},
        )

        with patch("onboarding.wizard.questionary") as questionary:
            message = self._run("/model mimo")

        questionary.text.assert_not_called()
        questionary.password.assert_not_called()
        self.assertIn("mimo-x", message)
        self.assertEqual(self.switched_settings.models.provider, "mimo")
        self.assertEqual(read_env_file(self.az_home / ".env")["AZ_MODEL_PROVIDER"], "mimo")

    def test_switch_to_unconfigured_provider_asks_for_missing_fields(self):
        with (
            patch("onboarding.wizard.questionary.print"),
            patch(
                "onboarding.wizard.questionary.text",
                side_effect=_async_answers("https://qwen.example/v1", "qwen-max"),
            ),
            patch("onboarding.wizard.questionary.password", side_effect=_async_answers("sk-qwen")),
        ):
            message = self._run("/model qwen")

        env = read_env_file(self.az_home / ".env")
        self.assertEqual(env["AZ_MODEL_PROVIDER"], "qwen")
        self.assertEqual(env["QWEN_BASE_URL"], "https://qwen.example/v1")
        self.assertEqual(env["QWEN_API_KEY"], "sk-qwen")
        self.assertEqual(self.switched_settings.models.qwen.model_name, "qwen-max")
        self.assertIn("qwen-max", message)

    def test_menu_selection_is_used_without_argument(self):
        write_env_values(self.az_home, {"OLLAMA_BASE_URL": "http://h:11434/v1", "OLLAMA_MODEL_NAME": "llama3"})

        with patch("onboarding.wizard.questionary.select", side_effect=_async_answers("ollama")):
            message = self._run("/model")

        self.assertEqual(self.switched_settings.models.provider, "ollama")
        self.assertIn("llama3", message)

    def test_unknown_provider_changes_nothing(self):
        message = self._run("/model gpt")

        self.assertIn("未知模型", message)
        self.session.switch_model.assert_not_called()

    def test_cancel_keeps_model_and_env(self):
        def cancelled(*_args, **_kwargs):
            prompt = MagicMock()
            prompt.unsafe_ask_async = AsyncMock(side_effect=KeyboardInterrupt)
            return prompt

        with (
            patch("onboarding.wizard.questionary.print"),
            patch("onboarding.wizard.questionary.text", side_effect=cancelled),
        ):
            message = self._run("/model qwen")

        self.assertIn("已取消", message)
        self.session.switch_model.assert_not_called()
        self.assertEqual(read_env_file(self.az_home / ".env")["AZ_MODEL_PROVIDER"], "deepseek")


class TestEnsureProviderConfigured(unittest.TestCase):
    def test_keeps_other_settings_untouched(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            az_home = Path(temp_dir)
            write_env_values(az_home, {**BASE_ENV, "TAVILY_API_KEY": "tv"})

            asyncio.run(ensure_provider_configured(az_home, "deepseek"))

            self.assertEqual(read_env_file(az_home / ".env"), {**BASE_ENV, "TAVILY_API_KEY": "tv"})


if __name__ == "__main__":
    unittest.main()
