from __future__ import annotations

from pydantic import ValidationError

from server.domain.chat import ModelSettingsUpdateRequest


def test_model_settings_update_request_forbids_unknown_fields() -> None:
    try:
        ModelSettingsUpdateRequest(unknown_field="x")
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected ValidationError for unknown field")


def test_model_settings_update_request_requires_string_credentials() -> None:
    try:
        ModelSettingsUpdateRequest(credentials={"openai": {"api_key": 123}})
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected ValidationError for non-string credential value")


def test_model_settings_update_request_accepts_valid_payload() -> None:
    payload = ModelSettingsUpdateRequest(
        active_provider_mode="cloud",
        chat_model_provider="openai",
        chat_model_name="gpt-4.1-mini",
        credentials={"openai": {"api_key": "secret"}},
    )

    assert payload.active_provider_mode == "cloud"
    assert payload.credentials["openai"]["api_key"] == "secret"


def test_model_settings_update_request_rejects_invalid_base_urls() -> None:
    try:
        ModelSettingsUpdateRequest(ollama_url="not-a-url")
    except ValidationError as exc:
        assert "Base URL must start with http:// or https://" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for invalid Ollama URL")
