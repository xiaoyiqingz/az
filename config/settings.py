from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class HostedModelSettings:
    model_name: str
    api_key: str | None
    base_url: str | None = None


@dataclass(frozen=True)
class OllamaModelSettings:
    base_url: str
    model_ds: str
    model_qwen: str


@dataclass(frozen=True)
class ModelSettings:
    deepseek: HostedModelSettings
    qwen: HostedModelSettings
    mimo: HostedModelSettings
    ollama: OllamaModelSettings


@dataclass(frozen=True)
class ObservabilitySettings:
    backend: str | None
    langfuse_base_url: str
    langfuse_public_key: str | None
    langfuse_secret_key: str | None


@dataclass(frozen=True)
class Settings:
    models: ModelSettings
    observability: ObservabilitySettings
    tavily_api_key: str | None
    az_home: Path
    mcp_config_path: Path
    skills_dir: Path
    context_target_tokens: int
    context_keep_messages: int
    context_keep_tool_pairs: int
    context_max_part_tokens: int
    planning_enabled: bool
    planning_cache_ttl: Literal["5m", "1h"]
    request_limit: int
    tool_calls_limit: int


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build project settings from process environment."""
    values = env or os.environ
    base_path = Path(__file__).resolve().parent.parent

    az_home = _resolve_path(values.get("AZ_HOME", "~/.az"), base_path)

    return Settings(
        models=ModelSettings(
            deepseek=HostedModelSettings(
                model_name=values.get("DEEPSEEK_MODEL_NAME", "deepseek-chat"),
                api_key=values.get("DEEPSEEK_API_KEY"),
            ),
            qwen=HostedModelSettings(
                model_name=values.get("QWEN_MODEL_NAME", "qwen3-coder-plus"),
                api_key=values.get("QWEN_API_KEY"),
                base_url=values.get("QWEN_BASE_URL"),
            ),
            mimo=HostedModelSettings(
                model_name=values.get("MIMO_MODEL_NAME", "mimo-v2.5-pro"),
                api_key=values.get("MIMO_API_KEY"),
                base_url=values.get(
                    "MIMO_BASE_URL",
                    "https://api.xiaomimimo.com/v1",
                ),
            ),
            ollama=OllamaModelSettings(
                base_url=values.get(
                    "OLLAMA_BASE_URL", "http://localhost:11434/v1"
                ),
                model_ds=values.get("OLLAMA_MODEL_DS", "deepseek-r1:7b"),
                model_qwen=values.get("OLLAMA_MODEL_QWEN", "qwen3:8b"),
            ),
        ),
        observability=ObservabilitySettings(
                backend=values.get("OBS_BACKEND"),
            langfuse_base_url=values.get(
                "LANGFUSE_BASE_URL", "https://cloud.langfuse.com"
            ),
            langfuse_public_key=values.get("LANGFUSE_PUBLIC_KEY"),
            langfuse_secret_key=values.get("LANGFUSE_SECRET_KEY"),
        ),
        tavily_api_key=values.get("TAVILY_API_KEY"),
        az_home=az_home,
        mcp_config_path=_resolve_path(values["MCP_CONFIG_PATH"], base_path)
        if values.get("MCP_CONFIG_PATH")
        else az_home / "mcp.json",
        skills_dir=_resolve_path(values["SKILLS_DIR"], base_path)
        if values.get("SKILLS_DIR")
        else az_home / "skills",
        context_target_tokens=int(values.get("CONTEXT_TARGET_TOKENS", "48000")),
        context_keep_messages=int(values.get("CONTEXT_KEEP_MESSAGES", "20")),
        context_keep_tool_pairs=int(values.get("CONTEXT_KEEP_TOOL_PAIRS", "4")),
        context_max_part_tokens=int(
            values.get("CONTEXT_MAX_PART_TOKENS", "30000")
        ),
        planning_enabled=values.get("USE_PLANNING_MODE", "true").lower()
        not in {"0", "false", "no", "off"},
        planning_cache_ttl=_load_planning_cache_ttl(values),
        request_limit=_load_positive_int(values, "REQUEST_LIMIT", 50),
        tool_calls_limit=_load_positive_int(values, "TOOL_CALLS_LIMIT", 40),
    )


def _resolve_path(raw_path: str, base_path: Path) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (base_path / candidate).resolve()


def _load_planning_cache_ttl(values: dict[str, str]) -> Literal["5m", "1h"]:
    value = values.get("PLANNING_CACHE_TTL", "5m")
    if value not in {"5m", "1h"}:
        raise ValueError("PLANNING_CACHE_TTL 必须为 '5m' 或 '1h'")
    return value  # type: ignore[return-value]


def _load_positive_int(values: dict[str, str], key: str, default: int) -> int:
    value = int(values.get(key, str(default)))
    if value < 1:
        raise ValueError(f"{key} 必须为正整数")
    return value
