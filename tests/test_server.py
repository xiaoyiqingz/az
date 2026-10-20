import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock

from pydantic_ai import DeferredToolRequests, ToolDenied
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.run import AgentRunResultEvent

from config.settings import load_settings
from core.server import AgentSession, _handle_shell_approvals, stream_session_turn
from core.shell_approval import ShellApprovalManager


class _StreamContext:
    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        async def stream():
            for event in self.events:
                yield event

        return stream()

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


class TestServer(unittest.TestCase):
    def test_stream_session_turn_persists_history_without_cli_dependencies(self):
        messages = [SimpleNamespace(role="assistant")]
        run_result = Mock()
        run_result.all_messages.return_value = messages
        agent = Mock()
        agent.run_stream_events.return_value = _StreamContext(
            [AgentRunResultEvent(result=run_result)]
        )
        session_store = Mock()
        runtime = SimpleNamespace(
            project_path=Path("/project"),
            conversation_id="conversation-1",
            session_store=session_store,
            ignored_cli_project_path=False,
        )
        session = AgentSession(
            runtime=runtime,
            agent=agent,
            deps=SimpleNamespace(
                session_id="session-1",
                settings=load_settings({}),
                shell_approvals=ShellApprovalManager("session-1"),
            ),
            all_messages=[],
        )

        async def consume():
            return [event async for event in stream_session_turn(session, "hello")]

        events = asyncio.run(consume())

        self.assertEqual(len(events), 1)
        self.assertEqual(session.all_messages, messages)
        session_store.save_message_history.assert_called_once_with(messages)
        agent.run_stream_events.assert_called_once_with(
            "hello",
            model=None,
            deps=session.deps,
            message_history=[],
            conversation_id="conversation-1",
            metadata={"session_id": "session-1", "project_path": "/project"},
            usage_limits=ANY,
        )

    def test_switch_model_is_used_by_later_turns(self):
        run_result = Mock()
        run_result.all_messages.return_value = []
        agent = Mock()
        agent.run_stream_events.return_value = _StreamContext(
            [AgentRunResultEvent(result=run_result)]
        )
        session = AgentSession(
            runtime=SimpleNamespace(
                project_path=Path("/project"),
                conversation_id="conversation-1",
                session_store=Mock(),
            ),
            agent=agent,
            deps=SimpleNamespace(
                session_id="session-1",
                settings=load_settings({}),
                shell_approvals=ShellApprovalManager("session-1"),
            ),
            all_messages=[],
        )
        settings = load_settings(
            {"AZ_MODEL_PROVIDER": "ollama", "OLLAMA_MODEL_NAME": "qwen3:14b"}
        )

        model = session.switch_model(settings)

        async def consume():
            return [event async for event in stream_session_turn(session, "hello")]

        asyncio.run(consume())
        self.assertIs(session.deps.settings, settings)
        self.assertIs(session.active_model, model)
        self.assertEqual(model.model_name, "qwen3:14b")
        self.assertIs(agent.run_stream_events.call_args.kwargs["model"], model)


class TestShellApprovalHandling(unittest.IsolatedAsyncioTestCase):
    async def test_json_string_arguments_show_the_actual_command(self):
        manager = ShellApprovalManager("session-1")
        ctx = SimpleNamespace(
            deps=SimpleNamespace(
                shell_approvals=manager,
                project_path=Path("/project"),
            )
        )
        requests = DeferredToolRequests(
            approvals=[
                ToolCallPart(
                    tool_name="run_command",
                    tool_call_id="call-1",
                    args='{"command":"printf hello"}',
                )
            ]
        )

        handler = asyncio.create_task(_handle_shell_approvals(ctx, requests))
        request = await manager.next_request()

        self.assertEqual(request.command, "printf hello")
        manager.resolve(request.approval_id, False)
        result = await handler
        self.assertIsInstance(result.approvals["call-1"], ToolDenied)

    async def test_missing_or_invalid_command_is_rejected_without_prompting(self):
        manager = ShellApprovalManager("session-1")
        ctx = SimpleNamespace(
            deps=SimpleNamespace(
                shell_approvals=manager,
                project_path=Path("/project"),
            )
        )
        requests = DeferredToolRequests(
            approvals=[
                ToolCallPart(
                    tool_name="run_command",
                    tool_call_id="call-1",
                    args='{"command": null}',
                )
            ]
        )

        result = await _handle_shell_approvals(ctx, requests)

        self.assertIsInstance(result.approvals["call-1"], ToolDenied)
        self.assertTrue(manager._requests.empty())


if __name__ == "__main__":
    unittest.main()
