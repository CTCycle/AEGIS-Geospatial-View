from __future__ import annotations

from typing import Any

from AEGIS.server.utils.constants import COMMON_GEOSPATIAL_LAYERS


type JsonDict = dict[str, Any]


CATALOG_PROVIDERS: list[JsonDict] = [
    {"id": "tomtom", "name": "TomTom", "docs_url": "https://developer.tomtom.com/", "commercial_notes": "Commercial use allowed under TomTom terms.", "warning_level": "medium"},
    {"id": "geoapify", "name": "Geoapify", "docs_url": "https://www.geoapify.com/", "commercial_notes": "Free tier supports limited commercial use with attribution.", "warning_level": "medium"},
    {"id": "openaq", "name": "OpenAQ", "docs_url": "https://docs.openaq.org/", "commercial_notes": "Coverage is uneven and source licenses vary by station.", "warning_level": "medium"},
    {"id": "eea", "name": "EEA", "docs_url": "https://www.eea.europa.eu/", "commercial_notes": "EU-focused institutional datasets; service shape may change.", "warning_level": "medium"},
    {"id": "esa", "name": "ESA", "docs_url": "https://services.terrascope.be/", "commercial_notes": "Attribution required for WorldCover services.", "warning_level": "low"},
    {"id": "pvgis", "name": "PVGIS", "docs_url": "https://re.jrc.ec.europa.eu/pvg_tools/en/", "commercial_notes": "PVGIS results are generally reusable; attribution recommended.", "warning_level": "low"},
    {"id": "gibs", "name": "NASA GIBS", "docs_url": "https://earthdata.nasa.gov/eosdis/science-system-description/eosdis-components/gibs", "commercial_notes": "NASA imagery requires attribution and service-aware usage.", "warning_level": "low"},
]


def build_catalog_basemaps(*, tomtom_key: str | None, geoapify_key: str | None) -> list[JsonDict]:
    return [
        {"id": "osm_default", "label": "OpenStreetMap", "provider": "fallback", "type": "tile", "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "attribution": "© OpenStreetMap contributors", "requires_key": False},
        {"id": "tomtom_basic", "label": "TomTom Basic", "provider": "tomtom", "type": "tile", "tile_url": f"https://api.tomtom.com/map/1/tile/basic/main/{{z}}/{{x}}/{{y}}.png?key={tomtom_key}" if tomtom_key else None, "attribution": "© TomTom", "requires_key": True},
        {"id": "geoapify_osm", "label": "Geoapify OSM Bright", "provider": "geoapify", "type": "tile", "tile_url": f"https://maps.geoapify.com/v1/tile/osm-bright/{{z}}/{{x}}/{{y}}.png?apiKey={geoapify_key}" if geoapify_key else None, "attribution": "© OpenMapTiles © OpenStreetMap contributors © Geoapify", "requires_key": True},
    ]


def build_catalog_overlays(*, tomtom_key: str | None) -> list[JsonDict]:
    overlays: list[JsonDict] = [
        {"id": "tomtom_traffic_flow", "label": "TomTom Traffic Flow", "provider": "tomtom", "type": "tile", "default_opacity": 0.7, "coverage": "global", "requires_key": True, "url": f"https://api.tomtom.com/traffic/map/4/tile/flow/absolute/{{z}}/{{x}}/{{y}}.png?key={tomtom_key}" if tomtom_key else None, "attribution": "© TomTom"},
        {"id": "geoapify_amenities", "label": "Geoapify Places (Amenities)", "provider": "geoapify", "type": "geojson", "default_opacity": 0.9, "coverage": "global", "requires_key": True, "attribution": "© Geoapify"},
        {"id": "eea_noise_2019", "label": "EEA Noise Exposure 2019", "provider": "eea", "type": "wms", "default_opacity": 0.55, "coverage": "eu-eea", "requires_key": False, "url": "https://noise.discomap.eea.europa.eu/arcgis/services/noiseStoryMap/noise_exposure_2019/MapServer/WMSServer", "layers": "0", "wms_version": "1.1.1", "wms_exceptions": "application/vnd.ogc.se_inimage", "bounds": [-35.0, 24.0, 45.0, 72.0], "attribution": "© European Environment Agency (CC BY 4.0 where applicable)"},
        {"id": "esa_worldcover", "label": "ESA WorldCover", "provider": "esa", "type": "wmts", "default_opacity": 0.45, "coverage": "global", "requires_key": False, "url": "https://services.terrascope.be/wmts/v2", "layer_id": "WORLDCOVER_2021_MAP", "tile_matrix_set": "EPSG:3857", "wmts_format": "image/png", "wmts_style": "", "attribution": "© ESA WorldCover / Terrascope"},
        {"id": "openaq_air_quality", "label": "OpenAQ Air Quality", "provider": "openaq", "type": "point-insight", "default_opacity": 1.0, "coverage": "global-partial", "requires_key": False, "attribution": "© OpenAQ and source providers"},
        {"id": "pvgis_solar", "label": "PVGIS Solar Potential", "provider": "pvgis", "type": "point-insight", "default_opacity": 1.0, "coverage": "global-except-poles", "requires_key": False, "attribution": "© European Commission JRC PVGIS"},
    ]
    for layer_id, layer_label in COMMON_GEOSPATIAL_LAYERS.items():
        overlays.append({"id": f"GIBS_{layer_id}", "label": layer_label, "provider": "gibs", "type": "legacy-image", "default_opacity": 0.68, "coverage": "global", "requires_key": False, "attribution": "© NASA GIBS"})
    return overlays
