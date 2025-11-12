from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from AEGIS.src.packages.constants import DATA_PATH
from AEGIS.src.packages.utils.repository.database import GeonamesRecord, database
