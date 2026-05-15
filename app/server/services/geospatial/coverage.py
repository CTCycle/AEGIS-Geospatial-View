from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.services.geospatial.runtime_registry import RuntimeRegistry


class CoverageService:
    def __init__(self, *, runtime_registry: RuntimeRegistry) -> None:
        self.runtime_registry = runtime_registry

    def is_location_supported(self, capability_id: str, location: ResolvedLocation) -> bool:
        policy = self.runtime_registry.coverage_policy(capability_id)
        latitude = float(location.latitude)

        if policy == "global":
            return True
        if policy == "global-partial":
            return -85.0 <= latitude <= 85.0
        if policy == "global-except-poles":
            return -75.0 <= latitude <= 75.0
        if policy == "eu-eea":
            country = str(location.country or "").upper()
            return country in {
                "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
                "DE", "GR", "HU", "IS", "IE", "IT", "LV", "LI", "LT", "LU",
                "MT", "NL", "NO", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
            }
        return True

    def explain_coverage_failure(self, capability_id: str, location: ResolvedLocation) -> str | None:
        if self.is_location_supported(capability_id, location):
            return None
        policy = self.runtime_registry.coverage_policy(capability_id)
        return f"Capability '{capability_id}' is not supported for coverage policy '{policy}' at this location."
