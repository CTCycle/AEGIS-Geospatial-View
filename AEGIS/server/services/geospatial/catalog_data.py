from __future__ import annotations

from typing import Any

from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader

type JsonDict = dict[str, Any]

_loader = GeospatialManifestLoader()


def _providers_payload() -> list[JsonDict]:
    providers = _loader.load_all()["providers"]
    mapped: list[JsonDict] = []
    for entry in providers:
        metadata = dict(entry.get("metadata") or {})
        mapped.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "docs_url": metadata.get("docs_url", ""),
                "commercial_notes": metadata.get("commercial_notes", ""),
                "warning_level": metadata.get("warning_level", "low"),
            }
        )
    return mapped


CATALOG_PROVIDERS: list[JsonDict] = _providers_payload()


def build_catalog_basemaps(
    *, tomtom_key: str | None, geoapify_key: str | None
) -> list[JsonDict]:
    basemaps = _loader.load_all()["basemaps"]
    mapped: list[JsonDict] = []
    for entry in basemaps:
        metadata = dict(entry.get("metadata") or {})
        tile_url = metadata.get("tile_url")
        tile_url_template = metadata.get("tile_url_template")
        provider = str(entry.get("provider") or "")
        if not tile_url and isinstance(tile_url_template, str):
            if provider == "tomtom":
                tile_url = tile_url_template.replace("{api_key}", tomtom_key) if tomtom_key else None
            elif provider == "geoapify":
                tile_url = tile_url_template.replace("{api_key}", geoapify_key) if geoapify_key else None
        mapped.append(
            {
                "id": entry["id"],
                "label": metadata.get("label", entry["name"]),
                "provider": entry["provider"],
                "type": entry["type"],
                "tile_url": tile_url,
                "attribution": metadata.get("attribution"),
                "requires_key": bool(metadata.get("requires_key", False)),
            }
        )
    return mapped


def build_catalog_overlays(*, tomtom_key: str | None) -> list[JsonDict]:
    overlays = _loader.load_all()["overlays"]
    mapped: list[JsonDict] = []
    for entry in overlays:
        metadata = dict(entry.get("metadata") or {})
        overlay = {
            "id": entry["id"],
            "label": metadata.get("label", entry["name"]),
            "provider": entry["provider"],
            "type": entry["type"],
            "default_opacity": metadata.get("default_opacity", 0.65),
            "coverage": entry.get("coverage"),
            "requires_key": bool(metadata.get("requires_key", False)),
            "url": metadata.get("url"),
            "layers": metadata.get("layers"),
            "layer_id": metadata.get("layer_id"),
            "tile_matrix_set": metadata.get("tile_matrix_set"),
            "wmts_format": metadata.get("wmts_format"),
            "wmts_style": metadata.get("wmts_style"),
            "wms_version": metadata.get("wms_version"),
            "wms_exceptions": metadata.get("wms_exceptions"),
            "bounds": metadata.get("bounds"),
            "attribution": metadata.get("attribution"),
        }
        url_template = metadata.get("url_template")
        if isinstance(url_template, str) and entry.get("provider") == "tomtom":
            overlay["url"] = url_template.replace("{api_key}", tomtom_key) if tomtom_key else None
        mapped.append(overlay)
    return mapped
