from __future__ import annotations

from server.repositories.model_settings import ModelSettingsRepository


###############################################################################
def test_model_settings_repository_creates_and_updates_record() -> None:
    repository = ModelSettingsRepository()
    current = repository.get_or_create()
    assert current.id is not None
    updated = repository.update(
        active_provider_mode="cloud",
        chat_model_provider="openai",
        chat_model_name="gpt-4.1-mini",
        parser_model_provider="openai",
        parser_model_name="gpt-4.1-mini",
        agent_model_provider="google",
        agent_model_name="gemini-2.0-flash",
        ollama_url="http://localhost:11434",
        openai_base_url="https://api.openai.com/v1",
        google_base_url="https://generativelanguage.googleapis.com/v1beta",
    )
    assert updated.active_provider_mode == "cloud"
    assert updated.chat_model_provider == "openai"
    assert updated.parser_model_provider == "openai"
