from __future__ import annotations

from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.search.planner import SearchPlanner


def test_search_planner_keeps_traffic_as_overlay() -> None:
    planner = SearchPlanner()
    manifests = GeospatialManifestLoader().load_all()
    plan = planner.plan(
        intent={
            "overlays": {"requested": ["tomtom_traffic_flow"]},
            "display_area": {"mode": "radius"},
            "planning": {"confidence": 0.8},
        },
        retrieval={
            "basemaps": [{"id": "osm_default", "score": 0.9}],
            "overlays": [{"id": "tomtom_traffic_flow", "score": 0.8}],
            "providers": [],
        },
        manifests=manifests,
    )
    assert plan.selected_basemap_id == "osm_default"
    assert "tomtom_traffic_flow" in plan.selected_overlay_ids
