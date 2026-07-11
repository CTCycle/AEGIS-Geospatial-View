from server.services.agent.context_assembler import AgentContextAssembler
from server.services.agent.instruction_state import ConversationInstructionService


def _messages(count: int) -> list[dict]:
    return [{"id": i, "turn_index": i, "role": "user" if i % 2 else "assistant", "content": f"message {i} " + "x" * 500} for i in range(1, count + 1)]


def test_small_model_compacts_more_than_long_context_model() -> None:
    assembler = AgentContextAssembler()
    messages = _messages(80)
    kwargs = {"current_user_message": "Current request", "messages": messages, "directives": [], "task_state": {"current_task_id": "task-1"}, "map_memory": {}}
    small = assembler.assemble(provider="ollama", model="unknown-local", **kwargs)
    large = assembler.assemble(provider="google", model="gemini-2.5-flash", **kwargs)
    assert len(small.recent_messages) < len(large.recent_messages)
    assert small.current_user_message == "Current request"
    assert small.conversation_summary is not None
    assert small.omitted_message_ids


def test_durable_instruction_is_scoped_and_deduplicated() -> None:
    service = ConversationInstructionService()
    first = service.apply_user_message([], "For this conversation, always use satellite imagery.", 1)
    unchanged = service.apply_user_message(first, "Show Rome.", 2)
    repeated = service.apply_user_message(unchanged, "For this conversation, always use satellite imagery.", 3)
    assert len(service.active(repeated)) == 1
    assert service.active(repeated)[0].source_turn_index == 1
    assert service.active([]) == []


def test_later_conflicting_instruction_supersedes_prior_directive() -> None:
    service = ConversationInstructionService()
    directives = service.apply_user_message([], "From now on, use satellite imagery.", 1)
    directives = service.apply_user_message(directives, "From now on, do not use satellite imagery.", 2)
    assert len(service.active(directives)) == 1
    assert service.active(directives)[0].source_turn_index == 2
    assert any(item.status == "superseded" for item in directives)
