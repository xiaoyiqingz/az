"""CLI 的 /model 命令：切换模型，未配置的模型先补全配置。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from config.settings import MODEL_PROVIDERS, Settings, load_settings
from core.server import AgentSession
from onboarding import PROVIDER_TITLES, choose_provider, ensure_provider_configured


def is_model_command(user_input: str) -> bool:
    parts = user_input.strip().split()
    return bool(parts) and parts[0].lower() == "/model"


async def handle_model_command(session: AgentSession, user_input: str) -> str:
    """处理 ``/model`` 或 ``/model <provider>``，返回要展示给用户的结果。"""
    settings = session.deps.settings
    args = user_input.strip().split()[1:]
    try:
        if args:
            provider = args[0].lower()
            if provider not in MODEL_PROVIDERS:
                return f"未知模型：{args[0]}。可选：{', '.join(MODEL_PROVIDERS)}"
        else:
            provider = await choose_provider(settings.az_home, settings.models.provider)
        await ensure_provider_configured(settings.az_home, provider)
    except KeyboardInterrupt:
        return "已取消切换，模型与 .env 均未改变。"

    model = session.switch_model(_reload_settings(settings.az_home))
    return f"已切换到 {PROVIDER_TITLES[provider]}：{model.model_name}（已设为默认模型）"


def describe_model(session: AgentSession) -> str:
    provider = session.deps.settings.models.provider
    return f"{PROVIDER_TITLES[provider]}：{session.active_model.model_name}"


def _reload_settings(az_home: Path) -> Settings:
    # 与启动时一致：.env 优先于已导出的环境变量，AZ Home 保持本次启动解析的目录。
    load_dotenv(az_home / ".env", override=True)
    os.environ["AZ_HOME"] = str(az_home)
    return load_settings()
