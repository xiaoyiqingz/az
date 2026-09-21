"""HTTP application shared by the Web UI and future public API routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from markdown_it import MarkdownIt
from pydantic import BaseModel, ValidationError
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from pydantic_ai.run import AgentRunResultEvent
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from config.settings import Settings
from core.context.session_id import generate_session_id
from core.context.session_store import SessionStore
from core.server import (
    UsageLimitReached,
    build_usage_limit_prompt,
    open_agent_session,
    stream_session_turn,
)
from core.shell_approval import ShellApprovalRequest, shell_approval_registry
from tools.register import get_tool_status_labels


WEB_STATIC_DIR = Path(__file__).resolve().parents[2] / "ui" / "web" / "static"
MARKDOWN_RENDERER = MarkdownIt(
    "commonmark",
    {"html": False, "breaks": True},
).enable("table")


class MessageRequest(BaseModel):
    prompt: str | None = None
    usage_limit_action: Literal["continue", "summarize"] | None = None


class ShellApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]


def create_app(
    settings: Settings,
    default_project_path: str | None = None,
) -> Starlette:
    """Create the same-origin Web UI and API application.

    ``default_project_path`` is a server startup option, never a browser input.
    Existing sessions continue to use their stored project binding.
    """
    tool_status_labels = get_tool_status_labels()

    async def index(_: Request) -> Response:
        return FileResponse(WEB_STATIC_DIR / "index.html")

    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok"})

    async def create_session(_: Request) -> Response:
        return JSONResponse({"session_id": generate_session_id()}, status_code=201)

    async def list_sessions(_: Request) -> Response:
        return JSONResponse({"sessions": _list_sessions(settings.az_home)})

    async def history(request: Request) -> Response:
        session_id = _validate_session_id(request.path_params["session_id"])
        if session_id is None:
            return JSONResponse({"detail": "session_id 必须是 UUID"}, status_code=422)
        store = SessionStore(settings.az_home, session_id)
        try:
            history_messages = store.load_message_history()
        except Exception:
            return JSONResponse({"detail": "会话历史无法读取"}, status_code=500)
        return JSONResponse({"messages": _visible_history(history_messages)})

    async def message(request: Request) -> Response:
        session_id = _validate_session_id(request.path_params["session_id"])
        if session_id is None:
            return JSONResponse({"detail": "session_id 必须是 UUID"}, status_code=422)

        try:
            payload = MessageRequest.model_validate(await request.json())
        except (ValidationError, json.JSONDecodeError):
            return JSONResponse({"detail": "请求体必须包含 prompt 字符串"}, status_code=422)

        if payload.usage_limit_action is not None:
            store = SessionStore(settings.az_home, session_id)
            recovery = store.load_usage_limit_recovery()
            if recovery is None:
                return JSONResponse({"detail": "没有可恢复的受限任务"}, status_code=409)
            prompt = build_usage_limit_prompt(recovery, payload.usage_limit_action)
        else:
            prompt = (payload.prompt or "").strip()
            if not prompt:
                return JSONResponse({"detail": "prompt 不能为空"}, status_code=422)

        async def event_stream():
            markdown_parts: list[str] = []
            try:
                async with open_agent_session(
                    settings=settings,
                    session_id=session_id,
                    requested_project_path=default_project_path,
                ) as session:
                    async for event in stream_session_turn(session, prompt):
                        payload = _event_payload(event, tool_status_labels)
                        if payload is not None and payload["type"] == "text_delta":
                            markdown_parts.append(payload["delta"])
                        if payload is not None and payload["type"] == "done":
                            payload["html"] = _render_markdown("".join(markdown_parts))
                        if payload is not None:
                            yield _encode_sse(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                yield _encode_sse({"type": "error", "message": str(exc)})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def resolve_shell_approval(request: Request) -> Response:
        session_id = _validate_session_id(request.path_params["session_id"])
        approval_id = request.path_params["approval_id"]
        if session_id is None:
            return JSONResponse({"detail": "session_id 必须是 UUID"}, status_code=422)
        try:
            payload = ShellApprovalDecisionRequest.model_validate(await request.json())
        except (ValidationError, json.JSONDecodeError):
            return JSONResponse({"detail": "decision 必须为 approve 或 reject"}, status_code=422)

        resolved = shell_approval_registry.resolve(
            session_id,
            approval_id,
            payload.decision == "approve",
        )
        if not resolved:
            return JSONResponse({"detail": "审批不存在、已过期或已处理"}, status_code=404)
        return JSONResponse({"status": "approved" if payload.decision == "approve" else "rejected"})

    return Starlette(
        routes=[
            Route("/", index),
            Mount("/static", app=StaticFiles(directory=WEB_STATIC_DIR), name="static"),
            Route("/api/v1/health", health),
            Route("/api/v1/sessions", create_session, methods=["POST"]),
            Route("/api/v1/sessions", list_sessions, methods=["GET"]),
            Route(
                "/api/v1/sessions/{session_id}/history",
                history,
                methods=["GET"],
            ),
            Route(
                "/api/v1/sessions/{session_id}/messages",
                message,
                methods=["POST"],
            ),
            Route(
                "/api/v1/sessions/{session_id}/shell-approvals/{approval_id}",
                resolve_shell_approval,
                methods=["POST"],
            ),
        ]
    )


def _validate_session_id(value: str) -> str | None:
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _event_payload(event: Any, tool_status_labels: dict[str, str]) -> dict[str, Any] | None:
    if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
        if event.part.content:
            return {"type": "text_delta", "delta": event.part.content}
    elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        if event.delta.content_delta:
            return {"type": "text_delta", "delta": event.delta.content_delta}
    elif isinstance(event, FunctionToolCallEvent):
        tool_name = event.part.tool_name
        return {
            "type": "tool_status",
            "message": tool_status_labels.get(tool_name, f"正在调用工具：{tool_name}"),
        }
    elif isinstance(event, FunctionToolResultEvent):
        return {"type": "tool_complete", "message": "工具调用已完成"}
    elif isinstance(event, ShellApprovalRequest):
        return {
            "type": "shell_approval_requested",
            "approval_id": event.approval_id,
            "command": event.command,
            "working_directory": event.working_directory,
            "is_background": event.is_background,
        }
    elif isinstance(event, UsageLimitReached):
        return {
            "type": "usage_limit_reached",
            "message": event.message,
            "request_limit": event.request_limit,
            "tool_calls_limit": event.tool_calls_limit,
        }
    elif isinstance(event, AgentRunResultEvent):
        return {"type": "done", "message": "回答已完成"}
    return None


def _encode_sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _list_sessions(az_home: Path) -> list[dict[str, str | int | None]]:
    sessions_dir = az_home / "sessions"
    if not sessions_dir.exists():
        return []

    sessions: list[dict[str, str | int | None]] = []
    for directory in sessions_dir.iterdir():
        if not directory.is_dir():
            continue
        session_id = _validate_session_id(directory.name)
        if session_id is None:
            continue
        store = SessionStore(az_home, session_id)
        try:
            meta = store.load_meta()
            if meta is None:
                continue
            history = store.load_message_history()
            message_count = len(history)
        except Exception:
            continue
        sessions.append(
            {
                "session_id": session_id,
                "project_path": meta.project_path,
                "updated_at": meta.updated_at.isoformat(),
                "message_count": message_count,
                "first_prompt": _first_user_prompt(history),
            }
        )
    return sorted(sessions, key=lambda item: str(item["updated_at"]), reverse=True)


def _visible_history(messages: list[Any]) -> list[dict[str, str]]:
    visible: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    visible.append({"role": "user", "content": part.content})
        elif isinstance(message, ModelResponse):
            content = "".join(
                part.content
                for part in message.parts
                if isinstance(part, TextPart) and isinstance(part.content, str)
            )
            if content:
                visible.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "html": _render_markdown(content),
                    }
                )
    return visible


def _first_user_prompt(messages: list[Any]) -> str | None:
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                return part.content
    return None


def _render_markdown(source: str) -> str:
    """Render model Markdown while refusing model-provided raw HTML."""
    return MARKDOWN_RENDERER.render(source)
