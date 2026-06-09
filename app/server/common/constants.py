from __future__ import annotations

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
NOMINATIM_SEARCH_PATH = "/search"
NOMINATIM_REVERSE_PATH = "/reverse"
NOMINATIM_SEARCH_URL = f"{NOMINATIM_BASE_URL}{NOMINATIM_SEARCH_PATH}"
NOMINATIM_REVERSE_URL = f"{NOMINATIM_BASE_URL}{NOMINATIM_REVERSE_PATH}"
OPENAQ_API_BASE_URL = "https://api.openaq.org/v3"
OPEN_ELEVATION_API_BASE_URL = "https://api.open-elevation.com/api/v1"
OLLAMA_DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL_PROVIDER_MODE = "local"
DEFAULT_MODEL_PROVIDER = "ollama"
DEFAULT_MODEL_NAME = "llama3.2"

GIBS_WMS_BASE_ENDPOINTS = {
    "EPSG:3857": "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
    "EPSG:4326": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
}
GIBS_CAPABILITIES_ENDPOINTS = {
    "EPSG:4326": "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml",
    "EPSG:3857": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml",
    "EPSG:3413": "https://gibs.earthdata.nasa.gov/wmts/epsg3413/best/1.0.0/WMTSCapabilities.xml",
    "EPSG:3031": "https://gibs.earthdata.nasa.gov/wmts/epsg3031/best/1.0.0/WMTSCapabilities.xml",
}
GIBS_OWS_NAMESPACES = {"ows": "http://www.opengis.net/ows/1.1"}

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

CHAT_SESSIONS_TABLE = "chat_sessions"
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

MAP_SEARCH_STATUS_MESSAGE = "Map search request submitted."
MAP_SEARCH_JOB_START_MESSAGE = "Map search job started"
MAP_SEARCH_JOB_INIT_ERROR = "Failed to initialize map search job"
MAP_SEARCH_CANCELLATION_REQUESTED = "Cancellation requested"
MAP_SEARCH_CANCELLATION_NOT_ALLOWED = "Job cannot be cancelled"

MAP_SEARCH_JOB_PROGRESS_COORDINATES = 8.0
MAP_SEARCH_JOB_PROGRESS_IMAGERY = 35.0
MAP_SEARCH_JOB_PROGRESS_POSTPROCESS = 70.0
MAP_SEARCH_JOB_PROGRESS_PERSISTED = 92.0

DEFAULT_DB_CONNECT_TIMEOUT = 10
DEFAULT_DB_INSERT_BATCH_SIZE = 1000
DEFAULT_NOMINATIM_USER_AGENT = "AEGIS-Geographics/1.0 (contact: support@aegis.local)"
DEFAULT_GIBS_USER_AGENT = "AEGIS-GIBS/1.0"
DEFAULT_GIBS_LAYER_SYNC_USER_AGENT = "AEGIS-GIBS-LayerSync/1.0"
DEFAULT_GIBS_DEFAULT_LAYER = "VIIRS_SNPP_CorrectedReflectance_TrueColor"
