from __future__ import annotations

from server.domain.geospatial.registry import AttributionEntry


###############################################################################
class AttributionService:

    # -------------------------------------------------------------------------
    def from_manifest(self, manifest: dict[str, object]) -> AttributionEntry:
        license_payload = manifest.get("license")
        license_data = license_payload if isinstance(license_payload, dict) else {}
        return AttributionEntry(
            capability_id=str(manifest.get("id") or ""),
            provider_id=str(manifest.get("provider") or "unknown"),
            label=str(license_data.get("name") or manifest.get("provider") or ""),
            url=str(license_data.get("url") or ""),
            required=bool(license_data.get("attributionRequired", False)),
        )

    # -------------------------------------------------------------------------
    def merge_labels(self, manifests: list[dict[str, object]]) -> list[str]:
        labels: list[str] = []
        seen: set[str] = set()
        for manifest in manifests:
            entry = self.from_manifest(manifest)
            normalized = entry.label.strip()
            if not normalized or normalized in seen:
                continue
            labels.append(normalized)
            seen.add(normalized)
        return labels
