from __future__ import annotations

import json

from server.repositories.model_settings import ModelSettingsRepository


###############################################################################
def test_parser_model_fields_round_trip() -> None:
    repo = ModelSettingsRepository()
    repo.update(
        active_provider_mode="local",
        chat_model_provider="ollama",
        chat_model_name="llama3.2",
        parser_model_provider="ollama",
        parser_model_name="llama3.2",
        agent_model_provider="ollama",
        agent_model_name="llama3.2",
        ollama_url="http://localhost:11434",
        openai_base_url=None,
        google_base_url=None,
    )
    current = repo.get_or_create()
    assert current.parser_model_provider == "ollama"
    assert current.parser_model_name == "llama3.2"


###############################################################################
def test_get_or_create_uses_current_schema_defaults() -> None:
    repo = ModelSettingsRepository()

    current = repo.get_or_create()

    assert current.capabilities_json == json.dumps([])
    assert current.supports_tools is False
    assert current.supports_structured_output is False
    assert current.tool_support_source == "unknown"
