from __future__ import annotations

from server.services.geospatial.layer_auditor import audit_all_manifests


###############################################################################
def test_geospatial_manifests_do_not_contain_secret_values() -> None:
    report = audit_all_manifests(strict=True)
    issues = [
        issue
        for issue in report.issues
        if issue.message == "Manifest appears to contain a secret-like value."
    ]

    assert not issues
