from __future__ import annotations

from os.path import abspath, join

# [PATHS]
###############################################################################
ROOT_DIR = abspath(join(__file__, "../../.."))
PROJECT_DIR = join(ROOT_DIR, "AEGIS")
RSC_PATH = join(PROJECT_DIR, "resources")
SETUP_PATH = join(ROOT_DIR, "DILIGENT", "setup")
CONFIGURATION_PATH = join(SETUP_PATH, "configurations.json")
MODELS_PATH = join(RSC_PATH, "models")
DATA_PATH = join(RSC_PATH, "database")
DOCS_PATH = join(DATA_PATH, "documents")
SOURCES_PATH = join(DATA_PATH, "sources")
TASKS_PATH = join(DATA_PATH, "tasks")
LOGS_PATH = join(RSC_PATH, "logs")

# [ENDPOINS]
###############################################################################
GEO_SEARCH_URL = "/maps/search"
GEO_AGENTIC_URL = "/maps/agentic"


# [EXTERNAL DATA SOURCES]
###############################################################################
NASA_BASE_URL = "https://atcddd.fhi.no/atc_ddd_index/"
API_BASE_URL = "http://127.0.0.1:8002"
HTTP_TIMEOUT_SECONDS = 1800.0
DEFAULT_TIMELINE_BACKTRACK = 20
SURROUNDING_RANGE = 10
MIN_YEAR = 1900
DEFAULT_AGENTIC_TEMPERATURE = 0.7
MIN_AGENTIC_TEMPERATURE = 0.0
MAX_AGENTIC_TEMPERATURE = 2.0

# [CLIENT OPTIONS]
###############################################################################
FILTER_CHOICES = [
    "Natural Color",
    "Topographic",
    "Population Density",
    "Weather Overlay",
]
DEFAULT_FILTER = FILTER_CHOICES[0]
OPENAI_MODEL_CHOICES = [
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-3.5-turbo",
]
AGENT_MODEL_CHOICES = [
    "llama3",
    "mistral",
    "phi3",
]
DEFAULT_AGENT_MODEL = AGENT_MODEL_CHOICES[0]


# [GEONAMES]
###############################################################################



