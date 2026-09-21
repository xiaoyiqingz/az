import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

from pydantic_ai_harness.compaction import TieredCompaction
from pydantic_ai_harness.planning import Planning
from pydantic_ai.models.test import TestModel
from rich.console import Console

from config.settings import load_settings
from core.readonly_filesystem import PROJECT_FILESYSTEM_TOOLS
from core.server import create_agent
from prompts.prompt import get_smart_assistant_prompt, get_smart_assistant_prompt_bak
from tools.register import build_agent_tools
from ui.cli.output_formatter import AZMarkdown


class TestAgentTools(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = load_settings(
            {
                "SKILLS_DIR": "./.agents/skills",
                "MCP_CONFIG_PATH": "/tmp/nonexistent-mcp.json",
            }
        )

    def test_legacy_code_editing_tools_are_not_registered_by_default(self):
        agent = create_agent(self.settings, Path.cwd())
        tool_names = set(agent._function_toolset.tools.keys())

        self.assertNotIn("read_code_file", tool_names)
        self.assertNotIn("apply_code_patch", tool_names)
        self.assertNotIn("check_and_modify_code", tool_names)
        self.assertNotIn("generate_code", tool_names)

    def test_git_readonly_replaces_the_old_project_review_tools(self):
        agent = create_agent(self.settings, Path.cwd())
        tool_names = {
            name
            for toolset in agent.toolsets
            for name in getattr(toolset, "tools", {})
        }

        self.assertIn("git_readonly", tool_names)
        self.assertNotIn("read_project_file", tool_names)
        self.assertNotIn("search_repo", tool_names)
        self.assertNotIn("exec_review_command", tool_names)

    def test_agent_registers_harness_compaction(self):
        agent = create_agent(self.settings, Path.cwd())

        self.assertTrue(
            any(
                isinstance(capability, TieredCompaction)
                for capability in agent.root_capability.capabilities
            )
        )

    def test_agent_registers_harness_planning_by_default(self):
        agent = create_agent(self.settings, Path.cwd())

        self.assertTrue(
            any(
                isinstance(capability, Planning)
                for capability in agent.root_capability.capabilities
            )
        )

    def test_review_tools_are_registered_via_toolset_registry(self):
        registered = build_agent_tools(self.settings)
        local_toolsets = registered.toolsets[:4]
        tool_names = {
            name for toolset in local_toolsets for name in toolset.tools
        }

        self.assertIn("git_readonly", tool_names)
        self.assertIn("read_files", tool_names)
        self.assertIn("search_files_batch", tool_names)

    def test_tool_status_labels_are_provided_by_registry(self):
        labels = build_agent_tools(self.settings).status_labels

        self.assertEqual(labels["read_file"], "正在读取项目文件")
        self.assertEqual(labels["read_files"], "正在批量读取项目文件")
        self.assertEqual(labels["search_files"], "正在搜索项目代码")
        self.assertEqual(labels["search_files_batch"], "正在批量搜索项目代码")
        self.assertEqual(labels["edit_file"], "正在修改项目文件")
        self.assertEqual(labels["write_file"], "正在写入项目文件")
        self.assertEqual(labels["git_readonly"], "正在检查 Git 仓库")
        self.assertEqual(labels["write_plan"], "正在更新执行计划")

    def test_project_filesystem_exposes_controlled_write_tools(self):
        self.assertEqual(
            PROJECT_FILESYSTEM_TOOLS,
            {
                "read_file",
                "write_file",
                "edit_file",
                "list_directory",
                "search_files",
                "find_files",
                "create_directory",
                "file_info",
            },
        )

    def test_smart_prompt_uses_compact_generic_tool_rules(self):
        prompt = get_smart_assistant_prompt_bak()

        self.assertIn("[工具规则]", prompt)
        self.assertIn("随请求以 schema 提供", prompt)
        self.assertIn("`find_files`", prompt)
        self.assertIn("`search_files`", prompt)
        self.assertIn("`read_files`", prompt)
        self.assertIn("`search_files_batch`", prompt)
        self.assertIn("`expected_hash`", prompt)
        self.assertIn('git_readonly(operation="status", repository_path=...)', prompt)
        self.assertIn("skill 或 MCP", prompt)
        self.assertIn("用户提供 URL 并要求读取或核实", prompt)
        self.assertNotIn("[工具使用优先级]", prompt)
        self.assertNotIn("MCP toolsets", prompt)
        self.assertNotIn("[可用能力]", prompt)
        self.assertNotIn("`get_current_time`:", prompt)

    def test_previous_smart_prompt_is_available_for_comparison(self):
        prompt = get_smart_assistant_prompt()

        self.assertIn("[工具使用优先级]", prompt)
        self.assertIn("MCP toolsets", prompt)
        self.assertIn("`read_files`", prompt)
        self.assertIn("`search_files_batch`", prompt)

    def test_registered_tools_are_sent_to_the_model_without_prompt_catalog(self):
        agent = create_agent(self.settings, Path.cwd())
        model = TestModel(call_tools=[], custom_output_text="ok")

        with agent.override(model=model):
            agent.run_sync("请告诉我当前有哪些能力", deps=Mock())

        self.assertIsNotNone(model.last_model_request_parameters)
        tool_names = {
            tool.name for tool in model.last_model_request_parameters.function_tools
        }
        self.assertTrue(
            {"get_current_time", "get_weather", "duckduckgo_search"}.issubset(
                tool_names
            )
        )
        self.assertTrue({"run_command", "start_command"}.issubset(tool_names))

    def test_hidden_tool_result_names_are_provided_by_registry(self):
        hidden_names = build_agent_tools(self.settings).hidden_result_names

        self.assertIn("list_skills", hidden_names)
        self.assertIn("load_skill", hidden_names)
        self.assertIn("read_skill_resource", hidden_names)
        self.assertIn("run_skill_script", hidden_names)

    def test_cli_markdown_headings_are_left_aligned(self):
        output = StringIO()
        Console(file=output, width=30, force_terminal=False).print(
            AZMarkdown("## 标题")
        )

        self.assertTrue(output.getvalue().startswith("标题"))

    def test_smart_prompt_no_longer_mentions_legacy_code_editing_tools(self):
        prompt = get_smart_assistant_prompt_bak()

        self.assertNotIn("`read_code_file`", prompt)
        self.assertNotIn("`apply_code_patch`", prompt)
        self.assertNotIn("`check_and_modify_code`", prompt)
        self.assertNotIn("`generate_code`", prompt)
