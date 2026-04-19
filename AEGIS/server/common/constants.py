from __future__ import annotations

from os.path import abspath, join

# [PATHS]
###############################################################################
ROOT_DIR = abspath(join(__file__, "../../../.."))
PROJECT_DIR = join(ROOT_DIR, "AEGIS")
SETTING_PATH = join(PROJECT_DIR, "settings")
RESOURCES_PATH = join(PROJECT_DIR, "resources")
MODELS_PATH = join(RESOURCES_PATH, "models")
SOURCES_PATH = join(RESOURCES_PATH, "sources")
LOGS_PATH = join(RESOURCES_PATH, "logs")
ENV_FILE_PATH = join(SETTING_PATH, ".env")
DATABASE_FILENAME = "database.db"

###############################################################################
CONFIGURATIONS_FILE = join(SETTING_PATH, "configurations.json")


# [BACKEND ROUTES]
###############################################################################
ROOT_ROUTE = "/"
DOCS_ROUTE = "/docs"
FASTAPI_TITLE = "AEGIS Geospatial Search Backend"
FASTAPI_DESCRIPTION = "FastAPI backend"
FASTAPI_VERSION = "1.0.0"
MAPS_ROUTER_PREFIX = "/maps"
MAPS_SEARCH_ROUTE = "/search"
MAPS_CATALOG_ROUTE = "/catalog"
MAPS_OSM_BASEMAP_TILE_ROUTE = "/basemaps/osm/{z}/{x}/{y}.png"
MAPS_JOBS_ROUTE = "/jobs"
MAPS_JOB_ROUTE = "/jobs/{job_id}"
GEO_SEARCH_URL = f"{MAPS_ROUTER_PREFIX}{MAPS_SEARCH_ROUTE}"
CHAT_ROUTER_PREFIX = "/chat"
CHAT_TURN_ROUTE = "/turn"
CHAT_STREAM_ROUTE = "/stream"
CHAT_MODELS_ROUTE = "/models"
CHAT_SETTINGS_ROUTE = "/settings"
CHAT_OLLAMA_REFRESH_ROUTE = "/models/ollama/refresh"
CHAT_OLLAMA_PULL_ROUTE = "/models/ollama/pull"
CHAT_VECTORS_REBUILD_ROUTE = "/vectors/rebuild"
CHAT_VECTORS_SYNC_ROUTE = "/vectors/sync"
CHAT_OLLAMA_HEALTH_ROUTE = "/models/ollama/health"

# [SERVER URLS]
###############################################################################
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
NOMINATIM_SEARCH_PATH = "/search"
NOMINATIM_REVERSE_PATH = "/reverse"
NOMINATIM_SEARCH_URL = f"{NOMINATIM_BASE_URL}{NOMINATIM_SEARCH_PATH}"
NOMINATIM_REVERSE_URL = f"{NOMINATIM_BASE_URL}{NOMINATIM_REVERSE_PATH}"
OPENAQ_API_BASE_URL = "https://api.openaq.org/v3"
OPEN_ELEVATION_API_BASE_URL = "https://api.open-elevation.com/api/v1"
OLLAMA_DEFAULT_HOST = "http://localhost:11434"

# [GIBS SERVICE URLS]
###############################################################################
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

# [EXTERNAL DATA SOURCES]
###############################################################################
NASA_ATTRIBUTION = (
    "Imagery courtesy of NASA's Global Imagery Browse Services (GIBS), "
    "operated by the NASA/GSFC Earth Science Data and Information System "
    "(ESDIS) project."
)

# Daily/NRT GIBS layers (updated frequently)
GIBS_NRT_LAYERS = {
    "VIIRS_SNPP_CorrectedReflectance_TrueColor": "True Color Satellite (VIIRS, Daily)",
    "MODIS_Terra_Aerosol": "Aerosol Optical Depth (MODIS, Daily)",
    "MODIS_Terra_Land_Surface_Temp_Day": "Surface Temperature Day (MODIS, Daily)",
    "MODIS_Terra_Land_Surface_Temp_Night": "Surface Temperature Night (MODIS, Daily)",
    "MODIS_Terra_NDVI_8Day": "Vegetation Index NDVI (MODIS, 8-day)",
    "MODIS_Terra_L3_Land_Water_Mask": "Land/Water Mask (MODIS, Daily)",
    "IMERG_Precipitation_Rate": "Precipitation Rate (IMERG, 30min)",
    "VIIRS_SNPP_DayNightBand_ENCC": "Nighttime Lights (VIIRS, Monthly)",
    "MODIS_Combined_Thermal_Anomalies_Fire": "Active Fires (MODIS, Daily)",
    "OMPS_Ozone_Total_Column": "Ozone Column (OMPS, Daily)",
}

