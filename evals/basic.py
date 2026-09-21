"""最小可运行的 Pydantic Evals 示例。

运行：uv run python -m evals.basic

这个示例不调用 LLM：它用一个确定性函数演示 Evals 的基本工作流，
即 Case（场景）→ Task（被评函数）→ Evaluator（评分规则）→ Report（报告）。
"""

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext


def answer_project_question(question: str) -> str:
    """被评测的最小任务；后续可替换为真实 Agent 调用。"""
    if "AZ" in question:
        return "AZ 是一个基于 Pydantic AI 的本地智能体应用。"
    return "暂时无法回答该问题。"


class MatchesExpectedAnswer(Evaluator[str, str]):
    """一个确定性评分器：输出与期望答案一致时得 1 分，否则得 0 分。"""

    def evaluate(self, ctx: EvaluatorContext[str, str]) -> float:
        return float(ctx.output == ctx.expected_output)


dataset = Dataset(
    name="az_basics",
    cases=[
        Case(
            name="introduce_az",
            inputs="AZ 是什么？",
            expected_output="AZ 是一个基于 Pydantic AI 的本地智能体应用。",
            metadata={"category": "getting-started"},
        )
    ],
    evaluators=[MatchesExpectedAnswer()],
)


if __name__ == "__main__":
    report = dataset.evaluate_sync(answer_project_question)
    report.print(include_input=True, include_output=True, include_durations=False)
