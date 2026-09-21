from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from httpx import AsyncClient

from config.settings import Settings
from core.shell_approval import ShellApprovalManager

from .session_store import SessionStore


@dataclass
class Deps:
    client: AsyncClient
    session_id: str
    conversation_id: str
    az_home: Path
    project_path: Path
    settings: Settings
    session_store: SessionStore
    shell_approvals: ShellApprovalManager
