import unittest
from pathlib import Path

from config.settings import load_settings


class TestConfig(unittest.TestCase):
    def test_load_settings_includes_observability_defaults(self):
        settings = load_settings(
            {
                "SKILLS_DIR": "./.agents/skills",
                "MCP_CONFIG_PATH": "./mcp.json",
            }
        )

        self.assertIsNone(settings.observability.backend)
        self.assertEqual(
            settings.observability.langfuse_base_url,
            "https://cloud.langfuse.com",
        )
        self.assertIsNone(settings.observability.langfuse_public_key)
        self.assertIsNone(settings.observability.langfuse_secret_key)
        self.assertEqual(settings.az_home, Path.home() / ".az")

    def test_load_settings_includes_mimo_defaults(self):
        settings = load_settings(
            {
                "SKILLS_DIR": "./.agents/skills",
                "MCP_CONFIG_PATH": "./mcp.json",
            }
        )

        self.assertEqual(
            settings.models.mimo.base_url,
            "https://api.xiaomimimo.com/v1",
        )
        self.assertIsNone(settings.models.mimo.api_key)
        self.assertEqual(settings.models.mimo.model_name, "mimo-v2.5-pro")

    def test_load_settings_accepts_mimo_overrides(self):
        settings = load_settings(
            {
                "MIMO_BASE_URL": "https://example.test/v1",
                "MIMO_API_KEY": "test-key",
                "MIMO_MODEL_NAME": "mimo-test",
                "SKILLS_DIR": "./.agents/skills",
                "MCP_CONFIG_PATH": "./mcp.json",
            }
        )

        self.assertEqual(settings.models.mimo.base_url, "https://example.test/v1")
        self.assertEqual(settings.models.mimo.api_key, "test-key")
        self.assertEqual(settings.models.mimo.model_name, "mimo-test")

    def test_load_settings_accepts_observability_overrides(self):
        settings = load_settings(
            {
                "OBS_BACKEND": "langfuse",
                "LANGFUSE_BASE_URL": "https://us.cloud.langfuse.com",
                "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
                "LANGFUSE_SECRET_KEY": "sk-lf-test",
                "SKILLS_DIR": "./.agents/skills",
                "MCP_CONFIG_PATH": "./mcp.json",
            }
        )

        self.assertEqual(settings.observability.backend, "langfuse")
        self.assertEqual(
            settings.observability.langfuse_base_url,
            "https://us.cloud.langfuse.com",
        )
        self.assertEqual(settings.observability.langfuse_public_key, "pk-lf-test")
        self.assertEqual(settings.observability.langfuse_secret_key, "sk-lf-test")

    def test_load_settings_accepts_az_home_override(self):
        settings = load_settings(
            {
                "AZ_HOME": "/tmp/az-home",
                "SKILLS_DIR": "./.agents/skills",
                "MCP_CONFIG_PATH": "./mcp.json",
            }
        )

        self.assertEqual(settings.az_home, Path("/tmp/az-home"))

    def test_load_settings_defaults_skills_and_mcp_to_az_home(self):
        settings = load_settings({"AZ_HOME": "/tmp/az-home"})

        self.assertEqual(settings.skills_dir, Path("/tmp/az-home/skills"))
        self.assertEqual(settings.mcp_config_path, Path("/tmp/az-home/mcp.json"))

    def test_load_settings_accepts_compaction_overrides(self):
        settings = load_settings(
            {
                "CONTEXT_TARGET_TOKENS": "12000",
                "CONTEXT_KEEP_MESSAGES": "8",
                "CONTEXT_KEEP_TOOL_PAIRS": "2",
                "CONTEXT_MAX_PART_TOKENS": "6000",
                "SKILLS_DIR": "./.agents/skills",
                "MCP_CONFIG_PATH": "./mcp.json",
            }
        )

        self.assertEqual(settings.context_target_tokens, 12000)
        self.assertEqual(settings.context_keep_messages, 8)
        self.assertEqual(settings.context_keep_tool_pairs, 2)
        self.assertEqual(settings.context_max_part_tokens, 6000)

    def test_load_settings_accepts_planning_overrides(self):
        settings = load_settings(
            {
                "USE_PLANNING_MODE": "false",
                "PLANNING_CACHE_TTL": "1h",
                "SKILLS_DIR": "./.agents/skills",
                "MCP_CONFIG_PATH": "./mcp.json",
            }
        )

        self.assertFalse(settings.planning_enabled)
        self.assertEqual(settings.planning_cache_ttl, "1h")
