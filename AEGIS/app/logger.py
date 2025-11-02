from __future__ import annotations

import logging
import logging.config
import os
from datetime import datetime
from typing import Any

from AEGIS.app.constants import LOGS_PATH

ACCESS_LOG_BLOCKLIST = ["/_nicegui/"]


###############################################################################
class AccessPathFilter(logging.Filter):
    # -----------------------------------------------------------------------------
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(blocked in message for blocked in ACCESS_LOG_BLOCKLIST)


# Generate timestamp for the log filename
###############################################################################
current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = os.path.join(LOGS_PATH, f"AEGIS_{current_timestamp}.log")

# Define logger configuration
###############################################################################
LOG_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "exclude_access_paths": {
            "()": AccessPathFilter,
        },
    },
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%d-%m-%Y %H:%M:%S",
        },
        "minimal": {
            "format": "[%(levelname)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "minimal",
        },
        "file": {
            "class": "logging.FileHandler",
            "level": "DEBUG",
            "formatter": "default",
            "filename": log_filename,
            "mode": "a",
        },
    },
    "loggers": {
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False,
            "filters": ["exclude_access_paths"],
        },
        "matplotlib": {
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False,
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file"],
    },
}


# override logger configuration and load root logger
###############################################################################
logging.config.dictConfig(LOG_CONFIG)
logger = logging.getLogger()
