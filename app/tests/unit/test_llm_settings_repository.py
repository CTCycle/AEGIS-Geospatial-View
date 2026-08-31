from __future__ import annotations

from server.repositories.model_settings import ModelSettingsRepository


###############################################################################
def test_model_settings_repository_creates_and_updates_record(sqlite_backend) -> None:
    repository = ModelSettingsRepository(sqlite_backend)
    repository.seed_required()
    current = repository.get_required()
    assert current.id is not None
    updated = repository.update(
        active_provider_mode="cloud",
        agent_model_provider="google",
        agent_model_name="gemini-2.0-flash",
        ollama_url="http://localhost:11434",
        openai_base_url="https://api.openai.com/v1",
        google_base_url="https://generativelanguage.googleapis.com/v1beta",
        deepseek_base_url="https://api.deepseek.com",
    )
    assert updated.active_provider_mode == "cloud"
    assert updated.agent_model_provider == "google"
    assert updated.agent_model_name == "gemini-2.0-flash"
