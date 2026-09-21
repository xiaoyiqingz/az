"""ASGI server entry point for AZ's local Web UI."""

from __future__ import annotations

import uvicorn

from config.settings import Settings

from .app import create_app


def run_web(
    settings: Settings,
    host: str = "127.0.0.1",
    port: int = 8000,
    default_project_path: str | None = None,
) -> None:
    """Start the local AZ Web UI and its same-origin API."""
    app = create_app(settings, default_project_path=default_project_path)
    uvicorn.run(app, host=host, port=port)
