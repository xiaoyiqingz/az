from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai.messages import ModelMessage

from core.context.project_path import resolve_session_project_path

from .models import SessionMeta, utc_now
from .session_store import SessionStore


@dataclass(frozen=True)
class SessionRuntime:
    session_store: SessionStore
    all_messages: list[ModelMessage]
    conversation_id: str
    project_path: Path
    ignored_cli_project_path: bool


def initialize_session_runtime(
    az_home: Path,
    session_id: str,
    requested_project_path: str | None = None,
    cwd: Path | None = None,
) -> SessionRuntime:
    session_store = SessionStore(az_home, session_id=session_id)
    all_messages = session_store.load_message_history()
    conversation_id = session_id
    session_meta = session_store.load_meta()
    project_path, ignored_cli_project_path = resolve_session_project_path(
        session_meta=session_meta,
        requested_project_path=requested_project_path,
        cwd=cwd,
    )
    now = utc_now()

    if session_meta is None:
        session_store.save_meta(
            SessionMeta(
                session_id=session_id,
                conversation_id=conversation_id,
                project_path=str(project_path),
                created_at=now,
                updated_at=now,
                resumed=bool(all_messages),
            )
        )
    else:
        session_store.save_meta(
            session_meta.model_copy(
                update={
                    "conversation_id": conversation_id,
                    "project_path": str(project_path),
                    "updated_at": now,
                    "resumed": session_meta.resumed or bool(all_messages),
                }
            )
        )

    return SessionRuntime(
        session_store=session_store,
        all_messages=all_messages,
        conversation_id=conversation_id,
        project_path=project_path,
        ignored_cli_project_path=ignored_cli_project_path,
    )
