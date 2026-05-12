from __future__ import annotations

from server.services.geospatial.layer_auditor import (
    PLACEHOLDER_STATUSES,
    audit_all_manifests,
)


def test_geospatial_implementation_audit_reports_all_capabilities() -> None:
    report = audit_all_manifests(strict=True)

    assert report.ok
    assert report.manifest_count == len(report.implementation_statuses)
    assert {
        "schema_valid",
        "runtime_registered",
        "provider_fetch_implemented",
        "normalizer_implemented",
        "cache_implemented",
        "api_endpoint_covered",
        "client_renderer_covered",
        "unit_tested",
        "visual_tested",
    }.issubset(report.implementation_statuses[0].model_dump())


def test_functional_capabilities_do_not_use_placeholder_provider_statuses() -> None:
    report = audit_all_manifests(strict=True)

    issues = [
        issue
        for issue in report.issues
        if "Functional capability provider exposes placeholder statuses" in issue.message
    ]

    assert not issues
    assert PLACEHOLDER_STATUSES

