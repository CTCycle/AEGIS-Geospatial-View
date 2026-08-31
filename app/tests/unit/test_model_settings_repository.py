from __future__ import annotations

import pytest

from server.repositories.model_settings import ModelSettingsRepository


###############################################################################
def test_get_required_fails_when_initialization_has_not_seeded_settings(
    sqlite_backend,
) -> None:
    repo = ModelSettingsRepository(sqlite_backend)

    with pytest.raises(RuntimeError, match="database initialization must seed it"):
        repo.get_required()


###############################################################################
def test_seed_required_creates_singleton_and_is_idempotent(sqlite_backend) -> None:
    repo = ModelSettingsRepository(sqlite_backend)

    repo.seed_required()
    repo.seed_required()
    current = repo.get_required()

    assert current.id is not None
    assert current.active_provider_mode == "cloud"
    assert current.agent_model_provider == ""
    assert current.agent_model_name == ""


###############################################################################
def test_update_persists_selected_agent_model(sqlite_backend) -> None:
    repo = ModelSettingsRepository(sqlite_backend)
    repo.seed_required()

    repo.update(
        active_provider_mode="local",
        agent_model_provider="ollama",
        agent_model_name="llama3.2",
        ollama_url="http://localhost:11434",
        openai_base_url=None,
        google_base_url=None,
        deepseek_base_url=None,
    )
    current = repo.get_required()

    assert current.agent_model_provider == "ollama"
    assert current.agent_model_name == "llama3.2"
