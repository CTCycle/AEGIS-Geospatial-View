from __future__ import annotations

from types import SimpleNamespace

from server.services.chat.settings_service import ChatSettingsService


###############################################################################
class _SettingsRepo:

    # -------------------------------------------------------------------------
    def get_or_create(self):  # noqa: ANN201
        return SimpleNamespace(
            active_provider_mode="cloud",
            chat_model_provider="openai",
            chat_model_name="gpt-4.1-mini",
            parser_model_provider="openai",
            parser_model_name="gpt-4.1-mini",
            agent_model_provider="openai",
            agent_model_name="gpt-4.1-mini",
            ollama_url="http://localhost:11434",
            openai_base_url=None,
            google_base_url=None,
        )


###############################################################################
class _CredentialsRepo:

    # -------------------------------------------------------------------------
    def list_active(self):  # noqa: ANN201
        return [
            SimpleNamespace(
                provider="openai",
                label="api_key",
                encrypted_value="readable",
            ),
            SimpleNamespace(
                provider="google",
                label="api_key",
                encrypted_value="broken",
            ),
        ]


###############################################################################
class _Crypto:

    # -------------------------------------------------------------------------
    def decrypt(self, encrypted_value: str) -> str:
        if encrypted_value == "broken":
            raise ValueError("bad key")
        return "secret"


###############################################################################
def test_settings_response_reports_credential_health() -> None:
    service = ChatSettingsService(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo(),
        crypto_service=_Crypto(),
    )

    response = service.get_settings()

    assert response.credentials == {
        "openai": {"api_key": True},
        "google": {"api_key": True},
    }
    assert response.credential_health == {
        "openai": {"api_key": "healthy"},
        "google": {"api_key": "unreadable"},
    }
