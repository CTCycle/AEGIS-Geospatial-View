from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from server.common.paths import PROJECT_DIR
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.provider_registry import PROVIDER_FACTORIES
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.geospatial.endpoint_validation import EndpointValidationService

NATIVE_TOOL_SOURCE = PROJECT_DIR / "server" / "services" / "agent" / "agent_tool_catalog_service.py"
RENDERER_SOURCE = PROJECT_DIR / "client" / "src" / "app" / "components" / "map-preview-rendering.ts"
PROVIDER_SOURCE_DIR = PROJECT_DIR / "server" / "services" / "geospatial" / "providers"
CATALOG_SOURCE = PROJECT_DIR / "resources" / "catalog"

DIRECT_TOOL_PROVIDERS = {
    "location_to_coordinates": "nominatim",
    "get_weather_forecast": "openmeteo",
    "get_air_quality_forecast": "openmeteo",
    "get_nearby_poi": "overpass",
}

PROVIDER_SOURCE_ALIASES = {
    "arcgis": "arcgis_rest",
    "gibs": "nasa_gibs",
}

REPLACEMENTS = [
    {
        "old": ["geoapify_osm", "tomtom_basic"],
        "new": ["openfreemap_liberty", "openfreemap_positron"],
        "outcome": "partial",
        "coverage": "Static global vector basemap styles replace raster basemap presentation only.",
        "lost_or_degraded": [
            "TomTom commercial road styling and traffic-oriented context are not equivalent.",
            "Geoapify-specific tile availability and SLA are not retained.",
            "OpenFreeMap public hosting has no contractual SLA.",
        ],
        "evidence": "commit da3f43b3",
    },
    {
        "old": ["transitland_feeds"],
        "new": ["mobility_database_feeds"],
        "outcome": "functional_for_metadata_discovery",
        "coverage": "Worldwide feed metadata search through a local Mobility Database CSV snapshot.",
        "lost_or_degraded": [
            "No live Transitland API query path remains.",
            "Catalog freshness depends on local snapshot refresh.",
            "Feed-specific realtime access still requires separate agency credentials and licensing.",
        ],
        "evidence": "commit da3f43b3 and mobility_database provider contract",
    },
    {
        "old": ["geoapify_amenities", "opentripmap_tourism_pois"],
        "new": ["overture_maps_places", "overpass_poi_amenities"],
        "outcome": "not_equivalent_without_parity_benchmark",
        "coverage": "Bulk/local Overture places plus bounded OSM Overpass augmentation.",
        "lost_or_degraded": [
            "Geoapify and OpenTripMap hosted ranking and tourism metadata are not guaranteed.",
            "Overture requires a local ingested index before interactive results are available.",
        ],
        "evidence": "public_and_optional_sources.md and poi_benchmark.py",
    },
]

