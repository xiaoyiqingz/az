"""首次启动或配置不完整时的交互式引导。"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import questionary

from config.settings import MODEL_PROVIDERS
from onboarding.env_file import env_file_path, read_env_file, write_env_values
from onboarding.fields import (
    ENV_FIELDS,
    PROVIDER_TITLES,
    EnvField,
    missing_fields,
    missing_provider_fields,
)


def ensure_env_configured(az_home: Path, *, reconfigure: bool = False) -> None:
    """确保 ``az_home/.env`` 配置完整；缺项时进入引导并写回文件。

    Args:
        az_home: 已解析的 AZ Home 目录。
        reconfigure: 为 True 时按顺序重新询问全部适用项，现有值作为默认值。
    """
    env_path = env_file_path(az_home)
    current = read_env_file(env_path)
    missing = missing_fields(current)
    if not reconfigure and not missing:
        return

    if not _is_interactive():
        keys = ", ".join(field.key for field in missing)
        raise SystemExit(
            f"{env_path} 配置不完整，缺少：{keys}\n"
            "请在终端中运行 `uv run main.py --setup` 完成配置。"
        )

    _print_intro(env_path, current, missing, reconfigure)
    try:
        updates = _ask(current, reconfigure=reconfigure)
    except KeyboardInterrupt:
        raise SystemExit("\n已取消配置，.env 未做任何修改。") from None

    write_env_values(az_home, updates)
    questionary.print(f"✔ 配置已保存到 {env_path}\n", style="bold fg:ansigreen")


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _print_intro(
    env_path: Path,
    current: dict[str, str],
    missing: list[EnvField],
    reconfigure: bool,
) -> None:
    questionary.print("AZ 配置向导", style="bold")
    if reconfigure:
        message = f"将重新配置 {env_path}，直接回车保留当前值。"
    elif not current:
        message = f"未找到 {env_path}，开始初始化配置。"
    else:
        message = f"{env_path} 缺少以下配置：{', '.join(f.key for f in missing)}"
    questionary.print(message + "\n", style="fg:ansiyellow")


def _ask(current: dict[str, str], *, reconfigure: bool) -> dict[str, str]:
    """按字段顺序提问；前面的回答会影响后面哪些字段适用。"""
    values = dict(current)
    updates: dict[str, str] = {}
    for field in ENV_FIELDS:
        if not field.when(values):
            continue
        if not reconfigure and not field.is_missing(values):
            continue
        answer = _prompt(field, values.get(field.key))
        values[field.key] = answer
        updates[field.key] = answer
    return updates


async def choose_provider(az_home: Path, current: str) -> str:
    """列出全部模型及其配置状态，返回用户选择的 provider。"""
    values = read_env_file(env_file_path(az_home))
    choices = []
    for provider in MODEL_PROVIDERS:
        status = "当前" if provider == current else (
            "已配置" if not missing_provider_fields(values, provider) else "未配置"
        )
        choices.append(questionary.Choice(f"{PROVIDER_TITLES[provider]}（{status}）", value=provider))
    return await questionary.select("切换到哪个模型", choices=choices, default=current).unsafe_ask_async()


async def ensure_provider_configured(az_home: Path, provider: str) -> None:
    """补全 provider 缺少的配置，并把它写为 ``AZ_MODEL_PROVIDER``。

    已配置完整的 provider 不会提问，只更新 ``AZ_MODEL_PROVIDER``。
    用户中途取消时抛出 ``KeyboardInterrupt``，此时 .env 不做任何修改。
    """
    current = read_env_file(env_file_path(az_home))
    missing = missing_provider_fields(current, provider)
    if missing:
        questionary.print(
            f"{PROVIDER_TITLES[provider]} 尚未配置，请补充：{', '.join(f.key for f in missing)}",
            style="fg:ansiyellow",
        )

    updates: dict[str, str] = {}
    for field in missing:
        updates[field.key] = await _prompt_async(field, current.get(field.key))
    if current.get("AZ_MODEL_PROVIDER") != provider:
        updates["AZ_MODEL_PROVIDER"] = provider
    if updates:
        write_env_values(az_home, updates)


def _prompt(field: EnvField, existing: str | None) -> str:
    question, convert = _question(field, existing)
    return convert(question.unsafe_ask())


async def _prompt_async(field: EnvField, existing: str | None) -> str:
    # CLI 运行在 asyncio 事件循环中，必须使用异步提问。
    question, convert = _question(field, existing)
    return convert(await question.unsafe_ask_async())


def _question(
    field: EnvField, existing: str | None
) -> tuple[questionary.Question, Callable[[Any], str]]:
    """构建字段对应的提问，以及把回答转换为 .env 取值的函数。"""
    valid_existing = existing if existing is not None and field.validate(existing) is None else None
    default = valid_existing if valid_existing is not None else field.default

    if field.kind == "select":
        question = questionary.select(
            field.label,
            choices=[questionary.Choice(c.title, value=c.value) for c in field.choices],
            default=default,
        )
        return question, str

    if field.kind == "confirm":
        question = questionary.confirm(field.label, default=default == "true")
        return question, lambda confirmed: "true" if confirmed else "false"

    if field.kind == "secret":
        # 密钥不回显，也不能作为默认值展示；已有值时允许直接回车保留。
        message = f"{field.label}（直接回车保留现有值）" if valid_existing else field.label
        question = questionary.password(
            message,
            validate=lambda value: (bool(valid_existing) and not value) or _validator(field)(value),
        )
        return question, lambda answer: valid_existing if valid_existing and not answer else answer.strip()

    question = questionary.text(field.label, default=default, validate=_validator(field))
    return question, lambda answer: answer.strip()


def _validator(field: EnvField):
    def validate(value: str) -> bool | str:
        return field.validate(value) or True

    return validate
