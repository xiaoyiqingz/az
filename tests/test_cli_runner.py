import asyncio
import signal
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from commands.builtin_commands import CommandType
from core.shell_approval import ShellApprovalManager
from ui.cli import runner


class _InputHandler:
    def __init__(self, *_args, **_kwargs):
        self.inputs = iter(("explain this", "/exit"))
        self.save_history = MagicMock()
        self.cleanup = MagicMock()

    def initialize(self):
        pass

    async def read_input(self):
        return next(self.inputs)


class TestCliRunner(unittest.IsolatedAsyncioTestCase):
    async def test_ctrl_c_cancels_active_turn_and_returns_to_input(self):
        input_handler = _InputHandler()
        formatter = MagicMock()
        session = SimpleNamespace(
            session_id="session-1",
            project_path=Path("/workspace"),
            ignored_requested_project_path=False,
            all_messages=[],
            deps=SimpleNamespace(shell_approvals=ShellApprovalManager("session-1")),
            save_history=MagicMock(),
        )
        turn_started = asyncio.Event()
        registered_handlers = []

        @asynccontextmanager
        async def open_session(**_kwargs):
            yield session

        async def consume_until_cancelled(**_kwargs):
            turn_started.set()
            await asyncio.Event().wait()

        def builtin_command(value, **_kwargs):
            if value == "/exit":
                return True, "", CommandType.DIRECT
            return False, None, None

        def record_signal_handler(_signal_number, handler):
            registered_handlers.append(handler)

        def old_sigint_handler(_signum, _frame):
            raise KeyboardInterrupt

        settings = SimpleNamespace(az_home=Path("/tmp/az-tests"))
        with (
            patch.object(runner, "InputHandler", return_value=input_handler),
            patch.object(runner, "open_agent_session", open_session),
            patch.object(runner, "consume_stream_events", consume_until_cancelled),
            patch.object(runner, "create_formatter", return_value=formatter),
            patch.object(runner, "get_tool_status_labels", return_value={}),
            patch.object(runner, "process_builtin_command", side_effect=builtin_command),
            patch.object(runner.signal, "getsignal", return_value=old_sigint_handler),
            patch.object(runner.signal, "signal", side_effect=record_signal_handler),
        ):
            cli_task = asyncio.create_task(runner.run_cli(settings, "session-1"))
            await turn_started.wait()
            registered_handlers[0](signal.SIGINT, None)
            await cli_task

        formatter.reset.assert_called()
        input_handler.save_history.assert_called()
        session.save_history.assert_called_once()
        self.assertIs(registered_handlers[-1], old_sigint_handler)

    async def test_cancelled_shell_confirmation_rejects_request(self):
        manager = ShellApprovalManager("session-1")
        request = manager.create_request(
            command="make test", working_directory="/workspace", is_background=False
        )
        session = SimpleNamespace(deps=SimpleNamespace(shell_approvals=manager))
        confirmation_started = asyncio.Event()

        class BlockingInput:
            async def confirm_shell_command(self, *_args):
                confirmation_started.set()
                await asyncio.Event().wait()

        decision = asyncio.create_task(manager.wait_for_decision(request.approval_id))
        confirmation = asyncio.create_task(
            runner._confirm_shell_command(BlockingInput(), session, request)
        )
        await confirmation_started.wait()
        confirmation.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await confirmation
        self.assertFalse(await decision)
