"""Complete counters alongside bounded, reviewable browser event samples."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Page


class NetworkCapture:
    upstream_hosts: frozenset[str] = frozenset()

    def __init__(self, max_events: int = 512) -> None:
        self.max_events = max_events
        self.events: list[dict[str, Any]] = []
        self.console: list[dict[str, str]] = []
        self.page_errors: list[str] = []
        self.requests_by_host: Counter[str] = Counter()
        self.requests_by_transport: Counter[str] = Counter()
        self.proxy_requests_by_capability: Counter[str] = Counter()
        self.dropped_events = 0
        self.started_at: str | None = None
        self.ended_at: str | None = None

    def _append(self, event: dict[str, Any]) -> None:
        if event.get("kind") == "request":
            host = (urlsplit(str(event.get("url", ""))).hostname or "").casefold()
            self.requests_by_host[host] += 1
            self.requests_by_transport[str(event.get("transport"))] += 1
            if event.get("transport") == "aegis_proxy":
                self.proxy_requests_by_capability[str(event.get("capability_id"))] += 1
        if len(self.events) < self.max_events:
            self.events.append(event)
        else:
            self.dropped_events += 1

    def summary(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "requests_by_host": {
                host: self.requests_by_host[host]
                for host in sorted(self.upstream_hosts | self.requests_by_host.keys())
            },
            "requests_by_transport": dict(self.requests_by_transport),
            "proxy_requests_by_capability": dict(self.proxy_requests_by_capability),
            "stored_events": len(self.events),
            "dropped_events": self.dropped_events,
            "counters_independent_of_event_limit": True,
        }

    def attach(self, page: Page) -> None:
        raise NotImplementedError


@contextmanager
def observed_page(
    browser: Browser, capture: NetworkCapture, output: Path
) -> Generator[Page, None, None]:
    """Observe a fresh context before navigation; retain evidence on exceptions."""
    with browser.new_context(
        service_workers="block", viewport={"width": 1440, "height": 1000}
    ) as context:
        # Routing disables the browser HTTP cache, without mocking any responses.
        context.route("**/*", lambda route: route.continue_())
        page = context.new_page()
        capture.attach(page)
        capture.started_at = datetime.now(timezone.utc).isoformat()
        failure: str | None = None
        try:
            yield page
        except BaseException as exc:
            # Exception messages can contain response bodies or credential URLs.
            failure = type(exc).__name__
            try:
                page.screenshot(
                    path=str(output.with_suffix(".png")), full_page=True, timeout=5000
                )
            except Exception:
                pass
            raise
        finally:
            capture.ended_at = datetime.now(timezone.utc).isoformat()
            output.write_text(
                json.dumps(
                    {
                        "observation": capture.summary(),
                        "service_workers": "blocked",
                        "http_cache": "disabled_by_context_routing",
                        "failure_type": failure,
                        "events": capture.events,
                        "console": capture.console,
                        "page_errors": capture.page_errors,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
