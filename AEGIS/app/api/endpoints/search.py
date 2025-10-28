from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, HTTPException, status


router = APIRouter(tags=["search"])


###############################################################################
@router.post("/location", status_code=status.HTTP_200_OK)
async def search_by_location():
    pass


