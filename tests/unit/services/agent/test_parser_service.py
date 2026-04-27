from __future__ import annotations

import json

import pytest

from AEGIS.server.services.agent.parser_service import PARSER_SYSTEM_PROMPT, ParserService
from AEGIS.server.services.llm.errors import LLMConfigurationError


class _ProviderStub:
    def structured_output(self, request, schema):  # noqa: ANN001
        payload = json.loads(request.messages[-1]["content"])
        user_message = payload.get("user_message", "")
        if "Colosseum" in user_message:
            return {
                "task_class": "direct_query",
                "intent_id": "location_lookup",
                "intent_label": "Location lookup",
                "task_tags": ["direct_query"],
                "intent_tags": ["coordinates"],
                "requires_location": True,
                "location_signals": [
                    {
                        "signal_type": "city",
                        "raw_value": "Rome",
                        "normalized_value": "Rome",
                        "confidence": 0.9,
                    }
                ],
                "temporal_signal": {"mode": "none"},
                "ambiguities": [],
                "disallowed_patterns": [],
                "parser_confidence": 0.9,
            }
        if "القاهرة" in user_message:
            return {
                "task_class": "map_search",
                "intent_id": "air_quality_map",
                "intent_label": "Air quality map",
                "task_tags": ["map"],
                "intent_tags": ["air_quality"],
                "requested_visualizations": ["air_quality"],
                "requires_location": True,
                "location_signals": [
                    {
                        "signal_type": "city",
                        "raw_value": "القاهرة",
                        "normalized_value": "Cairo",
                        "confidence": 0.9,
                    },
                    {
                        "signal_type": "city",
                        "raw_value": "الخرطوم",
                        "normalized_value": "Khartoum",
                        "confidence": 0.85,
                    },
                ],
                "temporal_signal": {"mode": "none"},
                "ambiguities": ["'الخرطية' likely intended as 'الخرطوم' (Khartoum)"],
                "disallowed_patterns": [],
                "parser_confidence": 0.9,
            }
        return {
            "task_class": "general_question",
            "intent_id": "general_map",
            "intent_label": "General map request",
            "task_tags": ["map"],
            "intent_tags": ["map"],
            "requires_location": False,
            "location_signals": [],
            "temporal_signal": {"mode": "none"},
            "ambiguities": [],
            "disallowed_patterns": [],
            "parser_confidence": 0.5,
        }


class _FactoryStub:
    def get_parser_provider(self, provider: str):  # noqa: ARG002
        return _ProviderStub()


class _ConfigErrorFactoryStub:
    def get_parser_provider(self, provider: str):  # noqa: ARG002
        raise LLMConfigurationError("OpenAI credentials are saved but cannot be decrypted.")


def test_parser_service_classifies_direct_query() -> None:
    parser = ParserService(llm_factory=_FactoryStub(), provider="openai", model="gpt-4.1-mini")
    result = parser.parse_turn(
        user_message="What are the coordinates of the Colosseum in Rome?",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert result.task_class == "direct_query"
    assert result.normalized_intent.intent_id == "location_lookup"


def test_parser_service_normalizes_recent_messages_to_strings() -> None:
    parser = ParserService(llm_factory=_FactoryStub(), provider="openai", model="gpt-4.1-mini")
    result = parser.parse_turn(
        user_message="Where am I?",
        memory_snapshot={"active_location": None},
        conversation_messages=[
            {
                "id": 515,
                "session_id": 217,
                "turn_index": 0,
                "role": "assistant",
                "content": None,
                "created_at": None,
            }
        ],
    )
    recent = result.conversation_context.recent_messages
    assert len(recent) == 1
    assert recent[0]["id"] == "515"
    assert recent[0]["session_id"] == "217"
    assert recent[0]["turn_index"] == "0"
    assert recent[0]["content"] == ""


def test_parser_service_does_not_hide_configuration_errors() -> None:
    parser = ParserService(
        llm_factory=_ConfigErrorFactoryStub(),
        provider="openai",
        model="gpt-4.1-mini",
    )

    with pytest.raises(LLMConfigurationError):
        parser.parse_turn(
            user_message="Show Rome",
            memory_snapshot={},
            conversation_messages=[],
        )


def test_parser_prompt_enforces_multilingual_and_verbatim_location_rules() -> None:
    assert "The user may write in any language" in PARSER_SYSTEM_PROMPT
    assert "raw_value must be a verbatim span" in PARSER_SYSTEM_PROMPT
    assert "requested_visualizations must use only canonical ids" in PARSER_SYSTEM_PROMPT


def test_parser_service_drops_non_verbatim_location_hallucinations() -> None:
    parser = ParserService(llm_factory=_FactoryStub(), provider="openai", model="gpt-4.1-mini")
    result = parser.parse_turn(
        user_message="اعرض جودة الهواء في القاهرة على الخريطة.",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert [item.raw_value for item in result.location_signals] == ["القاهرة"]
    assert result.ambiguities == []
