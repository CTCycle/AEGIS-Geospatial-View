"""Normalize provider metadata into safe, bounded map inspection contracts."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import urlsplit

from server.contracts.geospatial import (
    InspectionAssociation,
    InspectionField,
    MapInspection,
)


###############################################################################
class MapInspectionService:
    MAX_FIELDS = 14
    MAX_TEXT = 240
    MAX_FEATURES = 100

    _FIELD_LABELS: dict[str, str] = {
        "metric": "Metric",
        "value": "Value",
        "unit": "Unit",
        "units": "Unit",
        "observation_time": "Observed",
        "observationTime": "Observed",
        "forecast_time": "Forecast",
        "forecastTime": "Forecast",
        "time": "Time",
        "freshness": "Freshness",
        "name": "Name",
        "label": "Name",
        "category": "Category",
        "address": "Address",
        "status": "Status",
        "provider": "Provider",
        "event": "Event",
        "severity": "Severity",
        "effective": "Effective",
        "effective_time": "Effective",
        "expiry": "Expires",
        "expiry_time": "Expires",
        "feed": "Feed",
        "feed_id": "Feed",
        "station": "Station",
        "station_id": "Station",
        "camera": "Camera",
        "camera_id": "Camera",
        "period": "Period",
        "geography": "Geography",
        "source": "Source",
        "temperature_2m": "Temperature",
        "precipitation": "Precipitation",
        "weather_code": "Weather code",
        "relative_humidity_2m": "Relative humidity",
        "surface_pressure": "Surface pressure",
        "wind_speed_10m": "Wind speed",
        "wind_direction_10m": "Wind direction",
        "wind_gusts_10m": "Wind gusts",
        "precipitation_probability": "Precipitation probability",
        "pm2_5": "PM2.5",
        "pm10": "PM10",
        "carbon_monoxide": "Carbon monoxide",
        "nitrogen_dioxide": "Nitrogen dioxide",
        "ozone": "Ozone",
        "sulphur_dioxide": "Sulphur dioxide",
        "pressure": "Pressure",
        "humidity": "Humidity",
        "license": "License",
        "fetched_at": "Acquired",
        "resolved_at": "Processed",
        "result_status": "Result status",
        "partial": "Partial data",
        "timezone": "Time zone",
        "latitude": "Latitude",
        "longitude": "Longitude",
        "update_time": "Updated",
        "updated_at": "Updated",
        "updatedAt": "Updated",
    }

    _MEASUREMENT_KEYS = {
        "metric",
        "value",
        "unit",
        "units",
        "observation_time",
        "observationTime",
        "forecast_time",
        "forecastTime",
        "time",
        "freshness",
        "temperature_2m",
        "precipitation",
        "weather_code",
        "relative_humidity_2m",
        "surface_pressure",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "precipitation_probability",
        "pm2_5",
        "pm10",
        "carbon_monoxide",
        "nitrogen_dioxide",
        "ozone",
        "sulphur_dioxide",
        "pressure",
        "humidity",
        "fetched_at",
        "resolved_at",
        "result_status",
        "partial",
        "timezone",
        "latitude",
        "longitude",
    }
    _PLACE_KEYS = {"name", "label", "category", "address", "status", "provider"}
    _HAZARD_KEYS = {
        "event",
        "severity",
        "effective",
        "effective_time",
        "expiry",
        "expiry_time",
    }
    _TRANSIT_KEYS = {
        "feed",
        "feed_id",
        "station",
        "station_id",
        "camera",
        "camera_id",
        "freshness",
        "status",
    }
    _DATASET_KEYS = {
        "metric",
        "period",
        "geography",
        "source",
        "license",
        "update_time",
        "updated_at",
        "updatedAt",
    }
    _URL_KEYS = {
        "source_url",
        "sourceUrl",
        "official_url",
        "officialUrl",
        "dataset_url",
        "datasetUrl",
        "license_url",
        "licenseUrl",
    }

    # -------------------------------------------------------------------------
    @classmethod
    def _bounded_scalar(cls, value: object) -> str | int | float | bool | None:
        if isinstance(value, bool | int | float):
            return value
        if isinstance(value, str):
            text = " ".join(value.split())
            return text[: cls.MAX_TEXT] if text else None
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _safe_url(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return candidate[:500]

    # -------------------------------------------------------------------------
    @classmethod
    def _field_category(cls, key: str) -> str:
        if key in cls._MEASUREMENT_KEYS:
            return "measurement"
        if key in cls._PLACE_KEYS:
            return "place"
        if key in cls._HAZARD_KEYS:
            return "hazard"
        if key in cls._TRANSIT_KEYS:
            return "transit"
        if key in cls._DATASET_KEYS:
            return "dataset"
        return "general"

    # -------------------------------------------------------------------------
    @classmethod
    def _fields(
        cls,
        payload: dict[str, Any],
        *,
        allow_keys: set[str] | None = None,
    ) -> tuple[list[InspectionField], str | None, str | None]:
        fields: list[InspectionField] = []
        source_url: str | None = None
        freshness: str | None = None
        effective_keys = (
            allow_keys if allow_keys is not None else set(cls._FIELD_LABELS)
        )
        flattened = dict(payload)
        nested_metadata = payload.get("metadata")
        if isinstance(nested_metadata, dict):
            for key, raw_value in nested_metadata.items():
                if key in effective_keys and key not in flattened:
                    flattened[key] = raw_value
        for key, raw_value in flattened.items():
            if key in cls._URL_KEYS:
                source_url = source_url or cls._safe_url(raw_value)
        units = flattened.get("units")
        declared_units = units if isinstance(units, dict) else {}
        for key, raw_value in flattened.items():
            if key in cls._URL_KEYS:
                continue
            if key not in effective_keys:
                continue
            value = cls._bounded_scalar(raw_value)
            if value is None:
                continue
            if key.casefold() in {
                "freshness",
                "updated_at",
                "updatedat",
                "update_time",
                "fetched_at",
                "resolved_at",
            }:
                freshness = str(value)
            unit = declared_units.get(key)
            unit_text = unit.strip() if isinstance(unit, str) and unit.strip() else None
            fields.append(
                InspectionField(
                    key=key,
                    label=cls._FIELD_LABELS.get(key, key.replace("_", " ").title()),
                    value=value,
                    unit=unit_text,
                    category=cls._field_category(key),
                    source_url=source_url,
                    order=len(fields),
                )
            )
            if len(fields) >= cls.MAX_FIELDS:
                break
        return fields, source_url, freshness

    # -------------------------------------------------------------------------
    @classmethod
    def _inspection(
        cls,
        *,
        inspection_id: str,
        title: str,
        association: InspectionAssociation,
        provider: str | None,
        feature_id: str | None,
        payload: dict[str, Any],
        geometry: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        stale: bool = False,
        allow_keys: set[str] | None = None,
    ) -> MapInspection | None:
        fields, source_url, freshness = cls._fields(payload, allow_keys=allow_keys)
        if not fields and not warnings:
            return None
        return MapInspection(
            inspection_id=inspection_id,
            title=title[: cls.MAX_TEXT] or "Map item",
            association=association,
            provider=provider,
            feature_id=feature_id,
            fields=fields,
            source_url=source_url,
            freshness=freshness,
            stale=stale,
            warnings=[str(item)[: cls.MAX_TEXT] for item in (warnings or [])[:5]],
            geometry=geometry,
        )

    # -------------------------------------------------------------------------
    @classmethod
    def build_for_descriptor(cls, descriptor: dict[str, Any]) -> list[MapInspection]:
        provider = str(descriptor.get("provider") or "") or None
        overlay_id = str(
            descriptor.get("id") or descriptor.get("layer_id") or "overlay"
        )
        results: list[MapInspection] = []
        data = descriptor.get("data")
        data_object = cast(dict[str, Any], data) if isinstance(data, dict) else None
        if data_object is not None and data_object.get("type") == "FeatureCollection":
            features = data_object.get("features")
            feature_values = (
                cast(list[Any], features) if isinstance(features, list) else []
            )
            for index, raw_feature in enumerate(feature_values):
                feature = (
                    cast(dict[str, Any], raw_feature)
                    if isinstance(raw_feature, dict)
                    else None
                )
                if feature is None:
                    continue
                raw_properties = feature.get("properties")
                properties = (
                    cast(dict[str, Any], raw_properties)
                    if isinstance(raw_properties, dict)
                    else None
                )
                if properties is None:
                    continue
                feature_id = str(feature.get("id") or properties.get("id") or index)
                title = str(
                    properties.get("name")
                    or properties.get("label")
                    or descriptor.get("label")
                    or overlay_id
                )
                inspection = cls._inspection(
                    inspection_id=f"{overlay_id}:feature:{feature_id}",
                    title=title,
                    association="feature",
                    provider=provider,
                    feature_id=feature_id,
                    payload=properties,
                    geometry=(
                        cast(dict[str, Any], feature.get("geometry"))
                        if isinstance(feature.get("geometry"), dict)
                        else None
                    ),
                    stale=bool(descriptor.get("stale")),
                )
                if inspection is not None:
                    results.append(inspection)
                if len(results) >= cls.MAX_FEATURES:
                    break

        metadata = descriptor.get("inspection_metadata") or descriptor.get("metadata")
        if isinstance(metadata, dict):
            metadata = cast(dict[str, Any], metadata)
            latitude = metadata.get("latitude")
            longitude = metadata.get("longitude")
            latitude_number = (
                float(latitude) if isinstance(latitude, (int, float)) else None
            )
            longitude_number = (
                float(longitude) if isinstance(longitude, (int, float)) else None
            )
            spatial = latitude_number is not None and longitude_number is not None
            association: InspectionAssociation = (
                "location" if spatial else "non_spatial"
            )
            geometry = (
                {"type": "Point", "coordinates": [longitude_number, latitude_number]}
                if spatial
                else None
            )
            inspection = cls._inspection(
                inspection_id=f"{overlay_id}:metadata",
                title=str(
                    metadata.get("name") or descriptor.get("label") or overlay_id
                ),
                association=association,
                provider=provider,
                feature_id=None,
                payload=metadata,
                geometry=geometry,
                warnings=[
                    str(item)
                    for item in descriptor.get("warnings", [])
                    if isinstance(item, str)
                ],
                stale=bool(descriptor.get("stale")),
            )
            if inspection is not None:
                results.append(inspection)

        rendering_mode = str(descriptor.get("rendering_mode") or "").casefold()
        if rendering_mode in {
            "raster-tile",
            "xyz",
            "wmts",
            "wms",
            "raster-overlay",
            "choropleth",
        }:
            raster_payload = {
                key: descriptor.get(key)
                for key in (
                    "time",
                    "default_time",
                    "format",
                    "units",
                    "legend",
                    "attribution",
                    "freshness",
                    "source_url",
                    "official_url",
                )
                if descriptor.get(key) is not None
            }
            raster = cls._inspection(
                inspection_id=f"{overlay_id}:overlay",
                title=str(descriptor.get("label") or overlay_id),
                association="overlay",
                provider=provider,
                feature_id=None,
                payload=raster_payload,
                warnings=[
                    str(item)
                    for item in descriptor.get("warnings", [])
                    if isinstance(item, str)
                ],
                stale=bool(descriptor.get("stale")),
                allow_keys=cls._MEASUREMENT_KEYS
                | cls._DATASET_KEYS
                | {"format", "attribution", "legend", "default_time"},
            )
            if raster is not None:
                results.append(raster)
        return results

    # -------------------------------------------------------------------------
    @classmethod
    def attach_to_descriptor(cls, descriptor: dict[str, Any]) -> dict[str, Any]:
        inspections = cls.build_for_descriptor(descriptor)
        if not inspections:
            return descriptor
        descriptor = dict(descriptor)
        descriptor["inspections"] = [
            item.model_dump(mode="json") for item in inspections
        ]
        return descriptor
