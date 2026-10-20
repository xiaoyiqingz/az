from typing import Any, Optional, Type

from pydantic_ai import Agent, toolsets
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from config.settings import Settings


def create_agent(
    model_name: Optional[str] = None,
    ollama_base_url: Optional[str] = None,
    system_prompt: Optional[str] = None,
    deps_type: Optional[Type[Any]] = None,
    output_type: Optional[Type[Any]] = None,
    instructions: Optional[str] = None,
    toolsets: Optional[list[toolsets.AbstractToolset]] = None,
    settings: Optional[Settings] = None,
) -> Agent:
    """
    创建统一的 Agent 实例

    Args:
        model_name: 模型名称，默认从环境变量 OLLAMA_MODEL 获取
        ollama_base_url: Ollama 基础 URL，默认从环境变量 OLLAMA_BASE_URL 获取
        system_prompt: 系统提示词
        deps_type: 依赖类型
        output_type: 输出类型

    Returns:
        Agent: 配置好的 Agent 实例
    """
    if settings is not None:
        if model_name is None:
            model_name = settings.models.ollama.model_ds
        if ollama_base_url is None:
            ollama_base_url = settings.models.ollama.base_url

    if model_name is None or ollama_base_url is None:
        raise ValueError("model_name 和 ollama_base_url 未提供，且未传入 settings")

    # 创建模型
    model = OpenAIChatModel(
        model_name,
        provider=OllamaProvider(base_url=ollama_base_url),
    )

    # 创建 Agent
    agent_kwargs: dict[str, Any] = {"model": model}

    if system_prompt is not None:
        agent_kwargs["system_prompt"] = system_prompt

    if deps_type is not None:
        agent_kwargs["deps_type"] = deps_type

    if output_type is not None:
        agent_kwargs["output_type"] = output_type

    if instructions is not None:
        agent_kwargs["instructions"] = instructions

    if toolsets is not None:
        agent_kwargs["toolsets"] = toolsets

    return Agent(**agent_kwargs)
