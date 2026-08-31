from __future__ import annotations

NOMINATIM_SEARCH_PATH = "/search"
NOMINATIM_REVERSE_PATH = "/reverse"
OPENAQ_API_BASE_URL = "https://api.openaq.org/v3"
OPEN_ELEVATION_API_BASE_URL = "https://api.open-elevation.com/api/v1"
OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL_PROVIDER_MODE = "cloud"
DEFAULT_MODEL_PROVIDER = ""
DEFAULT_MODEL_NAME = ""
AEGIS_VERSION = "1.0.0"


NASA_ATTRIBUTION = (
    "Imagery courtesy of NASA's Global Imagery Browse Services (GIBS), "
    "operated by the NASA/GSFC Earth Science Data and Information System "
    "(ESDIS) project."
)

COMMON_FOLIUM_MAPS = {
    "OpenStreetMap": "Street Map",
    "CartoDB Positron": "Cartographic Light",
    "CartoDB Dark_Matter": "Cartographic Dark",
    "Esri WorldImagery": "Esri World Imagery",
    "OpenTopoMap": "Topographic Relief",
    "Esri NatGeoWorldMap": "National Geographic",
    "Esri OceanBasemap": "Ocean Basemap",
}

REFERENCE_COUNTRIES_TABLE_NAME = "reference_countries"
REFERENCE_COUNTRY_ALIASES_TABLE_NAME = "reference_country_aliases"
REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME = "reference_geospatial_layers"
REFERENCE_GEOSPATIAL_LAYER_ALIASES_TABLE_NAME = "reference_geospatial_layer_aliases"
REFERENCE_GEOSPATIAL_LAYER_KEYWORDS_TABLE_NAME = "reference_geospatial_layer_keywords"
REFERENCE_GIBS_TILE_MATRIX_SETS_TABLE_NAME = "reference_gibs_tile_matrix_sets"
REFERENCE_GIBS_LAYER_DEFAULTS_TABLE_NAME = "reference_gibs_layer_defaults"

ORIGIN_SHIFT = 20037508.342789244
MAX_WEB_MERCATOR = 20037508.342789244
MAX_MERCATOR_LAT = 85.05112878
MIN_MERCATOR_LAT = -85.05112878
MAX_GEO_LAT = 90.0
MIN_GEO_LAT = -90.0
MAX_LONGITUDE = 180.0
MIN_LONGITUDE = -180.0
EARTH_RADIUS_M = 6_378_137.0
CAPABILITIES_QUERY = {"SERVICE": "WMS", "REQUEST": "GetCapabilities"}
GIBS_MIN_IMAGE_DIMENSION = 512
GIBS_MAX_IMAGE_DIMENSION = 2048

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"


DEFAULT_SQLITE_LOCK_TIMEOUT_SECONDS = 60
