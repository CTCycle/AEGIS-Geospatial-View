from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from AEGIS.app.constants import DATA_PATH
from AEGIS.app.configurations import Configuration
from AEGIS.app.utils.repository.database import GeonamesRecord, database


