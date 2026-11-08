from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal

from server.common.identifiers import location_ref_matches

if TYPE_CHECKING:
    from server.contracts.geospatial import MapSession
    from server.domain.agent.capability_route import AgentRunState

RouteReferenceKind = Literal["location", "layer", "capability", "evidence"]


###############################################################################
def spells_layer(target: str, session: "MapSession") -> bool:
    """Whether the target contains, as whole words, the label or id of a layer on the map."""

    return any(
        re.search(rf"(?<!\w){re.escape(name)}(?!\w)", target, re.IGNORECASE) is not None
        for instance in session.overlay_collection.instances
        for name in (instance.instance_id, instance.capability_id, instance.label)
        if name
    )


###############################################################################
def route_reference_kind(target: str, state: "AgentRunState") -> RouteReferenceKind:
    """Return what a route target denotes, so every stage reads it the same way.

    A resolved place wins, so a layer named after a place cannot hide it. Any
    target that matches nothing known is a place still to be resolved.
    """

    if any(
        location_ref_matches(target, str(key), location.label)
        for key, location in state.location_refs.items()
    ):
        return "location"
    session = state.active_map_session
    if session is not None and spells_layer(target, session):
        return "layer"
    folded = target.strip().casefold()
    if folded in {str(ref).casefold() for ref in state.evidence_refs}:
        return "evidence"
    explicit = state.route.explicit_capability_ids if state.route is not None else []
    if folded in {str(ref).casefold() for ref in [*state.capability_ids, *explicit]}:
        return "capability"
    return "location"


###############################################################################
def place_targets(targets: Iterable[object], state: "AgentRunState") -> list[str]:
    """Keep only the targets that denote a geographic place."""

    return [
        str(target)
        for target in targets
        if route_reference_kind(str(target), state) == "location"
    ]


__all__ = ["RouteReferenceKind", "place_targets", "route_reference_kind", "spells_layer"]