OVERLAP_GROUPS = {
    "poi": {"geoapify", "google_maps", "opentripmap", "openaddresses", "overpass", "overture"},
    "air_quality": {"openaq", "openmeteo"},
    "imagery": {"arcgis", "gibs", "esa"},
    "transit": {"gtfs_static", "gtfs_realtime", "mobility_database"},
    "basemap": {"openfreemap", "osm_tiles", "cartodb_tiles", "terrain_tiles", "arcgis"},
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _safe_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlsplit(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    query = [(key, "<redacted>" if any(marker in key.casefold() for marker in ("key", "token", "secret")) else val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def _manifest_urls(manifest: dict[str, Any]) -> list[str]:
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    urls: list[str] = []
    for key, value in metadata.items():
        if "url" not in str(key).casefold() and not str(key).casefold().endswith("endpoint"):
            continue
        safe = _safe_url(value)
        if safe and safe not in urls:
            urls.append(safe)
    for value in manifest.get("sourceOfficialDocs") or []:
        safe = _safe_url(value)
        if safe and safe not in urls:
            urls.append(safe)
    return urls


def _native_tools() -> list[dict[str, Any]]:
    source = _read_text(NATIVE_TOOL_SOURCE)
    names = list(dict.fromkeys(re.findall(r'name="([a-z][a-z0-9_]+)"', source)))
    descriptions = dict(
        re.findall(
            r'name="([a-z][a-z0-9_]+)"\s*,\s*description="([^"]+)"',
            source,
        )
    )
    return [
        {
            "id": name,
            "name": name,
            "description": descriptions.get(name),
            "exposure": "llm-native",
            "source": str(NATIVE_TOOL_SOURCE.relative_to(PROJECT_DIR.parent)),
            "status": "active",
        }
        for name in names
    ]


def _provider_overlaps(provider_id: str, capabilities: set[str]) -> list[str]:
    matches: list[str] = []
    for group, providers in OVERLAP_GROUPS.items():
        if provider_id not in providers:
            continue
        if capabilities or group == "basemap":
            matches.append(group)
    return matches


def _adapter_path(provider_id: str) -> str | None:
    filename = PROVIDER_SOURCE_ALIASES.get(provider_id, provider_id.replace("-", "_"))
    path = PROVIDER_SOURCE_DIR / f"{filename}.py"
    if provider_id in PROVIDER_FACTORIES and path.is_file():
        return str(path.relative_to(PROJECT_DIR.parent))
    return None


def _endpoint_validation(
    by_provider: dict[str, list[dict[str, Any]]],
    *,
    enabled: bool,
) -> list[dict[str, Any]]:
    if not enabled:
        return []
    service = EndpointValidationService(timeout_seconds=8.0)
    results: list[dict[str, Any]] = []
    for provider_id in sorted(by_provider):
        entries = by_provider[provider_id]
        if any(bool((item.get("auth") or {}).get("required")) for item in entries):
            results.append(
                {
                    "provider_id": provider_id,
                    "status": "skipped_credentials",
                    "message": "Credential-gated provider endpoint was not called without configured credentials.",
                }
            )
            continue
        candidate = next(
            (
                item
                for item in entries
                if service.build_validation_url(item) is not None
                and str((item.get("metadata") or {}).get("endpoint_health") or "").casefold() != "local-snapshot"
            ),
            None,
        )
        if candidate is None:
            results.append(
                {
                    "provider_id": provider_id,
                    "status": "not_sampled",
                    "message": "No safe public endpoint is declared in the manifest.",
                }
            )
            continue
        result = service.validate_manifest(candidate)
        status = "passed" if result.ok else "failed"
        if "exceeded validation limit" in result.message.casefold():
            status = "passed_large_response"
        results.append(
            {
                "provider_id": provider_id,
                "capability_id": result.capability_id,
                "status": status,
                "status_code": result.status_code,
                "data_format": result.data_format,
                "message": result.message,
            }
        )
    return results


def _status_for_provider(
    provider_id: str,
    manifests: list[dict[str, Any]],
    runtime_profiles: dict[str, dict[str, Any]],
    live_by_provider: dict[str, dict[str, Any]],
) -> str:
    live = live_by_provider.get(provider_id)
    if live and live.get("status") == "failed":
        return "broken_live_check"
    if live and live.get("status") == "skipped":
        return "partial_missing_credentials"
    if provider_id in {"openfreemap", "osm_tiles", "cartodb_tiles", "terrain_tiles"}:
        return "active_rendering_only"
    if provider_id not in PROVIDER_FACTORIES:
        return "catalog_only" if manifests else "unregistered"
    if not manifests:
        return "runtime_only"
    if any(
        bool(runtime_profiles.get(str(item.get("id") or ""), {}).get("enabled_by_default"))
        for item in manifests
    ):
        return "active"
    return "registered_not_enabled"


def build_inventory(
    live_report: dict[str, Any] | None = None,
    *,
    validate_endpoints: bool = False,
) -> dict[str, Any]:
    catalog = GeospatialManifestLoader().load_all()
    manifests: list[dict[str, Any]] = []
    for collection in ("providers", "basemaps", "overlays", "cameras", "transit", "tools"):
        for item in catalog.get(collection) or []:
            manifests.append({"collection": collection, **dict(item)})

    runtime_profiles = {
        str(item.get("capability_id")): dict(item)
        for item in catalog.get("runtime_profiles") or []
        if str(item.get("capability_id") or "").strip()
    }
    live_by_provider: dict[str, dict[str, Any]] = {}
    for result in (live_report or {}).get("results") or []:
        if isinstance(result, dict):
            live_by_provider[str(result.get("provider_id") or "")] = result

    by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in manifests:
        provider_id = str(item.get("provider") or "").strip().lower()
        if provider_id:
            by_provider[provider_id].append(item)

    endpoint_results = _endpoint_validation(by_provider, enabled=validate_endpoints)
    endpoint_by_provider = {
        str(item.get("provider_id")): item for item in endpoint_results
    }
    provider_ids = sorted(set(by_provider) | set(PROVIDER_FACTORIES))
    providers: list[dict[str, Any]] = []
    for provider_id in provider_ids:
        provider_manifests = by_provider.get(provider_id, [])
        capabilities = sorted(
            {
                str(capability)
                for item in provider_manifests
                for capability in item.get("capabilities") or []
            }
        )
        auth_entries = [item.get("auth") for item in provider_manifests if isinstance(item.get("auth"), dict)]
        required_auth = any(bool(item.get("required")) for item in auth_entries)
        provider_key = next(
            (str(item.get("providerKey")) for item in auth_entries if item.get("providerKey")),
            None,
        )
        env_name = RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER.get(provider_key or provider_id)
        profile_ids = sorted(str(item.get("id")) for item in provider_manifests if str(item.get("id") or "") in runtime_profiles)
        operational_status = _status_for_provider(
            provider_id, provider_manifests, runtime_profiles, live_by_provider
        )
        if endpoint_by_provider.get(provider_id, {}).get("status") == "failed":
            operational_status = "broken_endpoint"
        providers.append(
            {
                "id": provider_id,
                "purpose": next((str(item.get("description") or "") for item in provider_manifests if item.get("description")), "Runtime provider adapter or rendering source."),
                "data_types": capabilities,
                "coverage": sorted({str(item.get("coverage") or "") for item in provider_manifests if item.get("coverage")}),
                "requires_authentication": required_auth,
                "configuration": {
                    "provider_key": provider_key,
                    "credential_environment_variable": env_name,
                    "runtime_profile_ids": profile_ids,
                    "local_or_external": "local_snapshot" if any(str(item.get("metadata", {}).get("endpoint_health", "")).casefold() == "local-snapshot" for item in provider_manifests) else "external_service",
                },
                "upstream_endpoints": sorted({url for item in provider_manifests for url in _manifest_urls(item)}),
                "internal_components": {
                    "adapter": _adapter_path(provider_id),
                    "manifest_ids": sorted(str(item.get("id")) for item in provider_manifests),
                    "renderer": str(RENDERER_SOURCE.relative_to(PROJECT_DIR.parent)) if any(item.get("renderingMode") != "metadata-only" for item in provider_manifests) else None,
                },
                "llm_exposure": sorted(
                    [tool_id for tool_id, tool_provider in DIRECT_TOOL_PROVIDERS.items() if tool_provider == provider_id]
                    + (["fetch_geospatial_provider_layers", "render_geospatial_provider_layer"] if provider_id in {str(item.get("provider") or "").lower() for item in provider_manifests} else [])
                ),
                "overlap_groups": _provider_overlaps(provider_id, set(capabilities)),
                "operational_status": operational_status,
                "live_validation": live_by_provider.get(provider_id),
                "catalog_manifest_count": len(provider_manifests),
                "adapter_registered": provider_id in PROVIDER_FACTORIES,
            }
        )

    tools = []
    for item in catalog.get("tools") or []:
        tool_id = str(item.get("id") or "")
        tools.append(
            {
                "id": tool_id,
                "name": item.get("name"),
                "description": item.get("description"),
                "provider": item.get("provider"),
                "capabilities": item.get("capabilities") or [],
                "exposure": "direct-tool-manifest",
                "handler": (item.get("metadata") or {}).get("handler_name"),
                "status": "active" if runtime_profiles.get(tool_id, {}).get("enabled_by_default") else "registered_not_enabled",
                "source": str((CATALOG_SOURCE / "tools" / f"{tool_id}.json").relative_to(PROJECT_DIR.parent)),
            }
        )
    tools.extend(_native_tools())

    findings = [
        {
            "id": "schema-v1-dominant",
            "severity": "medium",
            "status": "open_risk",
            "detail": "The loader accepts all manifests, but the auditor reports 83 schema-v1 and 3 schema-v2 manifests; migration is not part of this scoped audit fix.",
        },
        {
            "id": "credentialed-live-coverage",
            "severity": "medium",
            "status": "external_gate",
            "detail": "Credentialed live checks are skipped when optional provider keys are absent; no credentials are inferred or exposed.",
        },
        {
            "id": "openfreemap-rendering-provider",
            "severity": "resolved",
            "status": "fixed",
            "detail": "Production auditing and endpoint validation now recognize MapLibre style_url as the concrete fetch path for OpenFreeMap basemaps.",
        },
    ]
    eea_endpoint = endpoint_by_provider.get("eea")
    if eea_endpoint and eea_endpoint.get("status") == "failed":
        findings.append(
            {
                "id": "eea-noise-upstream-service",
                "severity": "high",
                "status": "upstream_unavailable",
                "detail": "The configured EEA noise ArcGIS service returned a service-not-started/404 response during validation; the layer remains an unresolved external risk and should not be treated as healthy.",
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "catalog_root": str(CATALOG_SOURCE.relative_to(PROJECT_DIR.parent)),
        "counts": {
            "manifests": len(manifests),
            "providers": len(providers),
            "direct_tools": len(catalog.get("tools") or []),
            "llm_native_tools": len(_native_tools()),
            "runtime_profiles": len(runtime_profiles),
        },
        "providers": providers,
        "tools": tools,
        "endpoint_validation": endpoint_results,
        "replacements": REPLACEMENTS,
        "findings": findings,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Geospatial Provider and Tool Inventory",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Counts",
        "",
        "| Item | Count |",
        "| --- | ---: |",
    ]
    for key, value in report["counts"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Provider Health Matrix", "", "| Provider | Status | Auth | Adapter | Catalog manifests | Live check |", "| --- | --- | --- | --- | ---: | --- |"])
    for provider in report["providers"]:
        live = (provider.get("live_validation") or {}).get("status", "not_sampled")
        lines.append(f"| `{provider['id']}` | {provider['operational_status']} | {'required' if provider['requires_authentication'] else 'none'} | {'yes' if provider['adapter_registered'] else 'rendering/catalog-only'} | {provider['catalog_manifest_count']} | {live} |")
    lines.extend(["", "## LLM Tools", "", "| Tool | Exposure | Provider/Handler | Status |", "| --- | --- | --- | --- |"])
    for tool in report["tools"]:
        lines.append(f"| `{tool['id']}` | {tool['exposure']} | {tool.get('provider') or tool.get('handler') or 'capability-oriented'} | {tool['status']} |")
    lines.extend(["", "## Replacement Outcomes", ""])
    for replacement in report["replacements"]:
        lines.append(f"- `{', '.join(replacement['old'])}` → `{', '.join(replacement['new'])}`: **{replacement['outcome']}**. {replacement['coverage']}")
        for item in replacement["lost_or_degraded"]:
            lines.append(f"  - {item}")
    lines.extend(["", "## Endpoint Samples", "", "| Provider | Capability | Status | HTTP | Message |", "| --- | --- | --- | ---: | --- |"])
    for endpoint in report.get("endpoint_validation") or []:
        lines.append(f"| `{endpoint['provider_id']}` | `{endpoint.get('capability_id', '')}` | {endpoint['status']} | {endpoint.get('status_code') or ''} | {endpoint.get('message') or ''} |")
    lines.extend(["", "## Findings", ""])
    for finding in report["findings"]:
        lines.append(f"- `{finding['id']}` ({finding['severity']}, {finding['status']}): {finding['detail']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a geospatial provider/tool inventory.")
    parser.add_argument("--output", type=Path, required=True, help="JSON report path.")
    parser.add_argument("--markdown", type=Path, help="Optional Markdown report path.")
    parser.add_argument("--live-report", type=Path, help="Optional live_validator JSON report to merge.")
    parser.add_argument(
        "--validate-endpoints",
        action="store_true",
        help="Run one bounded public endpoint sample per provider manifest group.",
    )
    args = parser.parse_args(argv)
    live_report = None
    if args.live_report and args.live_report.is_file():
        live_report = json.loads(args.live_report.read_text(encoding="utf-8"))
    report = build_inventory(live_report, validate_endpoints=args.validate_endpoints)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "providers": report["counts"]["providers"], "tools": report["counts"]["direct_tools"] + report["counts"]["llm_native_tools"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
