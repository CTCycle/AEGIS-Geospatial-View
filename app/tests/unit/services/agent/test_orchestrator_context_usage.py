from __future__ import annotations

from types import SimpleNamespace

from server.contracts.chat import ChatTurnResponse, ContextUsageResponse
from server.services.agent.orchestrator import AgentOrchestrator


###############################################################################
def _usage(
    *,
    estimated: int,
    reported_input: int,
    reported_output: int,
) -> ContextUsageResponse:
    return ContextUsageResponse(
        estimated_input_tokens=estimated,
        selected_context_window=4096,
        model_context_limit=4096,
        usage_percent=round(reported_input / 4096 * 100, 1),
        provider="test",
        model="runtime-model",
        reported_input_tokens=reported_input,
        reported_output_tokens=reported_output,
        reserved_output_tokens=512,
        tool_schema_tokens=40,
        response_schema_tokens=30,
        safety_margin_tokens=512,
        usage_source="provider_reported",
        usable_prompt_budget_tokens=3072,
        current_conversation_tokens=estimated,
        expected_output_tokens=512,
        context_profile_source="provider_metadata",
    )


###############################################################################
def test_phase_usage_reports_peak_request_and_preserves_all_phase_totals() -> None:
    parser_usage = _usage(estimated=90, reported_input=100, reported_output=7)
    native_usage = _usage(estimated=500, reported_input=700, reported_output=11)
    second_native_usage = _usage(
        estimated=600,
        reported_input=900,
        reported_output=13,
    )
    synthesis_usage = _usage(estimated=180, reported_input=200, reported_output=5)
    response = ChatTurnResponse.model_construct(
        context_usage=parser_usage,
        tool_payload={
            "context_usages": [
                native_usage.model_dump(mode="json"),
                second_native_usage.model_dump(mode="json"),
            ]
        },
    )
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.response_synthesizer = SimpleNamespace(
        last_context_usage=synthesis_usage.model_dump(mode="json")
    )

    result = orchestrator._with_phase_usage(response)

    assert result.context_usage is not None
    assert result.context_usage.peak_request_tokens == 900
    assert result.context_usage.total_input_tokens == 1900
    assert result.context_usage.total_output_tokens == 36
    assert result.context_usage.usage_percent == round(900 / 4096 * 100, 1)
    assert set(result.context_usage.phases) == {"parser", "native_loop", "synthesis"}
    assert result.context_usage.phases["native_loop"]["reported_input_tokens"] == 1600
    assert result.context_usage.phases["native_loop"]["reported_output_tokens"] == 24
    assert result.context_usage.phases["native_loop"]["peak_request_tokens"] == 900


###############################################################################
def test_phase_context_limit_is_used_when_initial_sample_is_unknown() -> None:
    parser_usage = _usage(estimated=90, reported_input=100, reported_output=7).model_copy(
        update={
            "selected_context_window": None,
            "model_context_limit": None,
            "usage_percent": None,
        }
    )
    native_usage = _usage(estimated=500, reported_input=700, reported_output=11)
    response = ChatTurnResponse.model_construct(
        context_usage=parser_usage,
        tool_payload={"context_usages": [native_usage.model_dump(mode="json")]},
    )
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.response_synthesizer = SimpleNamespace(last_context_usage=None)

    result = orchestrator._with_phase_usage(response)

    assert result.context_usage is not None
    assert result.context_usage.model_context_limit == 4096
    assert result.context_usage.usage_percent == round(700 / 4096 * 100, 1)
