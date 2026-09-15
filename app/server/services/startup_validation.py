from __future__ import annotations

from server.common.typing import is_json_array, is_json_object
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.repositories.credentials import CredentialRepository

###############################################################################
def run_startup_validations(credentials_repo: CredentialRepository) -> None:
    loader = GeospatialManifestLoader()
    catalog_snapshot = GeospatialManifestSnapshot.from_payload(loader.load_all())

    missing_execution_contracts: list[str] = []
    invalid_agent_domains: list[str] = []
    runtime_profiles = {
        str(item.get("capability_id")): item
        for item in catalog_snapshot.runtime_profiles
        if str(item.get("capability_id") or "").strip()
    }
    for collection_name in (
        "basemaps",
        "overlays",
        "cameras",
        "transit",
        "tools",
    ):
        for item in getattr(catalog_snapshot, collection_name):
            capability_id = str(item.get("id") or "").strip()
            agentic_use = item.get("agenticUse")
            if capability_id and is_json_object(agentic_use):
                domains = agentic_use.get("domains")
                if not is_json_array(domains) or not domains:
                    invalid_agent_domains.append(capability_id)
                else:
                    for domain in domains:
                        try:
                            CapabilityDomain(str(domain))
                        except ValueError:
                            invalid_agent_domains.append(capability_id)
                            break
            if (
                capability_id
                and is_json_object(agentic_use)
                and (
                    bool(
                        runtime_profiles.get(capability_id, {}).get(
                            "enabled_by_default"
                        )
                    )
                    or bool(
                        runtime_profiles.get(capability_id, {}).get("manual_toggle")
                    )
                )
                and not is_json_object(item.get("executionContract"))
            ):
                missing_execution_contracts.append(capability_id)
    if missing_execution_contracts:
        raise RuntimeError(
            "Enabled executable capabilities missing execution contracts: "
            + ", ".join(sorted(missing_execution_contracts))
        )
    if invalid_agent_domains:
        raise RuntimeError(
            "Agent-exposed capabilities must declare valid routing domains: "
            + ", ".join(sorted(set(invalid_agent_domains)))
        )
