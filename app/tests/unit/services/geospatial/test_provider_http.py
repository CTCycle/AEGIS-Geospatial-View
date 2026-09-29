from __future__ import annotations

import httpx
import pytest

from tests.conftest import run_async_in_thread

from server.services.geospatial.providers import http as provider_http


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: tuple[bytes, ...] = (),
        body_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = httpx.Headers(headers or {})
        self._chunks = chunks
        self._body_error = body_error

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def aiter_bytes(self):  # noqa: ANN201
        if self._body_error is not None:
            raise self._body_error
        for chunk in self._chunks:
            yield chunk


class _FakeClient:
    def __init__(self, response: _FakeResponse | Exception) -> None:
        self.response = response

    def stream(self, *args: object, **kwargs: object):  # noqa: ANN201
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _request_error(message: str) -> httpx.RequestError:
    return httpx.ConnectError(message, request=httpx.Request("GET", "https://example.test/tile"))


@pytest.mark.parametrize(
    ("status_code", "category"),
    [
        (301, "unexpected_redirect"),
        (401, "authentication_rejected"),
        (404, "invalid_request"),
        (429, "rate_limited"),
        (500, "upstream_http_5xx"),
        (503, "upstream_http_5xx"),
    ],
)
def test_raster_http_classifies_upstream_statuses(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    category: str,
) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                status_code=status_code,
                headers={
                    "content-type": "text/html; charset=utf-8",
                    "content-length": "17",
                },
            )
        ),
    )

    with provider_http.raster_diagnostic_scope(
        provider_id="fema", capability_id="fema_nfhl_flood_zones"
    ):
        with pytest.raises(provider_http.RasterHttpError) as error:
            run_async_in_thread(
                provider_http.fetch_raster_image_url(
                    "https://example.test/tile.png?api_key=secret-token&token=secret-token"
                )
            )

    diagnostic = error.value.diagnostic
    assert diagnostic.category == category
    assert diagnostic.status_code == status_code
    assert diagnostic.content_type == "text/html"
    assert diagnostic.content_length == 17
    assert diagnostic.failure_phase == "response_headers"
    assert diagnostic.provider_id == "fema"
    assert diagnostic.capability_id == "fema_nfhl_flood_zones"
    assert diagnostic.upstream == "https://example.test/tile.png"
    assert "secret-token" not in str(error.value)
    assert "secret-token" not in diagnostic.upstream


def test_raster_http_classifies_timeout_and_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for expected_category, exception in (
        ("timeout", httpx.ReadTimeout("secret-timeout")),
        ("transport_error", _request_error("secret-transport")),
    ):
        monkeypatch.setattr(
            provider_http,
            "_ASYNC_HTTP_CLIENT",
            _FakeClient(exception),
        )
        with pytest.raises(provider_http.RasterHttpError) as error:
            run_async_in_thread(
                provider_http.fetch_raster_image_url(
                    "https://example.test/tile.png?credential=secret-token"
                )
            )
        assert error.value.diagnostic.category == expected_category
        assert error.value.diagnostic.failure_phase == "request"
        assert error.value.diagnostic.status_code is None
        assert "secret" not in str(error.value).lower()


def test_raster_http_classifies_body_read_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                headers={"content-type": "image/png", "content-length": "8"},
                body_error=RuntimeError("secret body failure"),
            )
        ),
    )

    with pytest.raises(provider_http.RasterHttpError) as error:
        run_async_in_thread(
            provider_http.fetch_raster_image_url("https://example.test/tile.png")
        )

    assert error.value.diagnostic.category == "body_read_failure"
    assert error.value.diagnostic.failure_phase == "response_body"
    assert error.value.diagnostic.status_code == 200
    assert error.value.diagnostic.content_type == "image/png"
    assert error.value.diagnostic.content_length == 8
    assert "secret body failure" not in str(error.value)


@pytest.mark.parametrize(
    ("body", "content_type", "category"),
    [
        (b"", "image/png", "empty_body"),
        (b"<html>provider error</html>", "text/html", "non_image_body"),
        (b"<?xml version='1.0'?><error/>", "application/xml", "non_image_body"),
    ],
)
def test_raster_http_classifies_empty_and_non_image_bodies(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    content_type: str,
    category: str,
) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                headers={"content-type": content_type},
                chunks=(body,),
            )
        ),
    )

    with pytest.raises(provider_http.RasterHttpError) as error:
        run_async_in_thread(
            provider_http.fetch_raster_image_url("https://example.test/tile.png")
        )

    assert error.value.diagnostic.category == category
    assert error.value.diagnostic.failure_phase == "validation"
    assert error.value.diagnostic.status_code == 200
    assert error.value.diagnostic.content_type == content_type
    assert error.value.diagnostic.content_length == len(body)


@pytest.mark.parametrize(
    "body",
    [b"\x89PNG\r\n\x1a\npng", b"\xff\xd8\xffjpeg"],
)
def test_raster_http_accepts_png_and_jpeg(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                headers={"content-type": "image/png"}, chunks=(body,)
            )
        ),
    )

    assert run_async_in_thread(
        provider_http.fetch_raster_image_url("https://example.test/tile.png")
    ) == body


def test_raster_http_classifies_oversized_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_http,
        "_ASYNC_HTTP_CLIENT",
        _FakeClient(
            _FakeResponse(
                headers={"content-type": "image/png", "content-length": "9"},
                chunks=(b"\x89PNG\r\n\x1a\n",),
            )
        ),
    )

    with pytest.raises(provider_http.RasterHttpError) as error:
        run_async_in_thread(
            provider_http.fetch_raster_image_url(
                "https://example.test/tile.png", max_bytes=8
            )
        )

    assert error.value.diagnostic.category == "response_too_large"
    assert error.value.diagnostic.failure_phase == "response_headers"
    assert error.value.diagnostic.status_code == 200
    assert error.value.diagnostic.content_length == 9
