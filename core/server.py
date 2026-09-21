"""共享的 Agent 会话执行服务。

本模块不依赖终端、HTTP 或 Web UI。不同交互入口只需打开一个会话，
消费 ``stream_session_turn`` 产生的 Pydantic AI 事件，并按各自协议渲染。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
import asyncio
import os
from pathlib import Path
from typing import Any

from httpx import AsyncClient
from pydantic_ai import Agent, DeferredToolRequests, ToolDenied, UsageLimitExceeded
from pydantic_ai.capabilities import HandleDeferredToolCalls
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.usage import UsageLimits
from pydantic_ai_harness import Shell
from pydantic_ai_harness.planning import Planning

from config.settings import Settings
from infra.observability import configure_observability, instrument_http_client
from models.deepseek import build_deepseek_model
from prompts.prompt import get_smart_assistant_prompt
from tools.register import build_agent_tools

from .context.compaction import build_compaction
from .context.deps import Deps
from .context.models import UsageLimitRecovery
from .context.session_runtime import SessionRuntime, initialize_session_runtime
from .readonly_filesystem import build_project_filesystem
from .shell_approval import (
    ShellApprovalManager,
    ShellApprovalRequest,
    shell_approval_registry,
)


SHELL_EXECUTION_TOOLS = frozenset({"run_command", "start_command"})
MAX_RECOVERY_TRANSCRIPT_CHARS = 30_000


@dataclass(frozen=True)
class UsageLimitReached:
    message: str
    request_limit: int
    tool_calls_limit: int


def create_agent(settings: Settings, project_path: Path) -> Agent:
    """Build the Agent configured for one session's bound project."""
    registered_tools = build_agent_tools(settings)

    shell_toolset = Shell(
        cwd=project_path,
        denied_commands=[],
        default_timeout=30.0,
        max_output_chars=50_000,
        persist_cwd=False,
        allow_interactive=False,
        env=_build_shell_environment(),
    ).get_toolset().approval_required(
        lambda _ctx, tool_def, _args: tool_def.name in SHELL_EXECUTION_TOOLS
    )
    capabilities = [
        build_compaction(settings),
        build_project_filesystem(project_path),
        HandleDeferredToolCalls(handler=_handle_shell_approvals),
    ]
    if settings.planning_enabled:
        capabilities.append(Planning(cache_ttl=settings.planning_cache_ttl))

    agent_kwargs = {
        "model": build_deepseek_model(settings),
        "deps_type": Deps,
        "instructions": get_smart_assistant_prompt(),
        "capabilities": capabilities,
    }
    agent_kwargs["toolsets"] = [shell_toolset, *registered_tools.toolsets]

    return Agent(**agent_kwargs)


def _build_shell_environment() -> dict[str, str]:
    """Provide build tools only the minimum conventional process environment."""
    return {
        key: value
        for key in ("PATH", "HOME", "TMPDIR")
        if (value := os.environ.get(key)) is not None
    }


@dataclass
class AgentSession:
    """Resources and state shared by every turn in one open session."""

    runtime: SessionRuntime
    agent: Agent
    deps: Deps
    all_messages: list[ModelMessage]

    @property
    def session_id(self) -> str:
        return self.deps.session_id

    @property
    def project_path(self) -> Path:
        return self.runtime.project_path

    @property
    def ignored_requested_project_path(self) -> bool:
        return self.runtime.ignored_cli_project_path

    def save_history(self) -> None:
        """Persist the latest successfully completed history."""
        self.runtime.session_store.save_message_history(self.all_messages)


@asynccontextmanager
async def open_agent_session(
    settings: Settings,
    session_id: str,
    requested_project_path: str | None = None,
) -> AsyncIterator[AgentSession]:
    """Open a session without assuming how its events will be presented."""
    configure_observability(settings)
    runtime = initialize_session_runtime(
        az_home=settings.az_home,
        session_id=session_id,
        requested_project_path=requested_project_path,
    )
    all_messages, migrated = _strip_legacy_system_prompts(runtime.all_messages)
    if migrated:
        runtime.session_store.save_message_history(all_messages)
    agent = create_agent(settings, runtime.project_path)

    shell_approvals = ShellApprovalManager(session_id)
    shell_approval_registry.register(shell_approvals)
    try:
        async with AsyncClient() as client:
            instrument_http_client(client, settings)
            deps = Deps(
                client=client,
                session_id=session_id,
                conversation_id=runtime.conversation_id,
                az_home=settings.az_home,
                project_path=runtime.project_path,
                settings=settings,
                session_store=runtime.session_store,
                shell_approvals=shell_approvals,
            )
            yield AgentSession(
                runtime=runtime,
                agent=agent,
                deps=deps,
                all_messages=all_messages,
            )
    finally:
        shell_approval_registry.unregister(shell_approvals)


