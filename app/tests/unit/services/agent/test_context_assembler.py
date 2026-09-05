from server.services.agent.context_assembler import AgentContextAssembler
from server.services.agent.instruction_state import ConversationInstructionService
from server.services.llm.types import ModelContextProfile
from server.services.llm.context_budget import estimate_json_tokens


###############################################################################
class _ExplicitProfileResolver:
    def resolve(self, provider: str, model: str) -> ModelContextProfile:  # noqa: ARG002
        if model == "4k-local":
            return ModelContextProfile(
                provider=provider,
                model=model,
                context_window_tokens=4096,
                maximum_output_tokens=512,
                default_output_reserve=512,
                metadata_source="provider_metadata",
            )
        return ModelContextProfile(
            provider=provider,
            model=model,
            context_window_tokens=1_048_576,
            maximum_output_tokens=8192,
            default_output_reserve=8192,
            metadata_source="provider_metadata",
        )


###############################################################################
def _messages(count: int) -> list[dict]:
    return [
        {
            "id": i,
            "turn_index": i,
            "role": "user" if i % 2 else "assistant",
            "content": f"message {i} " + "x" * 500,
        }
        for i in range(1, count + 1)
    ]


###############################################################################
def test_known_model_profiles_drive_compaction_without_unknown_fallback() -> None:
    assembler = AgentContextAssembler(_ExplicitProfileResolver())
    messages = _messages(80)
    kwargs = {
        "current_user_message": "Current request",
        "messages": messages,
        "directives": [],
        "task_state": {"current_task_id": "task-1"},
        "map_memory": {},
    }
    small = assembler.assemble(provider="ollama", model="4k-local", **kwargs)
    large = assembler.assemble(provider="google", model="gemini-2.5-flash", **kwargs)
    assert len(small.recent_messages) < len(large.recent_messages)
    assert small.current_user_message == "Current request"
    assert small.conversation_summary is not None
    assert small.omitted_message_ids


###############################################################################
def test_durable_instruction_is_scoped_and_deduplicated() -> None:
    service = ConversationInstructionService()
    first = service.apply_user_message(
        [], "For this conversation, always use satellite imagery.", 1
    )
    unchanged = service.apply_user_message(first, "Show Rome.", 2)
    repeated = service.apply_user_message(
        unchanged, "For this conversation, always use satellite imagery.", 3
    )
    assert len(service.active(repeated)) == 1
    assert service.active(repeated)[0].source_turn_index == 1
    assert service.active([]) == []


###############################################################################
def test_later_conflicting_instruction_supersedes_prior_directive() -> None:
    service = ConversationInstructionService()
    directives = service.apply_user_message(
        [], "From now on, use satellite imagery.", 1
    )
    directives = service.apply_user_message(
        directives, "From now on, do not use satellite imagery.", 2
    )
    assert len(service.active(directives)) == 1
    assert service.active(directives)[0].source_turn_index == 2
    assert any(item.status == "superseded" for item in directives)


def test_oversized_newest_history_is_compacted_without_losing_location_state() -> None:
    location = {"active_location": {"name": "Rome", "lat": 41.9, "lon": 12.5}}
    package = AgentContextAssembler(_ExplicitProfileResolver()).assemble(
        provider="ollama",
        model="4k-local",
        current_user_message="Zoom there",
        messages=[{"id": 1, "turn_index": 1, "role": "user", "content": "x" * 100_000}],
        directives=[],
        task_state={},
        map_memory=location,
    )
    assert package.recent_messages == []
    assert package.omitted_message_ids == [1]
    assert package.map_memory == location
    assert estimate_json_tokens(package.model_dump(mode="json")) < 3072


def test_unknown_model_history_is_bounded_and_excludes_renderer_payloads() -> None:
    for turns in (10, 25, 50):
        messages = _messages(turns)
        for message in messages:
            message["tool_payload"] = {"features": ["geometry" * 10_000]}
            message["map_session"] = {"geometry": "coordinates" * 10_000}
        package = AgentContextAssembler().assemble(
            provider="unknown",
            model="unknown",
            current_user_message="Back to Rome",
            messages=messages,
            directives=[],
            task_state={},
            map_memory={},
        )
        assert estimate_json_tokens(package.model_dump(mode="json")) < 16_384
        assert all(
            "tool_payload" not in item and "map_session" not in item
            for item in package.recent_messages
        )
        assert package.relevant_tool_outcomes == []
