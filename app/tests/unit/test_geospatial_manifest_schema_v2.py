from __future__ import annotations

from server.services.geospatial.layer_auditor import audit_all_manifests


###############################################################################
def test_strict_schema_v2_audit_reports_required_coverage() -> None:
    report = audit_all_manifests(strict=True)

    assert report.ok, report.model_dump()
    assert report.manifest_count > 0
    assert report.schema_coverage
    assert report.provider_coverage
    assert report.renderer_coverage
    assert report.auth_coverage
    assert report.source_doc_coverage.get("with_source_docs") == report.manifest_count


###############################################################################
def test_metadata_only_manifests_do_not_claim_map_geometry() -> None:
    report = audit_all_manifests(strict=True)

    issues = [
        issue
        for issue in report.issues
        if issue.message == "Metadata-only manifest cannot claim map geometry."
    ]

    assert not issues
