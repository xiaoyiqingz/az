from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.messages import ModelMessage

from .models import ConversationSummary, SessionMeta, UsageLimitRecovery


class SessionStore:
    """Persist session-scoped context artifacts on disk."""

    def __init__(self, az_home: Path, session_id: str):
        self.az_home = az_home
        self.session_id = session_id
        self._session_dir = self.az_home / "sessions" / session_id
        self.message_history_path = self._session_dir / "az_message_history.json"
        self.meta_path = self._session_dir / "session_meta.json"
        self.summary_path = self._session_dir / "conversation_summary.json"
        self.usage_limit_recovery_path = self._session_dir / "usage_limit_recovery.json"

    @property
    def session_dir(self) -> Path:
        self._session_dir.mkdir(parents=True, exist_ok=True)
        return self._session_dir

    def load_message_history(self) -> list[ModelMessage]:
        if not self.message_history_path.exists():
            return []
        return ModelMessagesTypeAdapter.validate_json(
            self.message_history_path.read_bytes()
        )

    def save_message_history(self, messages: list[ModelMessage]) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.message_history_path.write_bytes(
            ModelMessagesTypeAdapter.dump_json(list(messages), indent=2)
        )

    def load_meta(self) -> SessionMeta | None:
        if not self.meta_path.exists():
            return None
        return SessionMeta.model_validate_json(self.meta_path.read_text("utf-8"))

    def save_meta(self, meta: SessionMeta) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(
            meta.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_summary(self) -> ConversationSummary | None:
        if not self.summary_path.exists():
            return None
        return ConversationSummary.model_validate_json(
            self.summary_path.read_text("utf-8")
        )

    def save_summary(self, summary: ConversationSummary) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.summary_path.write_text(
            summary.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_summary_metadata(self) -> dict[str, Any] | None:
        summary = self.load_summary()
        if summary is None:
            return None
        return json.loads(summary.model_dump_json())

    def load_usage_limit_recovery(self) -> UsageLimitRecovery | None:
        if not self.usage_limit_recovery_path.exists():
            return None
        return UsageLimitRecovery.model_validate_json(
            self.usage_limit_recovery_path.read_text("utf-8")
        )

    def save_usage_limit_recovery(self, recovery: UsageLimitRecovery) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.usage_limit_recovery_path.write_text(
            recovery.model_dump_json(indent=2), encoding="utf-8"
        )

    def clear_usage_limit_recovery(self) -> None:
        if self.usage_limit_recovery_path.exists():
            self.usage_limit_recovery_path.unlink()