# Annual/static GIBS layers (slow-changing data)
GIBS_ANNUAL_LAYERS = {
    "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual": "Land Cover Type (MODIS, Annual)",
    "SRTM_Color_Index": "Elevation DEM (SRTM)",
}

# Combined layers for UI selection
COMMON_GEOSPATIAL_LAYERS = {
    **GIBS_NRT_LAYERS,
    **GIBS_ANNUAL_LAYERS,
}

GEOSPATIAL_LAYER_CHOICES = [
    "None",
    *COMMON_GEOSPATIAL_LAYERS.values(),
]

COMMON_FOLIUM_MAPS = {
    "OpenStreetMap": "Street Map",
    "CartoDB Positron": "Cartographic Light",
    "CartoDB Dark_Matter": "Cartographic Dark",
    "Esri WorldImagery": "Esri World Imagery",
    "OpenTopoMap": "Topographic Relief",
    "Esri NatGeoWorldMap": "National Geographic",
    "Esri OceanBasemap": "Ocean Basemap",
}

# [DATABASE TABLES]
###############################################################################
GEONAMES_TABLE = "geonames"
GIBS_LAYERS_TABLE = "gibs_layers"
SEARCH_SESSIONS_TABLE = "search_sessions"
MODEL_PROVIDER_SETTINGS_TABLE = "model_provider_settings"
MODEL_CREDENTIALS_TABLE = "model_credentials"
CHAT_SESSIONS_TABLE = "chat_sessions"
CHAT_MESSAGES_TABLE = "chat_messages"


# [DATABASE COLUMNS]
###############################################################################
GEONAMES_COLUMNS = [
    "geonameid",
    "name",
    "asciiname",
    "alternatenames",
    "latitude",
    "longitude",
    "feature_class",
    "feature_code",
    "country_code",
    "cc2",
    "admin1_code",
    "admin2_code",
    "admin3_code",
    "admin4_code",
    "population",
    "elevation",
    "dem",
    "timezone",
    "modification_date",
]

GIBS_LAYER_COLUMNS = [
    "layer_id",
    "title",
    "abstract",
    "projections",
    "source_urls",
    "tile_matrix_sets",
    "meters_per_pixel",
]

SEARCH_SESSION_COLUMNS = [
    "id",
    "created_at",
    "user",
    "country",
    "city",
    "address",
    "coordinates",
    "base_map",
    "geospatial_layers",
    "state",
]

MODEL_PROVIDER_SETTINGS_COLUMNS = [
    "id",
    "active_provider_mode",
    "chat_model_provider",
    "chat_model_name",
    "parser_model_provider",
    "parser_model_name",
    "agent_model_provider",
    "agent_model_name",
    "ollama_url",
    "openai_base_url",
    "google_base_url",
    "created_at",
    "updated_at",
]

MODEL_CREDENTIALS_COLUMNS = [
    "id",
    "provider",
    "label",
    "encrypted_value",
    "key_version",
    "is_active",
    "created_at",
    "updated_at",
    "last_used_at",
]

CHAT_SESSION_COLUMNS = [
    "id",
    "title",
    "status",
    "created_at",
    "updated_at",
    "last_map_session_json",
]

CHAT_MESSAGE_COLUMNS = [
    "id",
    "session_id",
    "turn_index",
    "role",
    "content",
    "structured_payload_json",
    "tool_payload_json",
    "map_session_json",
    "created_at",
]


