from __future__ import annotations

from urllib.error import URLError
from urllib.request import Request, urlopen

from AEGIS.server.configurations import server_settings
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.llm.factory import LLMFactory


class EmbeddingFactory:
    def __init__(
        self,
        *,
        llm_factory: LLMFactory | None = None,
        settings_repo: ModelSettingsRepository | None = None,
    ) -> None:
        self.llm_factory = llm_factory or LLMFactory()
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self._ollama_reachable: bool | None = None

    def _is_ollama_reachable(self) -> bool:
        if self._ollama_reachable is not None:
            return self._ollama_reachable
        try:
            ollama_url = self.settings_repo.get_or_create().ollama_url.rstrip("/")
            request = Request(f"{ollama_url}/api/tags", method="GET")
            with urlopen(request, timeout=1):
                self._ollama_reachable = True
        except (OSError, URLError, TimeoutError):
            self._ollama_reachable = False
        return self._ollama_reachable

    def normalize_provider(self, provider: str | None) -> str:
        normalized = str(provider or "ollama").strip().lower()
        if normalized in {"ollama", "openai", "google"}:
            return normalized
        raise ValueError(f"Unsupported embedding provider: {provider}")

    def resolve_default_model(self, provider: str | None) -> str:
        normalized = self.normalize_provider(provider)
        if normalized == "openai":
            return server_settings.vectors.default_openai_embedding_model
        if normalized == "google":
            return server_settings.vectors.default_google_embedding_model
        return server_settings.vectors.default_ollama_embedding_model

    def get_embedding(self, *, provider: str, input_text: str, model: str | None = None) -> tuple[list[float], str]:
        normalized = self.normalize_provider(provider)
        if normalized == "ollama" and not self._is_ollama_reachable():
            raise RuntimeError("Ollama is not reachable for embedding generation.")
        selected_model = model.strip() if isinstance(model, str) and model.strip() else self.resolve_default_model(normalized)
        provider_client = self.llm_factory.get_provider(normalized)
        return provider_client.embeddings(model=selected_model, input_text=input_text), selected_model
