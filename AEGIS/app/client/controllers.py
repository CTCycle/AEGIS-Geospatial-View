from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import httpx
from gradio import update as gr_update

from AEGIS.app.constants import GEO_API_URL
   

# [AGENT RUNNING LOGIC]
###############################################################################
async def run_agent(
    patient_name: str | None,
    visit_date: datetime | date | dict[str, Any] | str | None,
    anamnesis: str,
    has_hepatic_diseases: bool,
    drugs: str,
    exams: str,
    alt: str,
    alt_max: str,
    alp: str,
    alp_max: str,
    symptoms: list[str],
    process_from_files: bool,
    enhance_clinical_text: bool,
) -> str:
    if process_from_files:
        url = f"{API_BASE_URL}{BATCH_AGENT_API_URL}"
        return await _trigger_agent(url)

    normalized_visit_date = _normalize_visit_date(visit_date)

    cleaned_payload = {
        "name": _sanitize_field(patient_name),
        "visit_date": (
            {
                "day": normalized_visit_date.day,
                "month": normalized_visit_date.month,
                "year": normalized_visit_date.year,
            }
            if normalized_visit_date
            else None
        ),
        "anamnesis": _sanitize_field(anamnesis),
        "has_hepatic_diseases": bool(has_hepatic_diseases),
        "drugs": _sanitize_field(drugs),
        "exams": _sanitize_field(exams),
        "alt": _sanitize_field(alt),
        "alt_max": _sanitize_field(alt_max),
        "alp": _sanitize_field(alp),
        "alp_max": _sanitize_field(alp_max),
        "symptoms": symptoms or [],
        "enhance_clinical_text": bool(enhance_clinical_text),
    }

    if not any(cleaned_payload[key] for key in ("anamnesis", "drugs", "exams")):
        return "[ERROR] Please provide at least one clinical section."

    url = f"{API_BASE_URL}{AGENT_API_URL}"
    return await _trigger_agent(url, cleaned_payload)
