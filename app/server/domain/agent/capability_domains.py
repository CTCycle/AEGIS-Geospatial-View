"""Shared capability-domain enum without importing transport contracts."""

from __future__ import annotations

from enum import StrEnum


class CapabilityDomain(StrEnum):
    CONVERSATION = "conversation"
    PLACE_SEARCH = "place_search"
    DATA_RETRIEVAL = "data_retrieval"
    SPATIAL_ANALYSIS = "spatial_analysis"
    ROUTING = "routing"
    MAP_RENDERING = "map_rendering"
    MAP_STATE = "map_state"
    PROVIDER_DISCOVERY = "provider_discovery"
    MIXED = "mixed"
