from __future__ import annotations

import math
import os
import time
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urljoin
from xml.etree import ElementTree

import httpx




