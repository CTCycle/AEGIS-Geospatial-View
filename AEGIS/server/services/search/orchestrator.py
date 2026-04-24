from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.request import urlopen

from AEGIS.server.domain.geographics import LocationSearchRequest, MapSession
from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry


class LocationSearchOrchestrator:
    def __init__(self, *, capability_registry: CapabilityRegistry | None = None) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()

    async def execute(self, payload: LocationSearchRequest) -> MapSession:
        self.capability_registry.load_capabilities()
        basemap = self._build_basemap_descriptor(payload.basemap_id)
        overlays: list[dict[str, object]] = []
        warnings: list[str] = []
        for overlay_id in payload.overlay_ids:
            overlay_result = self._build_overlay_descriptor(overlay_id)
            if overlay_result is None:
                warnings.append(f"Overlay '{overlay_id}' is not available in the capability catalog.")
                continue
            descriptor, overlay_warnings = overlay_result
            overlays.append(descriptor)
            warnings.extend(overlay_warnings)
        return MapSession(
            session_id=f"map-{int(datetime.now(UTC).timestamp())}",
            resolved_location=payload.resolved_location,
            basemap_id=payload.basemap_id,
            overlay_ids=list(payload.overlay_ids),
            viewport=payload.viewport,
            center={
                "latitude": payload.viewport.center_latitude,
                "longitude": payload.viewport.center_longitude,
            },
            bounds=payload.viewport.bbox,
            basemap=basemap,
            overlays=overlays,
            compliance_warnings=warnings,
            payload={
                "intent_id": payload.intent_id,
                "time_mode": payload.time_mode,
                "presentation": payload.presentation.model_dump(mode="json"),
            },
        )

    def _build_basemap_descriptor(self, basemap_id: str) -> dict[str, object] | None:
        capability = self.capability_registry.get_capability(basemap_id)
        if capability is None:
            return None
        metadata = self._metadata(capability)
        return {
            "id": str(capability.get("id") or basemap_id),
            "label": str(metadata.get("label") or capability.get("name") or basemap_id),
            "provider": str(capability.get("provider") or "unknown"),
            "tile_url": self._optional_string(metadata.get("tile_url")),
            "attribution": str(metadata.get("attribution") or ""),
        }

    def _build_overlay_descriptor(
        self, overlay_id: str
    ) -> tuple[dict[str, object], list[str]] | None:
        capability = self.capability_registry.get_capability(overlay_id)
        if capability is None:
            return None
        metadata = self._metadata(capability)
        warnings: list[str] = []
        resolved_url, url_warning = self._resolve_runtime_tile_url(
            metadata.get("url_template")
            or metadata.get("tile_url")
            or metadata.get("url")
        )
        if url_warning is not None:
            warnings.append(f"{overlay_id}: {url_warning}")
        descriptor: dict[str, object] = {
            "id": str(capability.get("id") or overlay_id),
            "label": str(metadata.get("label") or capability.get("name") or overlay_id),
            "provider": str(capability.get("provider") or "unknown"),
            "type": str(capability.get("type") or "tile"),
        }
        optional_fields = {
            "url": resolved_url,
            "layers": metadata.get("layers"),
            "layer_id": metadata.get("layer_id"),
            "tile_matrix_set": metadata.get("tile_matrix_set"),
            "wmts_format": metadata.get("wmts_format"),
            "wmts_style": metadata.get("wmts_style"),
            "wms_version": metadata.get("wms_version"),
            "wms_exceptions": metadata.get("wms_exceptions"),
            "attribution": metadata.get("attribution"),
        }
        for key, value in optional_fields.items():
            normalized = self._optional_string(value)
            if normalized is not None:
                descriptor[key] = normalized
        if isinstance(metadata.get("default_opacity"), int | float):
            descriptor["default_opacity"] = float(metadata["default_opacity"])
        if descriptor["provider"] == "rainviewer":
            descriptor["maxzoom"] = 10
        if self._is_bounds(metadata.get("bounds")):
            descriptor["bounds"] = list(metadata["bounds"])
        return descriptor, warnings

    @staticmethod
    def _metadata(capability: dict[str, Any]) -> dict[str, Any]:
        metadata = capability.get("metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

    @classmethod
    def _resolve_runtime_tile_url(cls, value: object) -> tuple[str | None, str | None]:
        template = cls._optional_string(value)
        if template is None:
            return None, "Tile URL is missing from provider metadata."
        if "{time}" not in template:
            return template, None
        rainviewer_url = cls._resolve_rainviewer_tile_url()
        if rainviewer_url is not None:
            return rainviewer_url, None
        timestamp = int(datetime.now(UTC).timestamp())
        rounded_timestamp = timestamp - (timestamp % 600)
        return (
            template.replace("{time}", str(rounded_timestamp)),
            "RainViewer metadata could not be fetched; using a timestamp fallback.",
        )

    @staticmethod
    def _resolve_rainviewer_tile_url() -> str | None:
        try:
            with urlopen(  # noqa: S310
                "https://api.rainviewer.com/public/weather-maps.json",
                timeout=2,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None
        radar = payload.get("radar") if isinstance(payload, dict) else None
        past = radar.get("past") if isinstance(radar, dict) else None
        if not isinstance(past, list) or not past:
            return None
        latest = past[-1]
        if not isinstance(latest, dict):
            return None
        path = latest.get("path")
        host = payload.get("host")
        if not isinstance(path, str) or not isinstance(host, str):
            return None
        return f"{host.rstrip('/')}{path}/256/{{z}}/{{x}}/{{y}}/2/1_1.png"

    @staticmethod
    def _is_bounds(value: object) -> bool:
        return (
            isinstance(value, list)
            and len(value) == 4
            and all(isinstance(item, int | float) for item in value)
        )
