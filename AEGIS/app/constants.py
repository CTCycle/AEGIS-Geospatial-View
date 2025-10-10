from __future__ import annotations

from os.path import abspath, join

# [PATHS]
###############################################################################
ROOT_DIR = abspath(join(__file__, "../../.."))
PROJECT_DIR = join(ROOT_DIR, "AEGIS")
RSC_PATH = join(PROJECT_DIR, "resources")
MODELS_PATH = join(RSC_PATH, "models")
DATA_PATH = join(RSC_PATH, "database")
DOCS_PATH = join(DATA_PATH, "documents")
SOURCES_PATH = join(DATA_PATH, "sources")
TASKS_PATH = join(DATA_PATH, "tasks")
LOGS_PATH = join(RSC_PATH, "logs")

# [ENDPOINS]
###############################################################################
API_BASE_URL = "http://127.0.0.1:8000"
AGENT_API_URL = "/agent"
BATCH_AGENT_API_URL = "/batch-agent"


# [EXTERNAL DATA SOURCES]
###############################################################################
ATC_BASE_URL = "https://atcddd.fhi.no/atc_ddd_index/"
LIVERTOX_BASE_URL = "https://ftp.ncbi.nlm.nih.gov/pub/litarch/29/31/"
LIVERTOX_ARCHIVE = "livertox_NBK547852.tar.gz"
DEFAULT_LLM_TIMEOUT_SECONDS = 1_800.0
LIVERTOX_LLM_TIMEOUT_SECONDS = DEFAULT_LLM_TIMEOUT_SECONDS
LIVERTOX_YIELD_INTERVAL = 25
LIVERTOX_SKIP_DETERMINISTIC_RATIO = 0.80
LIVERTOX_MONOGRAPH_MAX_WORKERS = 4
MAX_EXCERPT_LENGTH = 8000
LLM_NULL_MATCH_NAMES = {
    "",
    "none",
    "no match",
    "no matches",
    "not found",
    "unknown",
    "not applicable",
    "n a",
}


# [CLINICAL ANALYSIS]
###############################################################################
DRUG_SUSPENSION_EXCLUSION_DAYS = 14
ALT_LABELS = {"ALT", "ALAT"}
ALP_LABELS = {"ALP"}

