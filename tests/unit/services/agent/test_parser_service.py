from __future__ import annotations

from AEGIS.server.services.agent.parser_service import ParserService


class _ProviderStub:
    def structured_output(self, request, schema):  # noqa: ANN001
        user_message = request.messages[-1]["content"]
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
