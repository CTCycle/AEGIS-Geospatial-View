from __future__ import annotations

from server.domain.chat import (
    OllamaPullRequest,
    OllamaPullResponse,
    OllamaRefreshResponse,
    VectorizationResponse,
)
from server.services.chat.maintenance_service import ChatMaintenanceService


class _VectorIndexerStub:
    def __init__(self) -> None:
        self.called: list[str] = []

    def sync(self):  # noqa: ANN201
        self.called.append("sync")
        return {"status": "ok", "indexed_documents": 1, "vector_path": "vectors"}

    def rebuild(self):  # noqa: ANN201
        self.called.append("rebuild")
        return {"status": "ok", "indexed_documents": 2, "vector_path": "vectors"}


def test_maintenance_service_delegates_to_provider_and_vector_indexer(monkeypatch) -> None:
    provider_calls: list[tuple[str, str | None]] = []

    class _Provider:
        def __init__(self, *, base_url: str) -> None:
            provider_calls.append(("init", base_url))

        def list_library_models(self):  # noqa: ANN201
            provider_calls.append(("list_library_models", None))
            return [type("Model", (), {"name": "llama3.2"})()]

        def list_models(self):  # noqa: ANN201
            provider_calls.append(("list_models", None))
            return [
                type(
                    "Model",
                    (),
                    {
                        "name": "llama3.2",
                        "description": "local",
                        "provider": "ollama",
                        "capabilities": ["chat", "tools"],
                        "metadata": {"tool_support_source": "ollama_probe"},
                    },
                )()
            ]

        def pull_model(self, *, model: str):  # noqa: ANN201
            provider_calls.append(("pull_model", model))
            return {"status": "ok", "model": model}

        def health_check(self):  # noqa: ANN201
            provider_calls.append(("health_check", None))
            return {"ok": True, "detail": "healthy"}

    monkeypatch.setattr(
        "server.services.chat.maintenance_service.OllamaProvider", _Provider
    )
    vectors = _VectorIndexerStub()
    service = ChatMaintenanceService(
        get_ollama_url=lambda: "http://localhost:11434", vector_indexer=vectors
    )

    refresh = service.refresh_ollama_models()
    pull = service.pull_ollama_model(OllamaPullRequest(model="llama3.2"))
    health = service.get_ollama_health()
    sync = service.sync_vectors()
    rebuild = service.rebuild_vectors()

    assert isinstance(refresh, OllamaRefreshResponse)
    assert refresh.local_model_capabilities[0].supports_tools is True
    assert refresh.local_model_capabilities[0].tool_support_source == "ollama_probe"
    assert isinstance(pull, OllamaPullResponse)
    assert health.ok is True
    assert isinstance(sync, VectorizationResponse)
    assert isinstance(rebuild, VectorizationResponse)
    assert ("pull_model", "llama3.2") in provider_calls
    assert vectors.called == ["sync", "rebuild"]
