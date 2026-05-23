from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.actions import AgentAction
from server.domain.agent.tools import AgentToolCall
from server.services.agent.action_router import ActionRouter
from server.services.agent.chat_agent import ChatAgent
from server.services.agent.tool_executor import AgentExecutionContext, AgentToolExecutor
from server.services.agent.tool_manifest import ToolManifestService
from server.services.llm.types import LLMRequest, LLMToolDefinition


MAX_TOOL_CALLING_ROUNDS = 4
MAX_ACTIVE_TOOLS = 12

###############################################################################
class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)
    conversation_messages: list[dict[str, Any]] = Field(default_factory=list)
    map_context: dict[str, Any] = Field(default_factory=dict)
    visible_layer_ids: list[str] = Field(default_factory=list)
    available_source_ids: list[str] = Field(default_factory=list)

###############################################################################
class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    action_label: str
    action_confidence: float
    tools_considered: list[str] = Field(default_factory=list)
    tools_selected: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    map_operations: list[dict[str, Any]] = Field(default_factory=list)
    message: str

###############################################################################
class AgentPipeline:
    
    def __init__(
        self,
        *,
        action_router: ActionRouter,
        tool_manifest: ToolManifestService,
        tool_executor: AgentToolExecutor,
        llm_provider: Any | None = None,
        model: str = "",
        chat_agent: ChatAgent | None = None,
    ) -> None:
        self.action_router = action_router
        self.tool_manifest = tool_manifest
        self.tool_executor = tool_executor
        self.llm_provider = llm_provider
        self.model = model
        self.chat_agent = chat_agent or ChatAgent()

    # -------------------------------------------------------------------------
    async def run(self, request: AgentRequest) -> AgentResponse:
        turn = self.action_router.parse(request.message, request.memory_snapshot, request.conversation_messages)
        decision = self.action_router.decide(
            turn,
            map_context=request.map_context,
            visible_layer_ids=request.visible_layer_ids,
            available_source_ids=request.available_source_ids,
            max_tools=MAX_ACTIVE_TOOLS,
        )
        action = decision.action
        active_tools = self.tool_manifest.select_tools(
            action,
            topic=" ".join(turn.normalized_action.action_tags),
            map_context=request.map_context,
            visible_layer_ids=request.visible_layer_ids,
            available_source_ids=request.available_source_ids,
            max_tools=MAX_ACTIVE_TOOLS,
        )
        llm_tools = [
            LLMToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=tool.parameters_json_schema,
            )
            for tool in active_tools
        ]
        tool_calls: list[AgentToolCall] = []
        if self.llm_provider is not None and action != AgentAction.CHAT_RESPONSE:
            for _ in range(MAX_TOOL_CALLING_ROUNDS):
                response = self.llm_provider.chat(
                    LLMRequest(model=self.model, messages=[{"role": "user", "content": request.message}], temperature=0.0),
                    tools=llm_tools,
                    tool_choice="auto",
                )
                if not response.tool_calls:
                    break
                tool_calls.extend(
                    AgentToolCall(id=call.id, name=call.name, arguments=call.arguments)
                    for call in response.tool_calls
                )
                break
        elif action != AgentAction.CHAT_RESPONSE:
            tool_calls = [AgentToolCall(name=name, arguments={}) for name in decision.tool_names[:1]]

        context = AgentExecutionContext(
            map_context=request.map_context,
            visible_layer_ids=request.visible_layer_ids,
            available_source_ids=request.available_source_ids,
        )
        results = [await self.tool_executor.execute(call, context) for call in tool_calls]
        map_operations = [result.result for result in results if not result.error and result.result]
        return AgentResponse(
            action=action.value,
            action_label=turn.normalized_action.action_label,
            action_confidence=decision.action_confidence,
            tools_considered=[tool.name for tool in self.tool_manifest.list_all_tools()],
            tools_selected=[tool.name for tool in active_tools],
            tool_calls=[call.model_dump(mode="json") for call in tool_calls],
            map_operations=map_operations,
            message=self.chat_agent.render_response(user_message=request.message, tool_results=results),
        )
