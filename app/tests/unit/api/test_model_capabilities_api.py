from __future__ import annotations

from server.api.chat import get_models, refresh_ollama_models
from server.domain.chat import OllamaRefreshResponse


###############################################################################
class _ModelLibraryService:

    # -------------------------------------------------------------------------
    def list_models(self, *, ollama_url: str):
        assert ollama_url == "http://ollama.test"
        return {
            "cloud": [
                {
                    "id": "gpt-4.1",
                    "name": "gpt-4.1",
                    "description": "cloud",
                    "provider": "openai",
                    "capabilities": ["chat", "tools", "structured_output"],
                    "supports_tools": True,
                    "supports_structured_output": True,
                    "metadata": {},
                }
            ],
            "local": [
                {
                    "id": "llama",
                    "name": "llama",
                    "description": "local",
                    "provider": "ollama",
                    "capabilities": ["chat"],
                    "supports_tools": False,
                    "supports_structured_output": False,
                    "tool_support_source": "ollama_probe",
                    "metadata": {},
                }
            ],
        }


###############################################################################
class _SettingsService:

    # -------------------------------------------------------------------------
    def get_ollama_url(self) -> str:
        return "http://ollama.test"


###############################################################################
class _MaintenanceService:

    # -------------------------------------------------------------------------
    def refresh_ollama_models(self):
        return OllamaRefreshResponse.model_validate({
            "status": "ok",
            "library_models": [],
            "local_models": ["llama"],
            "local_model_capabilities": [
                {
                    "id": "llama",
                    "name": "llama",
                    "description": "local",
                    "provider": "ollama",
                    "capabilities": ["chat", "tools"],
                    "supports_tools": True,
                    "supports_structured_output": False,
                    "tool_support_source": "ollama_probe",
                    "metadata": {},
                }
            ],
        })


###############################################################################
class _Runtime:
    model_library_service = _ModelLibraryService()
    settings_service = _SettingsService()
    maintenance_service = _MaintenanceService()


###############################################################################
def test_models_endpoint_returns_capability_metadata() -> None:
    response = get_models(runtime=_Runtime())
    assert response.cloud[0].supports_tools is True
    assert response.cloud[0].supports_structured_output is True
    assert response.local[0].supports_tools is False
    assert response.local[0].tool_support_source == "ollama_probe"


###############################################################################
def test_ollama_refresh_returns_capability_metadata() -> None:
    response = refresh_ollama_models(runtime=_Runtime())
    assert response.local_model_capabilities[0].supports_tools is True
    assert response.local_model_capabilities[0].tool_support_source == "ollama_probe"
