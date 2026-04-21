from __future__ import annotations

from AEGIS.server.services.agent.parser_service import ParserService


def test_parser_service_classifies_direct_query() -> None:
    parser = ParserService()
    result = parser.parse_turn(
        user_message="What are the coordinates of the Colosseum in Rome?",
        memory_snapshot={},
        conversation_messages=[],
    )
    assert result.task_class == "direct_query"
    assert result.normalized_intent.intent_id == "location_lookup"
