from __future__ import annotations

from AEGIS.server.configurations import server_settings
from AEGIS.server.services.llm.factory import LLMFactory


class EmbeddingFactory:
    def __init__(self, *, llm_factory: LLMFactory | None = None) -> None:
        self.llm_factory = llm_factory or LLMFactory()

    def get_embedding(self, *, provider: str, input_text: str) -> tuple[list[float], str]:
        normalized = provider.strip().lower()
        if normalized == "ollama":
            model = server_settings.vectors.default_ollama_embedding_model
        elif normalized == "openai":
            model = server_settings.vectors.default_openai_embedding_model
        elif normalized == "google":
            model = server_settings.vectors.default_google_embedding_model
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")
        provider_client = self.llm_factory.get_provider(normalized)
        return provider_client.embeddings(model=model, input_text=input_text), model
