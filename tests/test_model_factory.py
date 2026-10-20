import unittest

from config.settings import load_settings
from models.factory import build_model


class TestModelFactory(unittest.TestCase):
    def test_defaults_to_deepseek(self):
        settings = load_settings({"DEEPSEEK_API_KEY": "sk-test"})

        self.assertEqual(settings.models.provider, "deepseek")
        self.assertEqual(build_model(settings).system, "deepseek")

    def test_builds_configured_provider(self):
        settings = load_settings(
            {
                "AZ_MODEL_PROVIDER": "ollama",
                "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1",
                "OLLAMA_MODEL_NAME": "qwen3:14b",
            }
        )

        model = build_model(settings)

        self.assertEqual(model.model_name, "qwen3:14b")
        self.assertEqual(model.system, "ollama")

    def test_rejects_unknown_provider(self):
        with self.assertRaises(ValueError):
            load_settings({"AZ_MODEL_PROVIDER": "unknown"})


if __name__ == "__main__":
    unittest.main()
