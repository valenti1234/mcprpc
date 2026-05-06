import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import settings

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="mcprpc-gui")
app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/config")
def get_config():
    return {
        "registry_url": settings.registry_url,
        "router_url": settings.router_url,
    }


def _merge_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {"accept": "application/json"}
    request_id = request.headers.get("x-request-id")
    if request_id:
        headers["x-request-id"] = request_id
    return headers


async def _proxy_json(
    *,
    request: Request,
    method: str,
    base_url: str,
    path: str,
    json_body: Any | None = None,
) -> Response:
    url = base_url.rstrip("/") + path
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method=method,
                url=url,
                params=dict(request.query_params),
                json=json_body,
                headers=_merge_headers(request),
                timeout=settings.timeout_s,
            )
    except httpx.TimeoutException as e:
        return JSONResponse(
            status_code=504,
            content={
                "error": "Upstream timeout",
                "upstream": url,
                "detail": str(e),
            },
        )
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=502,
            content={
                "error": "Upstream connection error",
                "upstream": url,
                "detail": str(e),
            },
        )

    content_type = resp.headers.get("content-type") or "application/json"
    return Response(content=resp.content, status_code=resp.status_code, media_type=content_type)


@app.get("/api/registry/health")
async def registry_health(request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.registry_url, path="/health")


@app.get("/api/registry/ready")
async def registry_ready(request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.registry_url, path="/ready")


@app.get("/api/registry/stats")
async def registry_stats(request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.registry_url, path="/stats")


@app.get("/api/registry/heartbeats")
async def registry_heartbeats(request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.registry_url, path="/heartbeats")


@app.get("/api/registry/functions")
async def registry_list_functions(request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.registry_url, path="/functions")


@app.get("/api/registry/functions/{name:path}")
async def registry_get_function(name: str, request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.registry_url, path=f"/functions/{name}")


@app.post("/api/registry/register")
async def registry_register(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})
    return await _proxy_json(
        request=request,
        method="POST",
        base_url=settings.registry_url,
        path="/register",
        json_body=payload,
    )


@app.post("/api/registry/resolve")
async def registry_resolve(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})
    return await _proxy_json(
        request=request,
        method="POST",
        base_url=settings.registry_url,
        path="/resolve",
        json_body=payload,
    )


@app.delete("/api/registry/functions/{name:path}")
async def registry_delete(name: str, request: Request):
    return await _proxy_json(request=request, method="DELETE", base_url=settings.registry_url, path=f"/functions/{name}")


@app.get("/api/router/health")
async def router_health(request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.router_url, path="/health")


@app.get("/api/router/ready")
async def router_ready(request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.router_url, path="/ready")


@app.get("/api/router/stats")
async def router_stats(request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.router_url, path="/stats")


@app.get("/api/router/heartbeat")
async def router_heartbeat(request: Request):
    return await _proxy_json(request=request, method="GET", base_url=settings.router_url, path="/heartbeat")


@app.post("/api/router/call")
async def router_call(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})
    return await _proxy_json(
        request=request,
        method="POST",
        base_url=settings.router_url,
        path="/call",
        json_body=payload,
    )


def cli():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="mcprpc-gui")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--reload", action="store_true", default=True)
    args = parser.parse_args()

    if args.command == "run":
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=bool(args.reload))
        return

    sys.exit(1)


if __name__ == "__main__":
    cli()
