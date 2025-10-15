from __future__ import annotations

import base64
import json
import os
from binascii import Error as BinasciiError
from typing import Any

import httpx
from gradio import update as gr_update

from AEGIS.app.constants import GEO_API_URL

_API_BASE_URL = os.getenv("AEGIS_API_BASE_URL", "http://127.0.0.1:8000")
_HTTP_TIMEOUT_SECONDS = 30.0


###############################################################################
def set_location_mode(use_coordinates: bool) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if use_coordinates:
        return (
            gr_update(value=None, interactive=False),
            gr_update(value="", interactive=False),
            gr_update(value=None, interactive=True),
            gr_update(value=None, interactive=True),
        )

    return (
        gr_update(interactive=True),
        gr_update(interactive=True),
        gr_update(value=None, interactive=False),
        gr_update(value=None, interactive=False),
    )


###############################################################################
async def load_map_image(
    filter_name: str | None,
    country: str | None,
    city: str | None,
    use_coordinates: bool,
    latitude: float | None,
    longitude: float | None,
) -> tuple[dict[str, Any], str]:
    payload, error_message = build_request_payload(
        filter_name=filter_name,
        country=country,
        city=city,
        use_coordinates=use_coordinates,
        latitude=latitude,
        longitude=longitude,
    )
    if error_message:
        return gr_update(value=None), error_message

    try:
        async with httpx.AsyncClient(
            base_url=_API_BASE_URL, timeout=_HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(GEO_API_URL, json=payload)
        response.raise_for_status()
    except httpx.RequestError as exc:
        return gr_update(value=None), f"[ERROR] Unable to reach map service: {exc}"
    except httpx.HTTPStatusError as exc:
        detail = extract_error_detail(exc.response)
        return (
            gr_update(value=None),
            f"[ERROR] Map service error {exc.response.status_code}: {detail}",
        )

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        return (
            gr_update(value=None),
            f"[ERROR] Invalid response received from map service: {exc}",
        )

    if not isinstance(data, dict):
        return gr_update(value=None), "[ERROR] Map service returned an unexpected payload."

    image_value, message = coerce_image_value(data)
    if image_value is None:
        detail = message or data.get("detail") or data.get("message")
        return gr_update(value=None), f"[ERROR] {detail or 'No imagery available.'}"

    status_message = message or data.get("message") or data.get("detail")
    if not status_message:
        status_message = "Map imagery loaded successfully."

    return gr_update(value=image_value), status_message


###############################################################################
def build_request_payload(
    *,
    filter_name: str | None,
    country: str | None,
    city: str | None,
    use_coordinates: bool,
    latitude: float | None,
    longitude: float | None,
) -> tuple[dict[str, Any], str | None]:
    payload: dict[str, Any] = {}
    if filter_name:
        payload["filter"] = filter_name

    if use_coordinates:
        if latitude is None or longitude is None:
            return {}, "[ERROR] Provide both latitude and longitude to use coordinates."
        payload["coordinates"] = {"latitude": latitude, "longitude": longitude}
        return payload, None

    if not country and not city:
        return {}, "[ERROR] Specify at least a country or a city to locate the map."

    payload["location"] = {
        "country": country or None,
        "city": city or None,
    }
    return payload, None


###############################################################################
def extract_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except json.JSONDecodeError:
        return response.text.strip() or "Unexpected error"

    if isinstance(data, dict):
        detail = data.get("detail") or data.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return "Unexpected error"


###############################################################################
def coerce_image_value(payload: dict[str, Any]) -> tuple[bytes | str | None, str]:
    message = ""
    image_value: bytes | str | None = None

    image_section = payload.get("image")
    if isinstance(image_section, dict):
        message = coerce_message(image_section)
        image_value = extract_image_from_dict(image_section)

    if image_value is None:
        if isinstance(payload.get("image_url"), str):
            image_value = payload["image_url"]
        elif isinstance(payload.get("animation_url"), str):
            image_value = payload["animation_url"]
        elif isinstance(payload.get("image_base64"), str):
            image_value = decode_base64(payload["image_base64"])
        elif isinstance(payload.get("image_data"), str):
            image_value = decode_base64(payload["image_data"])
        elif isinstance(payload.get("image"), str):
            decoded = decode_base64(payload["image"])
            image_value = decoded if decoded is not None else payload["image"]

    if image_value is None:
        frames = payload.get("frames")
        if isinstance(frames, list):
            for frame in frames:
                if isinstance(frame, str):
                    candidate = decode_base64(frame)
                    if candidate is not None:
                        image_value = candidate
                        break

    if not message:
        message = coerce_message(payload)

    return image_value, message


###############################################################################
def extract_image_from_dict(data: dict[str, Any]) -> bytes | str | None:
    if isinstance(data.get("url"), str):
        return data["url"]
    base64_candidate = data.get("base64") or data.get("data")
    if isinstance(base64_candidate, str):
        decoded = decode_base64(base64_candidate)
        if decoded is not None:
            return decoded
        return base64_candidate
    return None


###############################################################################
def coerce_message(data: dict[str, Any]) -> str:
    for key in ("caption", "message", "detail", "status"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


###############################################################################
def decode_base64(data: str) -> bytes | None:
    try:
        return base64.b64decode(data, validate=True)
    except (ValueError, BinasciiError):
        return None
