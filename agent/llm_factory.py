from typing import Any

from config.settings import Settings
from agent.ollama_client import OllamaTextClient


def create_text_client(settings: Settings) -> Any:
    """Crea el cliente LLM configurado sin obligar imports de Gemini cuando se usa Ollama."""
    if settings.llm_provider == "ollama":
        return OllamaTextClient(settings)

    if settings.llm_provider == "gemini":
        from agent.gemini_client import GeminiTextClient
        return GeminiTextClient(settings)

    raise ValueError(
        f"Proveedor LLM no soportado: {settings.llm_provider}. "
        "Usá HADES_LLM_PROVIDER=ollama o HADES_LLM_PROVIDER=gemini."
    )
