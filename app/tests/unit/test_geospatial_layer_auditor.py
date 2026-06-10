from __future__ import annotations

from server.services.geospatial.layer_auditor import audit_all_manifests


###############################################################################
def test_layer_auditor_exposes_phase_one_coverage_sections() -> None:
    report = audit_all_manifests(strict=True)
    payload = report.model_dump()

    assert report.ok, payload
    assert {
        "schema_coverage",
        "provider_coverage",
        "renderer_coverage",
        "auth_coverage",
        "source_doc_coverage",
    }.issubset(payload)


###############################################################################
def test_layer_auditor_blocks_broken_manual_toggles() -> None:
    report = audit_all_manifests(strict=True)
    issues = [
        issue
        for issue in report.issues
        if issue.message == "Broken manifest cannot be exposed as a manual toggle."
    ]

    assert not issues


###############################################################################
def test_layer_auditor_production_gate_has_no_placeholder_or_visual_gaps() -> None:
    report = audit_all_manifests(strict=True, production=True)
    payload = report.model_dump()

    assert report.ok, payload
    assert all(not status.placeholder_statuses for status in report.implementation_statuses)
    assert all(status.provider_fetch_implemented for status in report.implementation_statuses)
    assert all(
        status.visual_tested
        for status in report.implementation_statuses
        if status.capability_id != status.provider_id
    )
