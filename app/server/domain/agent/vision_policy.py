from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

###############################################################################
# Vision inspection policy (domain).
#
# Deterministic policy state for attaching a captured map image to model calls
# when the selected model supports vision.  "Relevant failures" are derived
# from run state (failed render observations + failed map tool results) rather
# than stored counters, so the policy survives checkpoints for free.
###############################################################################


class VisionPolicy(str, Enum):
    DISABLED = "disabled"
    ALWAYS = "always"
    ON_FAILURE = "on_failure"
    FINAL_CHECK = "final_check"


VISION_POLICY_VALUES = tuple(item.value for item in VisionPolicy)
VISION_POLICY_DEFAULT = VisionPolicy.DISABLED.value


class VisionState(BaseModel):
    """Minimal persisted vision-usage tracking carried by ``AgentRunState``."""

    model_config = ConfigDict(extra="forbid")

    # ``"{map_session_id}:{collection_revision}"`` of the last render whose
    # image was attached to a model call.  Guards one attachment per render.
    attached_capture_ref: str | None = None
    vision_calls: int = Field(default=0, ge=0, le=64)


def capture_ref_for(
    map_session_id: str,
    collection_revision: int,
) -> str:
    """Canonical identity of one render capture."""
    return f"{map_session_id}:{collection_revision}"


# Map-generation / map-understanding / map-validation tool names whose failed
# results arm the ``on_failure`` policy.
MAP_INSPECTION_TOOL_NAMES = frozenset(
    {"apply_map_plan", "execute_geospatial_capability"}
)

# Tool validation error types that count as map-understanding/validation
# failures for vision arming purposes.
MAP_VALIDATION_ERROR_TYPES = frozenset(
    {"malformed_call", "schema_validation", "semantic_validation", "policy_rejection"}
)