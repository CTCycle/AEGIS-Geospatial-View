"""Local QA proxy: answers the first N model POSTs with HTTP 429, forwards everything else.

Forwards only to the genuine OpenCode Go host. Usage: python fault_proxy.py <port> <n_429>
"""
import sys

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

UPSTREAM = "https://opencode.ai/zen/go/v1"
PORT = int(sys.argv[1])
REMAINING = {"429": int(sys.argv[2])}
client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
HOP = {"host", "content-length", "transfer-encoding", "connection", "accept-encoding"}


async def proxy(request: Request) -> Response:
    path = request.path_params["path"]
    if request.method == "POST" and REMAINING["429"] > 0:
        REMAINING["429"] -= 1
        print(f"INJECTED 429 for POST /{path} (left {REMAINING['429']})", flush=True)
        return JSONResponse(
            {"error": {"message": "Rate limit exceeded (QA injected)", "type": "rate_limit_error"}},
            status_code=429,
            headers={"Retry-After": "2"},
        )
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
    upstream = client.build_request(
        request.method, f"{UPSTREAM}/{path}", params=request.query_params,
        headers=headers, content=await request.body(),
    )
    response = await client.send(upstream, stream=True)
    print(f"forwarded {request.method} /{path} -> {response.status_code}", flush=True)
    out_headers = {k: v for k, v in response.headers.items() if k.lower() not in HOP | {"content-encoding"}}
    return StreamingResponse(response.aiter_bytes(), status_code=response.status_code, headers=out_headers,
                             background=None)


app = Starlette(routes=[Route("/{path:path}", proxy, methods=["GET", "POST"])])
uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
