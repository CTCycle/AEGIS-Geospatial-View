from __future__ import annotations

import argparse
import contextlib
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, parse, request


###############################################################################
class SpaProxyHandler(SimpleHTTPRequestHandler):
    server_version = "AEGIS-SpaProxy/1.0"

    # -------------------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy_request()
            return
        self._serve_spa()

    # -------------------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy_request()
            return
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    # -------------------------------------------------------------------------
    def do_PUT(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy_request()
            return
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    # -------------------------------------------------------------------------
    def do_DELETE(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy_request()
            return
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    # -------------------------------------------------------------------------
    def do_PATCH(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy_request()
            return
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    # -------------------------------------------------------------------------
    def _serve_spa(self) -> None:
        path_only = self.path.split("?", 1)[0]
        local_path = Path(self.translate_path(path_only))
        if local_path.exists():
            return super().do_GET()
        self.path = "/index.html"
        return super().do_GET()

    # -------------------------------------------------------------------------
    def _proxy_request(self) -> None:
        backend_base: str = self.server.backend_base_url  # type: ignore[attr-defined]
        target_url = parse.urljoin(backend_base, self.path)
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else None
        upstream = request.Request(
            target_url,
            data=body,
            method=self.command,
            headers={
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "content-length", "connection"}
            },
        )
        try:
            with request.urlopen(upstream, timeout=30) as response:
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() in {"transfer-encoding", "connection"}:
                        continue
                    self.send_header(key, value)
                self.end_headers()
                if payload:
                    self.wfile.write(payload)
        except error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() in {"transfer-encoding", "connection"}:
                    continue
                self.send_header(key, value)
            self.end_headers()
            if payload:
                self.wfile.write(payload)
        except Exception as exc:  # noqa: BLE001
            self.send_response(HTTPStatus.BAD_GATEWAY)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(str(exc).encode("utf-8"))


###############################################################################
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--frontend-root", required=True)
    parser.add_argument("--backend-base-url", required=True)
    return parser.parse_args()


###############################################################################
def main() -> int:
    args = parse_args()
    frontend_root = Path(args.frontend_root).resolve()
    if not frontend_root.exists():
        raise FileNotFoundError(f"Frontend root not found: {frontend_root}")

    os.chdir(frontend_root)
    server = ThreadingHTTPServer((args.host, args.port), SpaProxyHandler)
    server.backend_base_url = args.backend_base_url.rstrip("/")  # type: ignore[attr-defined]
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
