from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.tool_result import ToolResult
from server.domain.llm.types import LLMToolDefinition

if TYPE_CHECKING:
    from server.domain.agent.capability_route import AgentPhase, AgentRunState

ToolHandler = Callable[[BaseModel, "AgentRunState"], Awaitable[Any]]
ToolResultNormalizer = Callable[[Any, str], ToolResult]
ToolSemanticValidator = Callable[[BaseModel, "AgentRunState"], list[str]]

###############################################################################
@dataclass(frozen=True)
class RegisteredTool:
    """One typed tool registration used by the native exposure path."""

    definition: LLMToolDefinition
    input_model: type[BaseModel]
    handler: ToolHandler
    domains: frozenset[CapabilityDomain]
    phases: frozenset["AgentPhase"]
    visibility: Literal["model", "internal"]
    prerequisites: frozenset[str]
    timeout_key: str
    idempotent: bool
    result_normalizer: ToolResultNormalizer
    semantic_validator: ToolSemanticValidator | None = None
