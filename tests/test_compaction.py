import unittest

from pydantic_ai.messages import ToolCallPart
from pydantic_ai_harness.compaction import (
    ClampOversizedMessages,
    ClearToolResults,
    DeduplicateFileReads,
    SummarizingCompaction,
)

from config.settings import load_settings
from core.context.compaction import SUMMARY_PROMPT, build_compaction, file_read_key


class TestCompaction(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = load_settings(
            {
                "CONTEXT_TARGET_TOKENS": "12000",
                "CONTEXT_KEEP_MESSAGES": "8",
                "CONTEXT_KEEP_TOOL_PAIRS": "2",
                "CONTEXT_MAX_PART_TOKENS": "6000",
                "SKILLS_DIR": "./.agents/skills",
                "MCP_CONFIG_PATH": "./mcp.json",
            }
        )

    def test_builds_cheap_to_expensive_compaction_tiers(self):
        compaction = build_compaction(self.settings)

        self.assertEqual(compaction.target_tokens, 12000)
        self.assertEqual(len(compaction.tiers), 4)
        self.assertIsInstance(compaction.tiers[0], ClampOversizedMessages)
        self.assertIsInstance(compaction.tiers[1], DeduplicateFileReads)
        self.assertIsInstance(compaction.tiers[2], ClearToolResults)
        self.assertIsInstance(compaction.tiers[3], SummarizingCompaction)
        self.assertEqual(compaction.tiers[2].keep_pairs, 2)
        self.assertEqual(compaction.tiers[3].keep_messages, 8)

    def test_file_read_key_uses_project_file_path(self):
        call = ToolCallPart(
            tool_name="read_project_file",
            args={"file_path": "core/server.py", "start_line": 1, "end_line": 10},
        )

        self.assertEqual(file_read_key(call), "core/server.py")

    def test_file_read_key_supports_filesystem_style_path(self):
        call = ToolCallPart(tool_name="read_file", args={"path": "README.md"})

        self.assertEqual(file_read_key(call), "README.md")

    def test_file_read_key_ignores_non_file_tools(self):
        call = ToolCallPart(tool_name="git_diff_file", args={"file_path": "core/server.py"})

        self.assertIsNone(file_read_key(call))

    def test_summary_prompt_keeps_existing_az_schema(self):
        self.assertIn("HISTORICAL SUMMARY", SUMMARY_PROMPT)
        self.assertIn("Relevant files and entities", SUMMARY_PROMPT)
        self.assertIn("{messages}", SUMMARY_PROMPT)
