"""引导配置的配置项定义与完整性判断。

字段按提问顺序排列；``when`` 依据已有取值（含本轮已回答的值）决定该项是否适用，
因此切换模型或可观测后端后，只会检查和询问与之对应的配置。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from config.settings import MODEL_PROVIDERS

FieldKind = Literal["text", "secret", "select", "confirm"]
Values = Mapping[str, str]


@dataclass(frozen=True)
class Choice:
    value: str
    title: str


@dataclass(frozen=True)
class EnvField:
    key: str
    label: str
    kind: FieldKind = "text"
    default: str = ""
    choices: tuple[Choice, ...] = ()
    # 为 True 时，值可以为空，但键仍须出现在 .env 中（表示用户已做过选择）。
    allow_empty: bool = False
    url: bool = False
    when: Callable[[Values], bool] = lambda _values: True

    def is_missing(self, values: Values) -> bool:
        if self.key not in values:
            return True
        return self.validate(values[self.key]) is not None

    def validate(self, value: str) -> str | None:
        """返回错误提示；值合法时返回 ``None``。"""
        value = value.strip()
        if not value:
            return None if self.allow_empty else f"{self.label}不能为空"
        if self.choices and value not in {choice.value for choice in self.choices}:
            return f"{self.label}必须为 {', '.join(c.value for c in self.choices)} 之一"
        if self.url and not value.startswith(("http://", "https://")):
            return f"{self.label}必须以 http:// 或 https:// 开头"
        return None


def _provider_is(provider: str) -> Callable[[Values], bool]:
    return lambda values: values.get("AZ_MODEL_PROVIDER") == provider


def _hosted_model_fields(
    provider: str,
    title: str,
    *,
    default_model: str,
    default_base_url: str | None,
) -> list[EnvField]:
    prefix = provider.upper()
    when = _provider_is(provider)
    fields: list[EnvField] = []
    if default_base_url is not None:
        fields.append(
            EnvField(
                f"{prefix}_BASE_URL",
                f"{title} 接口地址",
                default=default_base_url,
                url=True,
                when=when,
            )
        )
    fields += [
        EnvField(f"{prefix}_MODEL_NAME", f"{title} 模型名称", default=default_model, when=when),
        EnvField(f"{prefix}_API_KEY", f"{title} API Key", kind="secret", when=when),
    ]
    return fields


_PROVIDER_TITLES = {
    "deepseek": "DeepSeek",
    "qwen": "通义千问 Qwen",
    "mimo": "小米 MiMo",
    "ollama": "Ollama（本地）",
}

ENV_FIELDS: tuple[EnvField, ...] = (
    EnvField(
        "AZ_MODEL_PROVIDER",
        "使用的模型",
        kind="select",
        default="deepseek",
        choices=tuple(Choice(p, _PROVIDER_TITLES[p]) for p in MODEL_PROVIDERS),
    ),
    # DeepSeekProvider 自带固定接口地址，因此不询问 base url。
    *_hosted_model_fields(
        "deepseek", "DeepSeek", default_model="deepseek-chat", default_base_url=None
    ),
    *_hosted_model_fields(
        "qwen",
        "Qwen",
        default_model="qwen3-coder-plus",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    *_hosted_model_fields(
        "mimo",
        "MiMo",
        default_model="mimo-v2.5-pro",
        default_base_url="https://api.xiaomimimo.com/v1",
    ),
    EnvField(
        "OLLAMA_BASE_URL",
        "Ollama 接口地址",
        default="http://localhost:11434/v1",
        url=True,
        when=_provider_is("ollama"),
    ),
    EnvField(
        "OLLAMA_MODEL_NAME",
        "Ollama 模型名称",
        default="qwen3:8b",
        when=_provider_is("ollama"),
    ),
    EnvField(
        "OBS_BACKEND",
        "可观测性后端",
        kind="select",
        default="",
        allow_empty=True,
        choices=(
            Choice("", "关闭"),
            Choice("logfire", "Logfire（需先执行 logfire auth）"),
            Choice("langfuse", "Langfuse"),
        ),
    ),
    EnvField(
        "LANGFUSE_BASE_URL",
        "Langfuse 地址",
        default="https://cloud.langfuse.com",
        url=True,
        when=lambda values: values.get("OBS_BACKEND") == "langfuse",
    ),
    EnvField(
        "LANGFUSE_PUBLIC_KEY",
        "Langfuse Public Key",
        kind="secret",
        when=lambda values: values.get("OBS_BACKEND") == "langfuse",
    ),
    EnvField(
        "LANGFUSE_SECRET_KEY",
        "Langfuse Secret Key",
        kind="secret",
        when=lambda values: values.get("OBS_BACKEND") == "langfuse",
    ),
    EnvField(
        "USE_PLANNING_MODE",
        "启用规划模式",
        kind="confirm",
        default="true",
        choices=(Choice("true", "是"), Choice("false", "否")),
    ),
    EnvField(
        "PLANNING_CACHE_TTL",
        "规划缓存时长",
        kind="select",
        default="5m",
        choices=(Choice("5m", "5 分钟"), Choice("1h", "1 小时")),
        when=lambda values: values.get("USE_PLANNING_MODE") == "true",
    ),
)


def missing_fields(values: Values) -> list[EnvField]:
    """按提问顺序返回当前取值下缺失或不合法的配置项。"""
    return [field for field in ENV_FIELDS if field.when(values) and field.is_missing(values)]