# [COUNTRY DATA]
###############################################################################
COUNTRY_NAME_TO_ISO2 = {
    "Afghanistan": "AF",
    "Albania": "AL",
    "Algeria": "DZ",
    "American Samoa": "AS",
    "Andorra": "AD",
    "Angola": "AO",
    "Anguilla": "AI",
    "Antarctica": "AQ",
    "Antigua & Barbuda": "AG",
    "Argentina": "AR",
    "Armenia": "AM",
    "Aruba": "AW",
    "Australia": "AU",
    "Austria": "AT",
    "Azerbaijan": "AZ",
    "Bahamas": "BS",
    "Bahrain": "BH",
    "Bangladesh": "BD",
    "Barbados": "BB",
    "Belarus": "BY",
    "Belgium": "BE",
    "Belize": "BZ",
    "Benin": "BJ",
    "Bermuda": "BM",
    "Bhutan": "BT",
    "Bolivia": "BO",
    "Bosnia & Herzegovina": "BA",
    "Botswana": "BW",
    "Bouvet Island": "BV",
    "Brazil": "BR",
    "British Indian Ocean Territory": "IO",
    "British Virgin Islands": "VG",
    "Brunei": "BN",
    "Bulgaria": "BG",
    "Burkina Faso": "BF",
    "Burundi": "BI",
    "Cambodia": "KH",
    "Cameroon": "CM",
    "Canada": "CA",
    "Cape Verde": "CV",
    "Caribbean Netherlands": "BQ",
    "Cayman Islands": "KY",
    "Central African Republic": "CF",
    "Chad": "TD",
    "Chile": "CL",
    "China": "CN",
    "Christmas Island": "CX",
    "Cocos (Keeling) Islands": "CC",
    "Colombia": "CO",
    "Comoros": "KM",
    "Congo - Brazzaville": "CG",
    "Congo - Kinshasa": "CD",
    "Cook Islands": "CK",
    "Costa Rica": "CR",
    "Croatia": "HR",
    "Cuba": "CU",
    "Cura\xe7ao": "CW",
    "Cyprus": "CY",
    "Czechia": "CZ",
    "C\xf4te d'Ivoire": "CI",
    "Denmark": "DK",
    "Djibouti": "DJ",
    "Dominica": "DM",
    "Dominican Republic": "DO",
    "Ecuador": "EC",
    "Egypt": "EG",
    "El Salvador": "SV",
    "Equatorial Guinea": "GQ",
    "Eritrea": "ER",
    "Estonia": "EE",
    "Eswatini": "SZ",
    "Ethiopia": "ET",
    "Falkland Islands": "FK",
    "Faroe Islands": "FO",
    "Fiji": "FJ",
    "Finland": "FI",
    "France": "FR",
    "French Guiana": "GF",
    "French Polynesia": "PF",
    "French Southern Territories": "TF",
    "Gabon": "GA",
    "Gambia": "GM",
    "Georgia": "GE",
    "Germany": "DE",
    "Ghana": "GH",
    "Gibraltar": "GI",
    "Greece": "GR",
    "Greenland": "GL",
    "Grenada": "GD",
    "Guadeloupe": "GP",
    "Guam": "GU",
    "Guatemala": "GT",
    "Guernsey": "GG",
    "Guinea": "GN",
    "Guinea-Bissau": "GW",
    "Guyana": "GY",
    "Haiti": "HT",
    "Heard & McDonald Islands": "HM",
    "Honduras": "HN",
    "Hong Kong SAR China": "HK",
    "Hungary": "HU",
    "Iceland": "IS",
    "India": "IN",
    "Indonesia": "ID",
    "Iran": "IR",
    "Iraq": "IQ",
    "Ireland": "IE",
    "Isle of Man": "IM",
    "Israel": "IL",
    "Italy": "IT",
    "Jamaica": "JM",
    "Japan": "JP",
    "Jersey": "JE",
    "Jordan": "JO",
    "Kazakhstan": "KZ",
    "Kenya": "KE",
    "Kiribati": "KI",
    "Kuwait": "KW",
    "Kyrgyzstan": "KG",
    "Laos": "LA",
    "Latvia": "LV",
    "Lebanon": "LB",
    "Lesotho": "LS",
    "Liberia": "LR",
    "Libya": "LY",
    "Liechtenstein": "LI",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Macau SAR China": "MO",
    "Madagascar": "MG",
    "Malawi": "MW",
    "Malaysia": "MY",
    "Maldives": "MV",
    "Mali": "ML",
    "Malta": "MT",
    "Marshall Islands": "MH",
    "Martinique": "MQ",
    "Mauritania": "MR",
    "Mauritius": "MU",
    "Mayotte": "YT",
    "Mexico": "MX",
    "Micronesia": "FM",
    "Moldova": "MD",
    "Monaco": "MC",
    "Mongolia": "MN",
    "Montenegro": "ME",
    "Montserrat": "MS",
    "Morocco": "MA",
    "Mozambique": "MZ",
    "Myanmar (Burma)": "MM",
    "Namibia": "NA",
    "Nauru": "NR",
    "Nepal": "NP",
    "Netherlands": "NL",
    "New Caledonia": "NC",
    "New Zealand": "NZ",
    "Nicaragua": "NI",
    "Niger": "NE",
    "Nigeria": "NG",
    "Niue": "NU",
    "Norfolk Island": "NF",
    "North Korea": "KP",
    "North Macedonia": "MK",
    "Northern Mariana Islands": "MP",
    "Norway": "NO",
    "Oman": "OM",
    "Pakistan": "PK",
    "Palau": "PW",
    "Palestinian Territories": "PS",
    "Panama": "PA",
    "Papua New Guinea": "PG",
    "Paraguay": "PY",
    "Peru": "PE",
    "Philippines": "PH",
    "Pitcairn Islands": "PN",
    "Poland": "PL",
    "Portugal": "PT",
    "Puerto Rico": "PR",
    "Qatar": "QA",
    "R\xe9union": "RE",
    "Romania": "RO",
    "Russia": "RU",
    "Rwanda": "RW",
    "Saint Barth\xe9lemy": "BL",
    "Saint Helena": "SH",
    "Saint Kitts & Nevis": "KN",
    "Saint Lucia": "LC",
    "Saint Martin": "MF",
    "Saint Pierre & Miquelon": "PM",
    "Saint Vincent & Grenadines": "VC",
    "Samoa": "WS",
    "San Marino": "SM",
    "S\xe3o Tom\xe9 & Pr\xedncipe": "ST",
    "Saudi Arabia": "SA",
    "Senegal": "SN",
    "Serbia": "RS",
    "Seychelles": "SC",
    "Sierra Leone": "SL",
    "Singapore": "SG",
    "Sint Maarten": "SX",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Solomon Islands": "SB",
    "Somalia": "SO",
    "South Africa": "ZA",
    "South Georgia & South Sandwich Islands": "GS",
    "South Korea": "KR",
    "South Sudan": "SS",
    "Spain": "ES",
    "Sri Lanka": "LK",
    "Sudan": "SD",
    "Suriname": "SR",
    "Svalbard & Jan Mayen": "SJ",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Syria": "SY",
    "Taiwan": "TW",
    "Tajikistan": "TJ",
    "Tanzania": "TZ",
    "Thailand": "TH",
    "Timor-Leste": "TL",
    "Togo": "TG",
    "Tokelau": "TK",
    "Tonga": "TO",
    "Trinidad & Tobago": "TT",
    "Tunisia": "TN",
    "Turkey": "TR",
    "Turkmenistan": "TM",
    "Turks & Caicos Islands": "TC",
    "Tuvalu": "TV",
    "U.S. Outlying Islands": "UM",
    "U.S. Virgin Islands": "VI",
    "Uganda": "UG",
    "Ukraine": "UA",
    "United Arab Emirates": "AE",
    "United Kingdom": "GB",
    "United States": "US",
    "Uruguay": "UY",
    "Uzbekistan": "UZ",
    "Vanuatu": "VU",
    "Vatican City": "VA",
    "Venezuela": "VE",
    "Vietnam": "VN",
    "Wallis & Futuna": "WF",
    "Western Sahara": "EH",
    "Yemen": "YE",
    "Zambia": "ZM",
    "Zimbabwe": "ZW",
    "\xc5land Islands": "AX",
}

