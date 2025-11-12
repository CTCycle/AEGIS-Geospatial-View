from __future__ import annotations

from os.path import abspath, join

# [PATHS]
###############################################################################
ROOT_DIR = abspath(join(__file__, "../../.."))
PROJECT_DIR = join(ROOT_DIR, "AEGIS")
SETUP_DIR = join(PROJECT_DIR, "setup")
RSC_PATH = join(PROJECT_DIR, "resources")
SETUP_PATH = join(ROOT_DIR, "DILIGENT", "setup")
CONFIGURATION_PATH = join(SETUP_PATH, "configurations.json")
MODELS_PATH = join(RSC_PATH, "models")
DATA_PATH = join(RSC_PATH, "database")
DOCS_PATH = join(DATA_PATH, "documents")
SOURCES_PATH = join(DATA_PATH, "sources")
TASKS_PATH = join(DATA_PATH, "tasks")
LOGS_PATH = join(RSC_PATH, "logs")
DATABASE_FILENAME = "database.db"

# [ENDPOINS]
###############################################################################
GEO_SEARCH_URL = "/maps/search"
GEO_AGENTIC_URL = "/maps/agentic"


# [EXTERNAL DATA SOURCES]
###############################################################################
NASA_BASE_URL = "https://atcddd.fhi.no/atc_ddd_index/"
DEFAULT_TIMELINE_BACKTRACK = 20
SURROUNDING_RANGE = 10
MIN_YEAR = 1900
DEFAULT_AGENTIC_TEMPERATURE = 0.7
MIN_AGENTIC_TEMPERATURE = 0.0
MAX_AGENTIC_TEMPERATURE = 2.0

# [CLIENT OPTIONS]
###############################################################################
OPENAI_CLOUD_MODELS = ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"]
GEMINI_CLOUD_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
    "gemini-1.0-pro",
    "gemini-1.0-pro-vision",
]

AGENT_MODEL_CHOICES = [
    "gpt-oss:20b",
    "llama3.1:8b",
    "llama3.1:70b",
    "phi3.5:mini",
    "phi3.5:moe",
    "deepseek-r1:14b",
    "gemma3:27b",
]

CLOUD_MODEL_CHOICES: dict[str, list[str]] = {
    "openai": OPENAI_CLOUD_MODELS,
    "gemini": GEMINI_CLOUD_MODELS,
}

SATELLITE_STYLE_CHOICES = [
    "Hybrid (Map + Satellite)",
    "Street Map",
    "Pure Satellite",
    "Terrain Emphasis",
]

GEOSPATIAL_LAYER_CHOICES = [
    "Land Cover (NLCD)",
    "Digital Elevation Model (SRTM)",
    "Population Density (GPW)",
    "Hydrology (HydroSHEDS)",
    "Weather Radar (NEXRAD)",
]
