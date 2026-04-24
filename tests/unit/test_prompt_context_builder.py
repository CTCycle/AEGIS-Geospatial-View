from __future__ import annotations

from AEGIS.server.services.llm.context_builder import build_conversation_context


###############################################################################
def test_context_builder_formats_messages_and_extracted_info() -> None:
    context = build_conversation_context(
        messages=[
            {"role": "user", "content": "Find Rome"},
            {"role": "assistant", "content": "Sure"},
        ],
        extracted_info='{"location":{"city":"Rome"}}',
        max_messages=5,
        current_user_message="Find Rome",
    )
    assert "user: Find Rome" in context
    assert "assistant: Sure" in context
    assert '# current extracted state\n{"location":{"city":"Rome"}}' in context
    assert "# current user message\nFind Rome" in context


###############################################################################
def test_context_builder_keeps_most_recent_messages_only() -> None:
    context = build_conversation_context(
        messages=[
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
        ],
        extracted_info="{}",
        max_messages=2,
    )
    assert "assistant: two" in context
    assert "user: three" in context
    assert "user: one" not in context
