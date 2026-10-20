from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from config.settings import Settings


def build_ollama_model(settings: Settings) -> OpenAIChatModel:
    return OpenAIChatModel(
        settings.models.ollama.model_name,
        provider=OllamaProvider(base_url=settings.models.ollama.base_url),
    )