COUNTRY_SYNONYMS = {
    "Bolivia (Plurinational State of)": "Bolivia",
    "Brunei Darussalam": "Brunei",
    "Burma": "Myanmar (Burma)",
    "Congo, Democratic Republic": "Congo - Kinshasa",
    "Congo, Republic": "Congo - Brazzaville",
    "Czech Republic": "Czechia",
    "Democratic Republic of the Congo": "Congo - Kinshasa",
    "Federated States of Micronesia": "Micronesia",
    "Great Britain": "United Kingdom",
    "Hong Kong": "Hong Kong SAR China",
    "Hong Kong SAR": "Hong Kong SAR China",
    "Iran, Islamic Republic": "Iran",
    "Ivory Coast": "C\xf4te d'Ivoire",
    "Ivory Cost": "C\xf4te d'Ivoire",
    "Korea (South)": "South Korea",
    "Korea, Republic of": "South Korea",
    "Korea, South": "South Korea",
    "Lao People's Democratic Republic": "Laos",
    "Macao": "Macao SAR China",
    "Macao SAR": "Macao SAR China",
    "Macau": "Macao SAR China",
    "Macedonia": "North Macedonia",
    "Micronesia (Federated States of)": "Micronesia",
    "Myanmar": "Myanmar (Burma)",
    "Palestine": "Palestinian Territories",
    "Palestinian Territory": "Palestinian Territories",
    "Republic of Korea": "South Korea",
    "Republic of Moldova": "Moldova",
    "Republic of the Congo": "Congo - Brazzaville",
    "Russian Federation": "Russia",
    "Saint Barthelemy": "Saint Barth\xe9lemy",
    "Saint Kitts and Nevis": "Saint Kitts & Nevis",
    "Saint Lucia": "Saint Lucia",
    "Saint Martin": "Saint Martin",
    "Saint Pierre and Miquelon": "Saint Pierre & Miquelon",
    "Saint Vincent and the Grenadines": "Saint Vincent & Grenadines",
    "Sao Tome & Principe": "S\xe3o Tom\xe9 & Pr\xedncipe",
    "Sao Tome and Principe": "S\xe3o Tom\xe9 & Pr\xedncipe",
    "St Barthelemy": "Saint Barth\xe9lemy",
    "St Kitts and Nevis": "Saint Kitts & Nevis",
    "St Lucia": "Saint Lucia",
    "St Martin": "Saint Martin",
    "St Pierre and Miquelon": "Saint Pierre & Miquelon",
    "St Vincent and the Grenadines": "Saint Vincent & Grenadines",
    "Swaziland": "Eswatini",
    "Taiwan, Province of China": "Taiwan",
    "Timor Leste": "Timor-Leste",
    "T\xfcrkiye": "Turkey",
    "U A E": "United Arab Emirates",
    "U K": "United Kingdom",
    "U S A": "United States",
    "U.A.E.": "United Arab Emirates",
    "U.K.": "United Kingdom",
    "U.S.A.": "United States",
    "UAE": "United Arab Emirates",
    "UK": "United Kingdom",
    "USA": "United States",
    "United Arab Emirates": "United Arab Emirates",
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
    "United States America": "United States",
    "United States of America": "United States",
    "Vatican": "Vatican City",
    "Viet Nam": "Vietnam",
}


