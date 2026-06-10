from __future__ import annotations

from server.domain.geographics import LayerHealthStatus
from server.services.geospatial.attribution import AttributionService
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.source_health import SourceHealthMonitor


###############################################################################
def test_source_health_prefers_recorded_provider_status() -> None:
    monitor = SourceHealthMonitor()
    manifest = {
        "provider": "rainviewer",
        "reliability": {"status": "partial"},
    }

    monitor.record("rainviewer", LayerHealthStatus.FUNCTIONAL)

    assert monitor.status_for_manifest(manifest) == LayerHealthStatus.FUNCTIONAL


###############################################################################
def test_source_health_uses_manifest_status_without_probe_record() -> None:
    monitor = SourceHealthMonitor()

    status = monitor.status_for_manifest(
        {"provider": "rainviewer", "reliability": {"status": "partial"}}
    )

    assert status == LayerHealthStatus.PARTIAL


###############################################################################
def test_attribution_service_deduplicates_manifest_labels() -> None:
    manifests = GeospatialManifestLoader().load_all()
    service = AttributionService()
    selected = [
        item
        for item in manifests["basemaps"] + manifests["overlays"]
        if item["provider"] == "gibs"
    ][:2]

    labels = service.merge_labels(selected)

    assert labels
    assert len(labels) == len(set(labels))
