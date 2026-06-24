from __future__ import annotations

from server.domain.agent.pipeline import SpecialistGroup
from server.domain.extraction.models import TurnParseResult


###############################################################################
class DeterministicAgentRouter:

    # -------------------------------------------------------------------------
    def select_specialist(self, turn: TurnParseResult) -> SpecialistGroup:
        if turn.relationship == "failure_inquiry":
            return "failure_diagnostics"
        if turn.task_class == "general_question":
            return "direct_chat"
        if "ambiguous_ground_temperature" in turn.ambiguities:
            return "environmental_data"
        if turn.relationship in {"follow_up", "correction"} and turn.requested_basemap:
            return "visualization_update"
        if turn.entity_target == "residential_buildings" or turn.requested_layers:
            return "geospatial_features"
        if turn.required_tool_category == "environmental_data":
            return "environmental_data"
        if turn.location_signals:
            return "map_layers"
        return "place_resolution"