# [GEOSPATIAL CONSTANTS]
###############################################################################
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

# [JOBS AND SEARCH WORKFLOW]
###############################################################################
JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
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

# [SETTINGS DEFAULTS]
###############################################################################
DEFAULT_DB_CONNECT_TIMEOUT = 10
DEFAULT_DB_INSERT_BATCH_SIZE = 1000
DEFAULT_NOMINATIM_USER_AGENT = "AEGIS-Geographics/1.0 (contact: support@aegis.local)"
DEFAULT_GIBS_USER_AGENT = "AEGIS-GIBS/1.0"
DEFAULT_GIBS_LAYER_SYNC_USER_AGENT = "AEGIS-GIBS-LayerSync/1.0"
DEFAULT_GIBS_DEFAULT_LAYER = "VIIRS_SNPP_CorrectedReflectance_TrueColor"

# [GIBS FALLBACKS]
###############################################################################
GIBS_LAYER_NATIVE_RESOLUTION_M: dict[str, float] = {
    "VIIRS_SNPP_CorrectedReflectance_TrueColor": 375.0,
    "MODIS_Terra_Aerosol": 10000.0,
    "MODIS_Terra_Land_Surface_Temp_Day": 1000.0,
    "MODIS_Terra_Land_Surface_Temp_Night": 1000.0,
    "MODIS_Terra_NDVI_8Day": 250.0,
    "MODIS_Terra_L3_Land_Water_Mask": 250.0,
    "IMERG_Precipitation_Rate": 11000.0,
    "VIIRS_SNPP_DayNightBand_ENCC": 500.0,
    "MODIS_Combined_Thermal_Anomalies_Fire": 1000.0,
    "OMPS_Ozone_Total_Column": 50000.0,
    "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual": 500.0,
    "SRTM_Color_Index": 30.0,
}
GIBS_LAYER_DATE_FALLBACK_DAYS: dict[str, int] = {
    "MODIS_Combined_Thermal_Anomalies_All": 3,
    "MODIS_Combined_Thermal_Anomalies_Day": 3,
    "MODIS_Combined_Thermal_Anomalies_Night": 3,
    "OMPS_Ozone_Total_Column": 2,
}

