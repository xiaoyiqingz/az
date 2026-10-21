"""首次启动或配置不完整时的交互式引导。"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config.settings import MODEL_PROVIDERS
from onboarding.env_file import env_file_path, read_env_file, write_env_values
from onboarding.fields import (
    ENV_FIELDS,
    PROVIDER_TITLES,
    SECTIONS,
    EnvField,
    missing_fields,
    missing_provider_fields,
)

_ACCENT = "#5f87ff"
_console = Console(highlight=False)
_STYLE = questionary.Style(
    [
        ("qmark", f"fg:{_ACCENT} bold"),
        ("question", "bold"),
        ("answer", "fg:#00af87 bold"),
        ("pointer", f"fg:{_ACCENT} bold"),
        ("highlighted", f"fg:{_ACCENT} bold"),
        ("selected", "fg:#00af87"),
        ("instruction", "fg:#808080"),
        ("text", ""),
    ]
)
_QMARK = "◆"


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
            f"请在终端中运行 `{_setup_command()}` 完成配置。"
        )

    _print_intro(env_path, current, missing, reconfigure)
    try:
        updates = _ask(current, missing, reconfigure=reconfigure)
    except KeyboardInterrupt:
        _console.print("\n[yellow]已取消配置，.env 未做任何修改。[/]")
        raise SystemExit(1) from None

    write_env_values(az_home, updates)
    _print_summary({**current, **updates}, updates)
    _console.print(f"[bold green]✔ 配置已保存到[/] [cyan]{env_path}[/]\n")


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _setup_command() -> str:
    """打包产物没有源码和 uv，提示直接运行可执行文件本身。"""
    if getattr(sys, "frozen", False):
        return f"{Path(sys.executable).name} --setup"
    return "uv run main.py --setup"


def _print_intro(
    env_path: Path,
    current: dict[str, str],
    missing: list[EnvField],
    reconfigure: bool,
) -> None:
    if reconfigure:
        message = "将逐项确认现有配置，直接回车保留当前值。"
    elif not current:
        message = "首次启动，回答几个问题即可完成配置。"
    else:
        message = f"配置不完整，还需补充 {len(missing)} 项：{', '.join(f.key for f in missing)}"
    body = Text.assemble(
        (message, "bold"),
        "\n",
        ("配置文件  ", "dim"),
        (str(env_path), "cyan"),
        "\n",
        ("↑↓ 选择 · 回车确认 · Ctrl-C 取消（不会修改文件）", "dim"),
    )
    _console.print()
    _console.print(
        Panel(
            body,
            title="[bold] AZ 配置向导 [/]",
            title_align="left",
            border_style=_ACCENT,
            padding=(1, 2),
            expand=False,
        )
    )


def _ask(current: dict[str, str], missing: list[EnvField], *, reconfigure: bool) -> dict[str, str]:
    """按分组和字段顺序提问；前面的回答会影响后面哪些字段适用。"""
    # 分组内的回答只会增减本组字段，因此步骤总数可以提前确定。
    sections = SECTIONS if reconfigure else [s for s in SECTIONS if any(f.section == s for f in missing)]
    values = dict(current)
    updates: dict[str, str] = {}
    for step, section in enumerate(sections, start=1):
        _print_section(step, len(sections), section)
        for field in ENV_FIELDS:
            if field.section != section or not field.when(values):
                continue
            if not reconfigure and not field.is_missing(values):
                continue
            answer = _prompt(field, values.get(field.key))
            values[field.key] = answer
            updates[field.key] = answer
    return updates


def _print_section(step: int, total: int, section: str) -> None:
    _console.print()
    _console.rule(f"[bold {_ACCENT}]步骤 {step}/{total}[/]  [bold]{section}[/]", align="left", style="dim")


def _print_summary(values: dict[str, str], updates: dict[str, str]) -> None:
    table = Table(box=None, show_header=False, padding=(0, 2, 0, 0))
    table.add_column(style="dim", no_wrap=True)
    table.add_column(overflow="fold")
    table.add_column(justify="right", no_wrap=True)
    for field in ENV_FIELDS:
        if field.key not in values or not field.when(values):
            continue
        mark = "[green]● 已更新[/]" if field.key in updates else ""
        table.add_row(field.key, _display_value(field, values[field.key]), mark)
    _console.print()
    _console.print(
        Panel(
            table,
            title="[bold] 配置汇总 [/]",
            title_align="left",
            border_style="green",
            padding=(1, 2),
            expand=False,
        )
    )


def _display_value(field: EnvField, value: str) -> str:
    if field.kind == "secret":
        return _mask(value)
    titles = {choice.value: choice.title for choice in field.choices}
    return titles.get(value, value) or "（空）"


def _mask(secret: str) -> str:
    if len(secret) <= 8:
        return "•" * 8
    return f"{secret[:3]}{'•' * 6}{secret[-4:]}"


async def choose_provider(az_home: Path, current: str) -> str:
    """列出全部模型及其配置状态，返回用户选择的 provider。"""
    values = read_env_file(env_file_path(az_home))
    choices = []
    for provider in MODEL_PROVIDERS:
        status = "当前" if provider == current else (
            "已配置" if not missing_provider_fields(values, provider) else "未配置"
        )
        choices.append(questionary.Choice(f"{PROVIDER_TITLES[provider]}（{status}）", value=provider))
    return await questionary.select(
        "切换到哪个模型",
        choices=choices,
        default=current,
        qmark=_QMARK,
        pointer="❯",
        style=_STYLE,
        instruction="（↑↓ 选择，回车确认）",
    ).unsafe_ask_async()


async def ensure_provider_configured(az_home: Path, provider: str) -> None:
    """补全 provider 缺少的配置，并把它写为 ``AZ_MODEL_PROVIDER``。

    已配置完整的 provider 不会提问，只更新 ``AZ_MODEL_PROVIDER``。
    用户中途取消时抛出 ``KeyboardInterrupt``，此时 .env 不做任何修改。
    """
    current = read_env_file(env_file_path(az_home))
    missing = missing_provider_fields(current, provider)
    if missing:
        _console.print(
            f"\n[yellow]●[/] [bold]{PROVIDER_TITLES[provider]}[/] 尚未配置，"
            f"还需补充 {len(missing)} 项（Ctrl-C 取消）"
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
    if field.hint:
        _console.print(f"  [dim]{field.hint}[/]")
    common: dict[str, Any] = {"qmark": _QMARK, "style": _STYLE}
    valid_existing = existing if existing is not None and field.validate(existing) is None else None
    default = valid_existing if valid_existing is not None else field.default

    if field.kind == "select":
        question = questionary.select(
            field.label,
            choices=[
                questionary.Choice(c.title, value=c.value, description=c.description or None)
                for c in field.choices
            ],
            default=default,
            pointer="❯",
            instruction=" ",
            **common,
        )
        return question, str

    if field.kind == "confirm":
        question = questionary.confirm(field.label, default=default == "true", **common)
        return question, lambda confirmed: "true" if confirmed else "false"

    if field.kind == "secret":
        # 密钥不回显，也不能作为默认值展示；已有值时允许直接回车保留。
        message = f"{field.label}（直接回车保留现有值）" if valid_existing else field.label
        question = questionary.password(
            message,
            validate=lambda value: (bool(valid_existing) and not value) or _validator(field)(value),
            **common,
        )
        return question, lambda answer: valid_existing if valid_existing and not answer else answer.strip()

    question = questionary.text(field.label, default=default, validate=_validator(field), **common)
    return question, lambda answer: answer.strip()


def _validator(field: EnvField):
    def validate(value: str) -> bool | str:
        return field.validate(value) or True

    return validate
