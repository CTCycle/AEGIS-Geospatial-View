from __future__ import annotations

import base64
import time

import pytest

from server.services.geospatial.render_capture import (
    MAX_CAPTURE_BASE64_CHARS,
    RenderCapture,
    RenderCaptureStore,
)


###############################################################################
def _png_base64() -> str:
    # Minimal 1x1 PNG payload.
    return base64.b64encode(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
            "1f15c4890000000d49444154789c626001000000ffff03000006000557"
            "bfabd40000000049454e44ae426082"
        )
    ).decode("ascii")


###############################################################################
def test_save_and_get_round_trips_by_run_identity() -> None:
    store = RenderCaptureStore()
    capture = store.save(
        run_id="run-1",
        map_session_id="map-1",
        collection_revision=2,
        mime_type="image/jpeg",
        image_base64=_png_base64(),
        width=640,
        height=480,
        viewport_bounds=[-73.0, 40.0, -72.0, 41.0],
    )

    assert isinstance(capture, RenderCapture)
    assert capture.run_id == "run-1"
    assert capture.collection_revision == 2
    assert capture.viewport_bounds == (-73.0, 40.0, -72.0, 41.0)

    found = store.get("run-1", "map-1", 2)
    assert found is not None
    assert found.image_base64 == _png_base64()
    assert len(store) == 1

    assert store.get("run-1", "map-1", 3) is None
    assert store.get("run-2", "map-1", 2) is None


###############################################################################
def test_save_rejects_invalid_mime_size_base64_and_identity() -> None:
    store = RenderCaptureStore()
    payload = _png_base64()
    with pytest.raises(ValueError, match="mime"):
        store.save(
            run_id="run-1",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/gif",
            image_base64=payload,
            width=10,
            height=10,
        )
    with pytest.raises(ValueError, match="base64"):
        store.save(
            run_id="run-1",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/jpeg",
            image_base64="not-base64!!",
            width=10,
            height=10,
        )
    with pytest.raises(ValueError, match="size"):
        store.save(
            run_id="run-1",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/jpeg",
            image_base64="A" * (MAX_CAPTURE_BASE64_CHARS + 1),
            width=10,
            height=10,
        )
    with pytest.raises(ValueError, match="run_id"):
        store.save(
            run_id="",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/jpeg",
            image_base64=payload,
            width=10,
            height=10,
        )
    with pytest.raises(ValueError, match="width"):
        store.save(
            run_id="run-1",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/jpeg",
            image_base64=payload,
            width=0,
            height=10,
        )


###############################################################################
def test_delete_for_run_removes_all_captures_for_that_run() -> None:
    store = RenderCaptureStore()
    payload = _png_base64()
    store.save(run_id="run-1", map_session_id="map-1", collection_revision=1, mime_type="image/jpeg", image_base64=payload, width=10, height=10)
    store.save(run_id="run-1", map_session_id="map-2", collection_revision=1, mime_type="image/jpeg", image_base64=payload, width=10, height=10)
    store.save(run_id="run-2", map_session_id="map-1", collection_revision=1, mime_type="image/jpeg", image_base64=payload, width=10, height=10)

    assert store.delete_for_run("run-1") == 2
    assert len(store) == 1
    assert store.get("run-1", "map-1", 1) is None
    assert store.get("run-2", "map-1", 1) is not None


###############################################################################
def test_ttl_expiry_reclaims_stale_captures() -> None:
    store = RenderCaptureStore(ttl_seconds=1.0)
    payload = _png_base64()
    store.save(run_id="run-1", map_session_id="map-1", collection_revision=1, mime_type="image/jpeg", image_base64=payload, width=10, height=10)
    assert store.get("run-1", "map-1", 1) is not None

    # A capture recorded beyond the TTL is reclaimed on read.
    stale = RenderCaptureStore(ttl_seconds=1.0)
    stale._captures[("run-1", "map-1", 1)] = RenderCapture(
        run_id="run-1",
        map_session_id="map-1",
        collection_revision=1,
        mime_type="image/jpeg",
        image_base64=payload,
        width=10,
        height=10,
        viewport_bounds=None,
        captured_at=time.time() - 60.0,
    )
    assert stale.get("run-1", "map-1", 1) is None
    assert len(stale) == 0


###############################################################################
def test_clear_empties_the_store() -> None:
    store = RenderCaptureStore()
    store.save(run_id="run-1", map_session_id="map-1", collection_revision=1, mime_type="image/jpeg", image_base64=_png_base64(), width=10, height=10)
    store.clear()
    assert len(store) == 0