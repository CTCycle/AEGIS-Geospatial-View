from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.services.geospatial.coverage import CoverageService
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
def test_coverage_global_policy_supported() -> None:
    service = CoverageService(runtime_registry=RuntimeRegistry())
    location = ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5)
    assert service.is_location_supported("osm_default", location)
