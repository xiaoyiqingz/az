from collections.abc import Callable

from pydantic_ai.models.openai import OpenAIChatModel

from config.settings import ModelProvider, Settings
from models.deepseek import build_deepseek_model
from models.mimo import build_mimo_model
from models.ollama import build_ollama_model
from models.qwen import build_qwen_model

MODEL_BUILDERS: dict[ModelProvider, Callable[[Settings], OpenAIChatModel]] = {
    "deepseek": build_deepseek_model,
    "qwen": build_qwen_model,
    "mimo": build_mimo_model,
    "ollama": build_ollama_model,
}


def build_model(settings: Settings) -> OpenAIChatModel:
    """按 ``AZ_MODEL_PROVIDER`` 构建主对话模型。"""
    return MODEL_BUILDERS[settings.models.provider](settings)
