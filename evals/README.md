# Evals

这里存放 AZ 的 LLM/Agent 评测；它与 `tests/` 分开，避免默认单元测试意外产生模型调用或成本。

当前只有一个最小、零 LLM 成本的示例：

```bash
uv run python -m evals.basic
```

它展示的执行链路是：

```text
Case（输入和期望答案）
  → Task（answer_project_question）
  → Evaluator（MatchesExpectedAnswer）
  → EvaluationReport（终端报告）
```

后续真实 Agent 评测应继续放在这个目录：Task 改为调用 Agent，Case 增加代表性用户任务，Evaluator 增加工具调用、安全边界与回答质量规则。真实模型或 `LLMJudge` 的评测应显式运行，不加入默认 `tests/` 发现流程。

`agent_assembly.py` 是第一个覆盖实际系统模块的评测。它通过
`core.server.create_agent()` 创建生产配置的 Agent，再用 Pydantic AI 的
`TestModel` 执行一次无真实模型调用的运行；评测模型实际收到的工具、核心
capability，以及已废弃工具是否未出现：

```bash
uv run python -m evals.agent_assembly
# 或直接运行：uv run python evals/agent_assembly.py
```

`live_git_tool_selection.py` 是第一个真实模型 Eval。它让当前配置的
DeepSeek Agent 自主处理“只读检查 Git 状态”的请求，并评测它是否选择
`git_readonly`、避开写入和 Shell 工具，以及是否生成了最终回答。它会调用
真实模型并消耗 token，因此不会由默认测试自动执行：

```bash
# 需要在环境中设置 DEEPSEEK_API_KEY
uv run python -m evals.live_git_tool_selection
```
