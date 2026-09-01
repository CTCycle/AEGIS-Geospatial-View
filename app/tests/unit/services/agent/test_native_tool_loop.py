from __future__ import annotations

import asyncio

from tests.conftest import run_async_in_thread
from typing import Any

from server.services.agent.native_tool_loop import (
    AgentExecutionContext,
    AgentToolLoopRequest,
    NativeToolLoop,
)
from server.services.agent.tool_registry import ToolRegistry
from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    ViewportPolicy,
)
from server.domain.agent.decision import ResolvedLocation
from server.domain.llm.types import LLMToolResult
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.llm.types import LLMResult, LLMToolCall, LLMToolDefinition


###############################################################################
class _Credentials:
    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN001
        _ = provider, label
        return None


###############################################################################
def _registry() -> ToolRegistry:
    return ToolRegistry(
        runtime_registry=RuntimeRegistry(
            manifest_loader=GeospatialManifestLoader(),
            credentials_repo=_Credentials(),  # type: ignore[arg-type]
        )
    )


###############################################################################
def _tool(name: str = "lookup") -> LLMToolDefinition:
    return LLMToolDefinition(
        name=name,
        description="Lookup",
        parameters_json_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    )


###############################################################################
class _Provider:
    # -------------------------------------------------------------------------
    def __init__(self, responses: list[LLMResult]) -> None:
        self.responses = responses
        self.requests: list[Any] = []

    # -------------------------------------------------------------------------
    def chat(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


###############################################################################
class _Factory:
    # -------------------------------------------------------------------------
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> _Provider:
        return self.provider


###############################################################################
def test_native_tool_loop_keeps_usage_with_concurrent_invocations() -> None:
    class _InvocationProvider(_Provider):
        def chat(self, request):  # noqa: ANN001
            return LLMResult(
                content=request.model,
                context_usage={
                    "provider": "test",
                    "model": request.model,
                    "estimated_input_tokens": 10,
                },
            )

    async def _run() -> None:
        provider = _InvocationProvider([])
        loop = NativeToolLoop(
            provider_factory=_Factory(provider), tool_registry=_registry()
        )

        async def run_model(model: str) -> object:
            request = AgentToolLoopRequest(
                provider="test",
                model=model,
                messages=[{"role": "user", "content": model}],
                tools=[],
                temperature=0,
                context=AgentExecutionContext(),
            )
            return await asyncio.to_thread(
                lambda: asyncio.run(loop.run(request))
            )

        first, second = await asyncio.gather(
            run_model("model-a"),
            run_model("model-b"),
        )

        assert first.context_usages == [
            {
                "provider": "test",
                "model": "model-a",
                "estimated_input_tokens": 10,
            }
        ]
        assert second.context_usages == [
            {
                "provider": "test",
                "model": "model-b",
                "estimated_input_tokens": 10,
            }
        ]

    run_async_in_thread(_run())


###############################################################################
def test_native_tool_loop_executes_single_tool_call() -> None:
    async def _run() -> None:
        provider = _Provider(
            [
                LLMResult(
                    content="",
                    tool_calls=[
                        LLMToolCall(id="1", name="lookup", arguments={"q": "Rome"})
                    ],
                ),
                LLMResult(content="done"),
            ]
        )
        registry = _registry()

        async def handler(
            arguments: dict[str, Any], context: AgentExecutionContext
        ) -> dict[str, Any]:
            return {"echo": arguments["q"], "conversation": context.conversation_id}

        registry.register_native_tool(_tool(), handler)
        loop = NativeToolLoop(
            provider_factory=_Factory(provider), tool_registry=registry
        )
        result = await loop.run(
            AgentToolLoopRequest(
                provider="test",
                model="model",
                messages=[{"role": "user", "content": "lookup Rome"}],
                tools=registry.list_native_tools(),
                temperature=0,
                context=AgentExecutionContext(conversation_id="s1"),
            )
        )
        assert result.final_text == "done"
        assert result.tool_results[0].content["ok"] is True
        assert provider.requests[1].messages[-1]["role"] == "tool"

    run_async_in_thread(_run())


###############################################################################
def test_native_tool_loop_replaces_working_state_instead_of_appending_it() -> None:
    async def _run() -> None:
        provider = _Provider(
            [
                LLMResult(
                    content="",
                    tool_calls=[
                        LLMToolCall(id="1", name="lookup", arguments={"q": "Rome"})
                    ],
                ),
                LLMResult(content="done"),
            ]
        )
        registry = _registry()

        async def handler(
            arguments: dict[str, Any], context: AgentExecutionContext
        ) -> dict[str, Any]:
            _ = context
            return {"echo": arguments["q"]}

        registry.register_native_tool(_tool(), handler)
        loop = NativeToolLoop(
            provider_factory=_Factory(provider), tool_registry=registry
        )
        result = await loop.run(
            AgentToolLoopRequest(
                provider="test",
                model="model",
                messages=[
                    {"role": "system", "content": "native agent"},
                    {"role": "user", "content": "lookup Rome"},
                ],
                tools=registry.list_native_tools(),
                temperature=0,
                context=AgentExecutionContext(parsed_request={"task": "lookup"}),
            )
        )

        assert result.final_text == "done"
        working_states = [
            message
            for request in provider.requests
            for message in request.messages
            if "WORKING_STATE" in str(message.get("content"))
        ]
        assert len(working_states) == 2
        assert '"completed_tool_results": []' in str(working_states[0]["content"])
        assert '"tool": "lookup"' in str(working_states[1]["content"])
        assert all(
            sum(
                "WORKING_STATE" in str(message.get("content"))
                for message in request.messages
            )
            == 1
            for request in provider.requests
        )

    run_async_in_thread(_run())


###############################################################################
def test_native_tool_loop_returns_tool_errors_as_tool_results() -> None:
    async def _run() -> None:
        provider = _Provider(
            [
                LLMResult(
                    content="",
                    tool_calls=[LLMToolCall(id="1", name="lookup", arguments={})],
                ),
                LLMResult(content="handled"),
            ]
        )
        registry = _registry()

        async def handler(
            arguments: dict[str, Any], context: AgentExecutionContext
        ) -> dict[str, Any]:
            return arguments

        registry.register_native_tool(_tool(), handler)
        loop = NativeToolLoop(
            provider_factory=_Factory(provider), tool_registry=registry
        )
        result = await loop.run(
            AgentToolLoopRequest(
                provider="test",
                model="model",
                messages=[{"role": "user", "content": "lookup"}],
                tools=registry.list_native_tools(),
                temperature=0,
            )
        )
        assert result.tool_results[0].is_error is True
        assert result.tool_results[0].content["error"]["code"] == "invalid_arguments"

    run_async_in_thread(_run())


###############################################################################
def test_native_tool_loop_stops_at_max_iterations() -> None:
    async def _run() -> None:
        provider = _Provider(
            [
                LLMResult(
                    content="",
                    tool_calls=[
                        LLMToolCall(id=str(index), name="lookup", arguments={"q": "x"})
                    ],
                )
                for index in range(3)
            ]
        )
        registry = _registry()

        async def handler(
            arguments: dict[str, Any], context: AgentExecutionContext
        ) -> dict[str, Any]:
            return arguments

        registry.register_native_tool(_tool(), handler)
        loop = NativeToolLoop(
            provider_factory=_Factory(provider),
            tool_registry=registry,
            max_iterations=2,
        )
        result = await loop.run(
            AgentToolLoopRequest(
                provider="test",
                model="model",
                messages=[{"role": "user", "content": "loop"}],
                tools=registry.list_native_tools(),
                temperature=0,
            )
        )
        assert result.stopped_reason == "max_iterations"
        assert result.iterations == 2

    run_async_in_thread(_run())


###############################################################################
def test_native_tool_loop_rejects_tools_disallowed_by_policy_constraints() -> None:
    async def _run() -> None:
        provider = _Provider(
            [
                LLMResult(
                    content="",
                    tool_calls=[
                        LLMToolCall(id="1", name="lookup", arguments={"q": "x"})
                    ],
                ),
                LLMResult(content="handled"),
            ]
        )
        registry = _registry()

        async def handler(
            arguments: dict[str, Any], context: AgentExecutionContext
        ) -> dict[str, Any]:
            raise AssertionError("policy-rejected tool must not execute")

        registry.register_native_tool(_tool(), handler)
        loop = NativeToolLoop(
            provider_factory=_Factory(provider), tool_registry=registry
        )
        result = await loop.run(
            AgentToolLoopRequest(
                provider="test",
                model="model",
                messages=[{"role": "user", "content": "loop"}],
                tools=registry.list_native_tools(),
                temperature=0,
                context=AgentExecutionContext(
                    policy_constraints={"allowed_tool_names": ["other_tool"]}
                ),
            )
        )
        assert result.tool_results[0].is_error is True
        assert result.tool_results[0].content["error"]["code"] == "tool_rejected"

    run_async_in_thread(_run())


###############################################################################
def test_native_tool_loop_uses_the_latest_map_session_result() -> None:
    location = ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5)
    viewport = ViewportPolicy(center_latitude=41.9, center_longitude=12.5)
    first = MapSession(
        session_id="first",
        resolved_location=location,
        basemap_id="osm",
        viewport=viewport,
        overlay_collection=OverlayCollectionState(),
    )
    second = first.model_copy(update={"session_id": "second"})
    result = NativeToolLoop._extract_map_session(
        [
            LLMToolResult(
                content={
                    "data": {
                        "operation": "map_session_created",
                        "map_session": first.model_dump(mode="json"),
                    }
                }
            ),
            LLMToolResult(
                content={
                    "data": {
                        "operation": "map_session_created",
                        "map_session": second.model_dump(mode="json"),
                    }
                }
            ),
        ]
    )

    assert result is not None
    assert result.session_id == "second"
