"""首次启动或配置不完整时的交互式引导。"""

from __future__ import annotations

import sys
from pathlib import Path

import questionary

from onboarding.env_file import env_file_path, read_env_file, write_env_values
from onboarding.fields import ENV_FIELDS, EnvField, missing_fields


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


def _prompt(field: EnvField, existing: str | None) -> str:
    valid_existing = existing if existing is not None and field.validate(existing) is None else None
    default = valid_existing if valid_existing is not None else field.default

    if field.kind == "select":
        return questionary.select(
            field.label,
            choices=[questionary.Choice(c.title, value=c.value) for c in field.choices],
            default=default,
        ).unsafe_ask()

    if field.kind == "confirm":
        confirmed = questionary.confirm(field.label, default=default == "true").unsafe_ask()
        return "true" if confirmed else "false"

    if field.kind == "secret":
        # 密钥不回显，也不能作为默认值展示；已有值时允许直接回车保留。
        message = f"{field.label}（直接回车保留现有值）" if valid_existing else field.label
        answer = questionary.password(
            message,
            validate=lambda value: (bool(valid_existing) and not value) or _validator(field)(value),
        ).unsafe_ask()
        if valid_existing and not answer:
            return valid_existing
        return answer.strip()

    return questionary.text(field.label, default=default, validate=_validator(field)).unsafe_ask().strip()


def _validator(field: EnvField):
    def validate(value: str) -> bool | str:
        return field.validate(value) or True

    return validate
