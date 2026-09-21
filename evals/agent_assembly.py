"""评测 ``core.server.create_agent`` 的 Agent 装配契约。

运行：uv run python -m evals.agent_assembly

该 Eval 不调用真实 LLM。任务先使用生产工厂创建 Agent，再以 TestModel
覆盖运行时模型，从 TestModel 收到的工具 schema 中检查真实装配结果。
"""

from dataclasses import dataclass
from pathlib import Path
import sys
from unittest.mock import Mock

# 允许 ``uv run python evals/agent_assembly.py`` 直接运行；以 ``-m`` 方式
# 运行时，仓库根目录已经在 sys.path 中，因此无需调整。
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_ai.models.test import TestModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from config.settings import load_settings
from core.server import create_agent


@dataclass(frozen=True)
class AgentAssembly:
    tool_names: tuple[str, ...]
    capability_names: tuple[str, ...]
    test_model_output: str


@dataclass(frozen=True)
class ExpectedAgentAssembly:
    required_tools: frozenset[str]
    prohibited_tools: frozenset[str]
    required_capabilities: frozenset[str]


def inspect_agent_assembly(_: None) -> AgentAssembly:
    """创建当前生产 Agent，并用 TestModel 获取其提供给模型的工具 schema。"""
    settings = load_settings(
        {
            "SKILLS_DIR": "./.agents/skills",
            "MCP_CONFIG_PATH": "/tmp/nonexistent-mcp.json",
        }
    )
    agent = create_agent(settings, Path.cwd())
    test_model = TestModel(call_tools=[], custom_output_text="agent assembly checked")

    # TestModel 替代实际 DeepSeek/Ollama：不会发出网络或模型请求。
    with agent.override(model=test_model):
        result = agent.run_sync("列出当前可用能力", deps=Mock())

    request_parameters = test_model.last_model_request_parameters
    if request_parameters is None:
        raise RuntimeError("TestModel 未收到 Agent 的模型请求参数")

    return AgentAssembly(
        tool_names=tuple(
            sorted(tool.name for tool in request_parameters.function_tools)
        ),
        capability_names=tuple(
            type(capability).__name__
            for capability in agent.root_capability.capabilities
        ),
        test_model_output=result.output,
    )


class AgentAssemblyMatchesExpectation(Evaluator[None, AgentAssembly]):
    """验证必须存在的工具/capability，以及必须保持缺失的遗留工具。"""

    def evaluate(
        self, ctx: EvaluatorContext[None, AgentAssembly]
    ) -> float:
        expected = ctx.expected_output
        if not isinstance(expected, ExpectedAgentAssembly):
            raise TypeError("expected_output 必须为 ExpectedAgentAssembly")

        tool_names = set(ctx.output.tool_names)
        capability_names = set(ctx.output.capability_names)
        matches = (
            expected.required_tools <= tool_names
            and tool_names.isdisjoint(expected.prohibited_tools)
            and expected.required_capabilities <= capability_names
            and ctx.output.test_model_output == "agent assembly checked"
        )
        return float(matches)


dataset = Dataset(
    name="az_agent_assembly",
    cases=[
        Case(
            name="production_agent_has_the_expected_safe_surface",
            inputs=None,
            expected_output=ExpectedAgentAssembly(
                required_tools=frozenset(
                    {
                        "git_readonly",
                        "read_file",
                        "read_files",
                        "search_files",
                        "search_files_batch",
                        "run_command",
                        "start_command",
                    }
                ),
                prohibited_tools=frozenset(
                    {
                        "read_code_file",
                        "apply_code_patch",
                        "check_and_modify_code",
                        "generate_code",
                    }
                ),
                required_capabilities=frozenset(
                    {
                        "TieredCompaction",
                        "HandleDeferredToolCalls",
                        "Planning",
                    }
                ),
            ),
        )
    ],
    evaluators=[AgentAssemblyMatchesExpectation()],
)


if __name__ == "__main__":
    report = dataset.evaluate_sync(inspect_agent_assembly)
    report.print(include_input=False, include_output=True, include_durations=False)