GIBS_TILE_MATRIX_SET_TO_RESOLUTION_M: dict[str, float] = {
    "15.625m": 15.625,
    "31.25m": 31.25,
    "250m": 250.0,
    "500m": 500.0,
    "1km": 1000.0,
    "1.5km": 1500.0,
    "2km": 2000.0,
    "GoogleMapsCompatible_Level6": 2445.98490512564,
    "GoogleMapsCompatible_Level7": 1222.99245256282,
    "GoogleMapsCompatible_Level8": 611.49622628141,
    "GoogleMapsCompatible_Level9": 305.748113140705,
    "GoogleMapsCompatible_Level12": 38.21851414258813,
    "GoogleMapsCompatible_Level13": 19.109257071294063,
}

DEFAULT_LAYER_DEFINITIONS: dict[str, dict[str, object]] = {
    "VIIRS_SNPP_CorrectedReflectance_TrueColor": {
        "provider": "gibs",
        "aliases": (
            "truecolor",
            "true color",
            "viirs truecolor",
            "true color satellite",
            "satellite imagery",
        ),
    },
    "MODIS_Terra_Aerosol": {
        "provider": "gibs",
        "aliases": (
            "aerosol",
            "aerosol optical depth",
            "modis aerosol",
            "aod",
            "air pollution",
        ),
    },
    "MODIS_Terra_Land_Surface_Temp_Day": {
        "provider": "gibs",
        "aliases": (
            "surface temperature day",
            "land surface temperature",
            "lst day",
            "modis lst",
            "temperature day",
        ),
    },
    "MODIS_Terra_Land_Surface_Temp_Night": {
        "provider": "gibs",
        "aliases": (
            "surface temperature night",
            "lst night",
            "temperature night",
            "night temperature",
        ),
    },
    "MODIS_Terra_NDVI_8Day": {
        "provider": "gibs",
        "aliases": (
            "ndvi",
            "vegetation index",
            "modis ndvi",
            "vegetation",
            "greenness",
        ),
    },
    "MODIS_Terra_L3_Land_Water_Mask": {
        "provider": "gibs",
        "aliases": ("land/water mask", "water mask", "land water mask", "coastline"),
    },
    "IMERG_Precipitation_Rate": {
        "provider": "gibs",
        "aliases": (
            "precipitation rate",
            "imerg precipitation",
            "imerg",
            "rain",
            "rainfall",
        ),
    },
    "VIIRS_SNPP_DayNightBand_ENCC": {
        "provider": "gibs",
        "aliases": (
            "nighttime lights",
            "city lights",
            "viirs lights",
            "light pollution",
            "night lights",
        ),
    },
    "MODIS_Combined_Thermal_Anomalies_Fire": {
        "provider": "gibs",
        "provider_name": "MODIS_Combined_Thermal_Anomalies_All",
        "aliases": ("active fires", "fire", "fires", "thermal anomalies", "wildfire"),
    },
    "OMPS_Ozone_Total_Column": {
        "provider": "gibs",
        "aliases": (
            "ozone",
            "ozone column",
            "total ozone",
            "omps ozone",
            "atmospheric ozone",
        ),
    },
    "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual": {
        "provider": "gibs",
        "aliases": (
            "land cover",
            "land cover type",
            "modis igbp land cover",
            "igbp land cover",
            "land use",
        ),
    },
    "SRTM_Color_Index": {
        "provider": "gibs",
        "aliases": (
            "elevation",
            "dem",
            "digital elevation model",
            "terrain",
            "topography",
        ),
    },
}