async def stream_session_turn(
    session: AgentSession,
    user_input: str,
) -> AsyncIterator[Any]:
    """Run and persist one turn, yielding provider-independent stream events.

    Consumers may format these events for a terminal, encode them as SSE, or
    turn them into a non-streaming API response. History is written only after
    the stream completes successfully.
    """
    run_result = None
    transcript: list[str] = []
    try:
        async with session.agent.run_stream_events(
            user_input,
            deps=session.deps,
            message_history=session.all_messages,
            conversation_id=session.runtime.conversation_id,
            metadata={
                "session_id": session.session_id,
                "project_path": str(session.project_path),
            },
            usage_limits=_usage_limits(session.deps.settings),
        ) as stream:
            event_iterator = stream.__aiter__()
            event_task = asyncio.ensure_future(anext(event_iterator))
            approval_task = asyncio.create_task(session.deps.shell_approvals.next_request())
            try:
                while True:
                    done, _ = await asyncio.wait(
                        {event_task, approval_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if approval_task in done:
                        yield approval_task.result()
                        approval_task = asyncio.create_task(
                            session.deps.shell_approvals.next_request()
                        )
                    if event_task not in done:
                        continue
                    try:
                        event = event_task.result()
                    except StopAsyncIteration:
                        break
                    _append_recovery_transcript(transcript, event)
                    if isinstance(event, AgentRunResultEvent):
                        run_result = event.result
                    yield event
                    event_task = asyncio.ensure_future(anext(event_iterator))
            finally:
                event_task.cancel()
                approval_task.cancel()
                await asyncio.gather(
                    event_task, approval_task, return_exceptions=True
                )
    except UsageLimitExceeded as exc:
        recovery = UsageLimitRecovery(
            session_id=session.session_id,
            original_prompt=user_input,
            tool_transcript="\n\n".join(transcript)[-MAX_RECOVERY_TRANSCRIPT_CHARS:],
            limit_message=str(exc),
        )
        session.runtime.session_store.save_usage_limit_recovery(recovery)
        yield UsageLimitReached(
            message=str(exc),
            request_limit=session.deps.settings.request_limit,
            tool_calls_limit=session.deps.settings.tool_calls_limit,
        )
        return

    if run_result is None:
        raise RuntimeError("Agent 流式运行未返回最终结果")

    session.all_messages = run_result.all_messages()
    session.save_history()
    session.runtime.session_store.clear_usage_limit_recovery()


def _usage_limits(settings: Settings) -> UsageLimits:
    return UsageLimits(
        request_limit=settings.request_limit,
        tool_calls_limit=settings.tool_calls_limit,
    )


def _append_recovery_transcript(transcript: list[str], event: Any) -> None:
    if isinstance(event, FunctionToolCallEvent):
        transcript.append(f"工具调用 {event.part.tool_name}: {event.part.args}")
    elif isinstance(event, FunctionToolResultEvent):
        transcript.append(f"工具结果: {event.part.content}")


def build_usage_limit_prompt(recovery: UsageLimitRecovery, action: str) -> str:
    """Build a fresh, budgeted run from persisted evidence after a limit hit."""
    if action == "summarize":
        instruction = (
            "不要调用任何工具。仅基于以下已保存的工具结果，给出阶段结论、"
            "已核实事实、尚未验证的缺口与建议下一步。"
        )
    else:
        instruction = (
            "继续完成原任务。优先使用以下已保存的工具结果，避免重复读取；"
            "仅补充完成结论所必需的内容。"
        )
    return (
        f"{instruction}\n\n原任务：\n{recovery.original_prompt}\n\n"
        f"此前已获得的工具记录：\n{recovery.tool_transcript}"
    )


async def _handle_shell_approvals(
    ctx: Any, requests: DeferredToolRequests
) -> Any:
    """Suspend deferred Shell calls until the active UI makes a choice."""
    approvals: dict[str, bool | ToolDenied] = {}
    for call in requests.approvals:
        # Providers may supply tool arguments either as a mapping or as a JSON
        # string.  Use Pydantic AI's normalizer so the command shown to the
        # user is always the command that will be executed.
        args = call.args_as_dict()
        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            approvals[call.tool_call_id] = ToolDenied(
                "Shell 命令缺失或格式无效，已拒绝执行"
            )
            continue
        request = ctx.deps.shell_approvals.create_request(
            command=command,
            working_directory=str(ctx.deps.project_path),
            is_background=call.tool_name == "start_command",
        )
        if await ctx.deps.shell_approvals.wait_for_decision(request.approval_id):
            approvals[call.tool_call_id] = True
        else:
            approvals[call.tool_call_id] = ToolDenied("用户取消了 Shell 命令执行")
    return requests.build_results(approvals=approvals)


def _strip_legacy_system_prompts(
    messages: list[ModelMessage],
) -> tuple[list[ModelMessage], bool]:
    """Remove static prompts persisted before AZ switched to instructions.

    AZ historically had one static ``system_prompt``. Its content is now
    supplied by the current agent as ``instructions``, so retaining those old
    parts would defeat the new history semantics and waste context tokens.
    """
    migrated_messages: list[ModelMessage] = []
    changed = False

    for message in messages:
        if not isinstance(message, ModelRequest):
            migrated_messages.append(message)
            continue

        parts = [
            part for part in message.parts if not isinstance(part, SystemPromptPart)
        ]
        if len(parts) == len(message.parts):
            migrated_messages.append(message)
            continue

        changed = True
        if parts:
            migrated_messages.append(replace(message, parts=parts))

    return migrated_messages, changed
