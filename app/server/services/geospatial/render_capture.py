from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field

from server.common.typing import is_json_array

###############################################################################
# In-memory TTL store for browser map captures.
#
# The client posts the rendered MapLibre canvas here (after downscaling) keyed
# by the run identity tuple the render handshake already carries.  The agent
# loop reads the capture back on the next model step when the vision policy
# asks for it.  Captures are bounded by size, expire on a TTL, and are deleted
# when the owning run terminates.
###############################################################################

SUPPORTED_CAPTURE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)
# Client-side downscale/compression keeps captures well under this bound; the
# cap protects the store and the LLM request from runaway payloads.
MAX_CAPTURE_BASE64_CHARS = 3 * 1024 * 1024
DEFAULT_CAPTURE_TTL_SECONDS = 900.0


###############################################################################
@dataclass(frozen=True)
class RenderCapture:
    run_id: str
    map_session_id: str
    collection_revision: int
    mime_type: str
    image_base64: str
    width: int
    height: int
    viewport_bounds: tuple[float, float, float, float] | None
    captured_at: float = field(default_factory=time.time)

    # -------------------------------------------------------------------------
    def image_bytes(self) -> bytes:
        return base64.b64decode(self.image_base64)


###############################################################################
def _is_valid_base64(value: str) -> bool:
    if not value:
        return False
    try:
        base64.b64decode(value, validate=True)
        return True
    except (ValueError, TypeError):
        return False


###############################################################################
class RenderCaptureStore:
    """Bounded in-memory capture registry keyed by the run identity tuple."""

    def __init__(self, *, ttl_seconds: float = DEFAULT_CAPTURE_TTL_SECONDS) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self._captures: dict[tuple[str, str, int], RenderCapture] = {}

    # -------------------------------------------------------------------------
    def _key(self, run_id: str, map_session_id: str, collection_revision: int) -> tuple[str, str, int]:
        return (run_id, map_session_id, collection_revision)

    # -------------------------------------------------------------------------
    def _expire(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        if not self._captures:
            return
        stale = [
            key
            for key, capture in self._captures.items()
            if now - capture.captured_at > self.ttl_seconds
        ]
        for key in stale:
            self._captures.pop(key, None)

    # -------------------------------------------------------------------------
    def save(
        self,
        *,
        run_id: str,
        map_session_id: str,
        collection_revision: int,
        mime_type: str,
        image_base64: str,
        width: int,
        height: int,
        viewport_bounds: list[float] | None = None,
    ) -> RenderCapture:
        if not run_id.strip() or not map_session_id.strip():
            raise ValueError("run_id and map_session_id are required.")
        if collection_revision < 0:
            raise ValueError("collection_revision must be non-negative.")
        if mime_type not in SUPPORTED_CAPTURE_MIME_TYPES:
            raise ValueError(
                f"Unsupported capture mime type '{mime_type}'. "
                f"Supported: {sorted(SUPPORTED_CAPTURE_MIME_TYPES)}."
            )
        if not isinstance(image_base64, str) or not _is_valid_base64(image_base64):
            raise ValueError("image_base64 must be valid base64 image data.")
        if len(image_base64) > MAX_CAPTURE_BASE64_CHARS:
            raise ValueError(
                "Capture exceeds the base64 size bound "
                f"({MAX_CAPTURE_BASE64_CHARS} characters)."
            )
        if width <= 0 or height <= 0:
            raise ValueError("Capture width and height must be positive.")
        bounds: tuple[float, float, float, float] | None = None
        if is_json_array(viewport_bounds) and len(viewport_bounds) == 4:
            if not all(isinstance(item, (int, float)) for item in viewport_bounds):
                raise ValueError("viewport_bounds must contain numeric values.")
            bounds = (float(viewport_bounds[0]), float(viewport_bounds[1]), float(viewport_bounds[2]), float(viewport_bounds[3]))
        self._expire()
        capture = RenderCapture(
            run_id=run_id,
            map_session_id=map_session_id,
            collection_revision=collection_revision,
            mime_type=mime_type,
            image_base64=image_base64,
            width=width,
            height=height,
            viewport_bounds=bounds,
        )
        self._captures[self._key(run_id, map_session_id, collection_revision)] = capture
        return capture

    # -------------------------------------------------------------------------
    def get(
        self,
        run_id: str,
        map_session_id: str,
        collection_revision: int,
    ) -> RenderCapture | None:
        self._expire()
        return self._captures.get(
            self._key(run_id, map_session_id, collection_revision)
        )

    # -------------------------------------------------------------------------
    def delete_for_run(self, run_id: str) -> int:
        removed = [
            key
            for key in self._captures
            if key[0] == run_id
        ]
        for key in removed:
            self._captures.pop(key, None)
        return len(removed)

    # -------------------------------------------------------------------------
    def clear(self) -> None:
        self._captures.clear()

    # -------------------------------------------------------------------------
    def __len__(self) -> int:
        self._expire()
        return len(self._captures)