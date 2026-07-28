from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.services.geospatial.coverage import CoverageService
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
class _NoCredentials:

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        return None

###############################################################################
def test_coverage_global_policy_supported() -> None:
    service = CoverageService(
        runtime_registry=RuntimeRegistry(
            manifest_loader=GeospatialManifestLoader(),
            credentials_repo=_NoCredentials(),  # type: ignore[arg-type]
        )
    )
    location = ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5)
    assert service.is_location_supported("osm_default", location)
