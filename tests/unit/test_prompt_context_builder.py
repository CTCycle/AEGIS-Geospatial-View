from __future__ import annotations

from AEGIS.server.services.llm.context_builder import build_conversation_context


def test_context_builder_formats_messages_and_extracted_info() -> None:
    context = build_conversation_context(
        messages=[
            {"role": "user", "content": "Find Rome"},
            {"role": "assistant", "content": "Sure"},
        ],
        extracted_info='{"location":{"city":"Rome"}}',
        max_messages=5,
    )
    assert "# message 1\nFind Rome" in context
    assert "# message 2\nSure" in context
    assert '# extracted info\n{"location":{"city":"Rome"}}' in context


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
    assert "# message 1\ntwo" in context
    assert "# message 2\nthree" in context
    assert "# message 1\none" not in context
