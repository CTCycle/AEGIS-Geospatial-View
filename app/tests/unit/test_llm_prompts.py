from __future__ import annotations

from server.services.llm.prompts import (
    get_agent_decision_system_prompt,
    get_agent_extraction_prompt,
    get_agent_response_prompt,
    prompt_within_budget,
)


def test_prompt_builders_include_required_guardrails() -> None:
    extraction = get_agent_extraction_prompt(provider="ollama", model="llama3.2")
    decision = get_agent_decision_system_prompt(provider="openai", model="gpt-4.1-mini")
    response = get_agent_response_prompt(provider="google", model="gemini-2.0-flash")

    for prompt in (extraction, decision, response):
        lowered = prompt.lower()
        assert "location-driven geospatial" in lowered
        assert "never explain technical implementation details" in lowered
        assert "never expose app internals" in lowered
        assert "ask for missing information only when genuinely necessary" in lowered


def test_prompt_builders_stay_under_token_budget() -> None:
    prompts = [
        get_agent_extraction_prompt(provider="ollama", model="llama3.2"),
        get_agent_decision_system_prompt(provider="openai", model="gpt-4.1"),
        get_agent_response_prompt(provider="google", model="gemini-2.0-flash"),
    ]
    assert all(prompt_within_budget(prompt, max_tokens=2000) for prompt in prompts)
