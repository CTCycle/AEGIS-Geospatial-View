from __future__ import annotations

import pytest

from server.services.agent.agent_tool_catalog_service import (
    AgentToolCatalogService,
    CapabilityCatalogFilter,
)
from server.services.agent.tool_registry import ToolRegistry


class _Registry:
    def __init__(self) -> None:
        self.load_calls = 0
        self.capabilities = [
            {
                "id": "b",
                "name": "Beta",
                "description": "Second",
                "provider": "test",
                "capabilityKind": "raster-overlay",
                "metadata": {"geometry_type": "raster-grid"},
            },
            {
                "id": "a",
                "name": "Alpha",
                "description": "First",
                "provider": "test",
                "capabilityKind": "analysis-tool",
                "metadata": {
                    "geometry_type": "point",
                    "argument_schema": {
                        "type": "object",
                        "properties": {"q": {"type": "string"}},
                        "required": ["q"],
                    },
                },
            },
        ]

    def load_capabilities(self):
        self.load_calls += 1
        return type(
            "Snapshot",
            (),
            {
                "basemaps": [],
                "overlays": self.capabilities,
                "cameras": [],
                "transit": [],
                "tools": [],
            },
        )()

    def get_capability(self, capability_id: str):
        return next(
            (item for item in self.capabilities if item["id"] == capability_id),
            None,
        )


def test_catalog_builds_stable_native_tools() -> None:
    service = AgentToolCatalogService(capability_registry=_Registry())
    names = [tool.name for tool in service.build_native_tools()]
    assert names == [
        "list_geospatial_capabilities",
        "describe_geospatial_capability",
        "execute_geospatial_capability",
    ]


def test_catalog_pagination_is_deterministic() -> None:
    service = AgentToolCatalogService(capability_registry=_Registry())
    first = service.list_geospatial_capabilities(CapabilityCatalogFilter(limit=1))
    second = service.list_geospatial_capabilities(
        CapabilityCatalogFilter(limit=1, cursor=first["next_cursor"])
    )
    assert first["items"][0]["id"] == "a"
    assert second["items"][0]["id"] == "b"


def test_capability_description_includes_executable_schema() -> None:
    service = AgentToolCatalogService(capability_registry=_Registry())
    descriptor = service.describe_geospatial_capability("a")
    assert descriptor["argument_schema"]["required"] == ["q"]


def test_execute_validates_arguments_against_manifest_schema() -> None:
    service = AgentToolCatalogService(capability_registry=_Registry())
    with pytest.raises(ValueError, match="Missing required argument 'q'"):
        service.execute_geospatial_capability("a", {})


def test_catalog_tools_register_with_tool_registry() -> None:
    registry = ToolRegistry()
    AgentToolCatalogService(capability_registry=_Registry()).register_with(registry)
    assert registry.has_native_tool("list_geospatial_capabilities")
    assert len(registry.list_native_tools()) == 3

