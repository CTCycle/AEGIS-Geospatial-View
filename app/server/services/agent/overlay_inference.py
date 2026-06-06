from __future__ import annotations

from dataclasses import dataclass

from server.domain.extraction.models import TurnParseResult
from server.domain.agent.decision import ResolvedLocation
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


@dataclass(frozen=True)
class OverlayInferenceResult:
    overlay_ids: list[str]
    warnings: list[str]
    reasons: dict[str, list[str]]


class OverlayInferenceService:
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.runtime_registry = runtime_registry or RuntimeRegistry()

    def infer_overlays(
        self,
        *,
        turn_contract: TurnParseResult,
        location: ResolvedLocation | None,
        existing_overlay_ids: list[str],
    ) -> OverlayInferenceResult:
        _ = location
        snapshot = self.capability_registry.load_capabilities()
        candidates = [
            *snapshot.overlays,
            *snapshot.cameras,
            *snapshot.transit,
            *snapshot.tools,
        ]
        text_parts = [
            turn_contract.user_text,
            turn_contract.normalized_action.action_id,
            *turn_contract.normalized_action.task_tags,
            *turn_contract.normalized_action.action_tags,
        ]
        haystack = " ".join(part.strip().lower() for part in text_parts if isinstance(part, str))
        explicit_ids = list(existing_overlay_ids)
        explicit_haystack = " ".join(item.strip().lower() for item in explicit_ids)
        chosen: list[str] = []
        reasons: dict[str, list[str]] = {}
        warnings: list[str] = []

        mappings = [
            (
                ("traffic", "congestion", "incidents"),
                ("tomtom_traffic_flow", "tomtom_traffic_incidents"),
                "Matched traffic intent from request text or action metadata.",
            ),
            (
                ("precipitation", "rain", "radar", "storm"),
                ("rainviewer_precipitation_radar", "noaa_radar", "openmeteo_weather_forecast"),
                "Matched precipitation or radar intent from request text or action metadata.",
            ),
            (
                ("air quality", "pollution", "pm2.5", "pm10", "aqi"),
                ("openaq_air_quality", "openmeteo_air_quality_forecast"),
                "Matched air-quality intent from request text or action metadata.",
            ),
            (
                ("satellite", "imagery", "true color"),
                ("VIIRS_SNPP_CorrectedReflectance_TrueColor",),
                "Matched satellite or imagery intent from request text or action metadata.",
            ),
            (
                ("terrain", "elevation", "topography"),
                ("SRTM_Color_Index",),
                "Matched terrain or elevation intent from request text or action metadata.",
            ),
            (
                ("webcam", "webcams", "camera", "cameras"),
                ("windy_webcams",),
                "Matched webcam or camera intent from request text or action metadata.",
            ),
            (
                ("poi", "amenities", "nearby", "places"),
                ("overpass_poi_amenities", "overture_maps_places"),
                "Matched POI or nearby-place intent from request text or action metadata.",
            ),
            (
                ("solar", "photovoltaic", "pv"),
                ("pvgis_solar",),
                "Matched solar intent from request text or action metadata.",
            ),
            (
                ("weather", "forecast", "temperature"),
                ("openmeteo_weather_forecast", "rainviewer_precipitation_radar"),
                "Matched weather intent from request text or action metadata.",
            ),
        ]

        for triggers, preferred_ids, reason in mappings:
            if not any(trigger in haystack for trigger in triggers):
                continue
            normalized_triggers = tuple(trigger.replace(" ", "") for trigger in triggers)
            if any(trigger in explicit_haystack.replace(" ", "") for trigger in normalized_triggers):
                continue
            for capability_id in preferred_ids:
                if capability_id in explicit_ids or capability_id in chosen:
                    continue
                manifest = next(
                    (item for item in candidates if str(item.get("id") or "") == capability_id),
                    None,
                )
                if manifest is None:
                    continue
                if not self.runtime_registry.supports_mode(capability_id, "map"):
                    continue
                chosen.append(capability_id)
                reasons[capability_id] = [reason]
                health = self.runtime_registry.provider_health(capability_id)
                if health not in {"healthy", "missing_credentials"}:
                    warnings.append(
                        f"{capability_id}: inferred from request intent but runtime health is {health}."
                    )
                break

        return OverlayInferenceResult(
            overlay_ids=chosen,
            warnings=warnings,
            reasons=reasons,
        )
