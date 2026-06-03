from __future__ import annotations

from server.domain.chat import (
    OllamaPullRequest,
    OllamaPullResponse,
    OllamaRefreshResponse,
)
from server.services.chat.maintenance_service import ChatMaintenanceService


def test_maintenance_service_delegates_to_ollama_provider() -> None:
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
    service = ChatMaintenanceService(
        get_ollama_url=lambda: "http://localhost:11434",
        ollama_provider_factory=lambda base_url, _cache: _Provider(base_url=base_url),
    )

    refresh = service.refresh_ollama_models()
    pull = service.pull_ollama_model(OllamaPullRequest(model="llama3.2"))
    health = service.get_ollama_health()

    assert isinstance(refresh, OllamaRefreshResponse)
    assert refresh.local_model_capabilities[0].supports_tools is True
    assert refresh.local_model_capabilities[0].tool_support_source == "ollama_probe"
    assert isinstance(pull, OllamaPullResponse)
    assert health.ok is True
    assert ("pull_model", "llama3.2") in provider_calls
