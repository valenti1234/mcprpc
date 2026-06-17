import sys
import time
import uuid
import logging
import os
import httpx
from collections import Counter, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from threading import Lock

from .schemas import CallRequest, CallResponse, CallResponseMeta
from .registry_client import resolve_function, RegistryClientError, registry_circuit_snapshot
from .acl import validate_acl, ACLError
from .mcp_executor import (
    execute_mcp_tool,
    MCPExecutorError,
    mcp_circuits_snapshot,
    start_stdio_pool,
    shutdown_stdio_pool,
)
from .config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_stdio_pool()
    yield
    await shutdown_stdio_pool()

app = FastAPI(title="MCP RPC Router", lifespan=lifespan)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_cors_any_origin = True
_cors_origins_raw = os.getenv("MCPRPC_CORS_ORIGINS", "").strip()
_cors_origin_regex = os.getenv(
    "MCPRPC_CORS_ALLOW_ORIGIN_REGEX",
    r"^https?://(localhost|127\.0\.0\.1|\[::1\]|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$",
).strip()
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

if _cors_any_origin:
    _cors_origins = ["*"]
    _cors_origin_regex = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=None if _cors_origins else (_cors_origin_regex or None),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def _cors_any_origin_preflight(request: Request, call_next):
    if request.method.upper() != "OPTIONS":
        return await call_next(request)

    origin = request.headers.get("origin") or "*"
    request_method = request.headers.get("access-control-request-method") or "*"
    request_headers = request.headers.get("access-control-request-headers") or "*"

    allow_origin = "*" if origin == "null" else origin
    allow_methods = request_method if request_method != "*" else "GET,POST,PUT,PATCH,DELETE,OPTIONS"

    headers = {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Methods": allow_methods,
        "Access-Control-Allow-Headers": request_headers,
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers",
    }
    return Response(status_code=204, headers=headers)

START_TS = time.time()
STATS_LOCK = Lock()
STATS_START_TS = time.time()
STATS_DURATIONS_MS = deque(maxlen=2000)
STATS_TOTAL = 0
STATS_OK = 0
STATS_ERR = 0
STATS_BY_FUNCTION = Counter()
STATS_BY_FUNCTION_OK = Counter()
STATS_BY_FUNCTION_ERR = Counter()
STATS_BY_MESH_ID = Counter()
STATS_BY_ENDPOINT = Counter()
STATS_BY_MCP_TRANSPORT = Counter()
STATS_RECENT_ERRORS = deque(maxlen=50)


def _stats_record(
    *,
    function: str,
    ok: bool,
    duration_ms: int,
    mcp_transport: str | None = None,
    mesh_id: str | None = None,
    endpoint: str | None = None,
    error: str | None = None,
    resolved_function: str | None = None,
):
    global STATS_TOTAL, STATS_OK, STATS_ERR
    with STATS_LOCK:
        STATS_TOTAL += 1
        STATS_BY_FUNCTION[function] += 1
        STATS_DURATIONS_MS.append(int(duration_ms))
        if mcp_transport:
            STATS_BY_MCP_TRANSPORT[mcp_transport] += 1
        if mesh_id:
            STATS_BY_MESH_ID[mesh_id] += 1
        if endpoint:
            STATS_BY_ENDPOINT[endpoint] += 1
        if ok:
            STATS_OK += 1
            STATS_BY_FUNCTION_OK[function] += 1
        else:
            STATS_ERR += 1
            STATS_BY_FUNCTION_ERR[function] += 1
            STATS_RECENT_ERRORS.append(
                {
                    "ts": int(time.time()),
                    "function": function,
                    "resolved_function": resolved_function,
                    "mcp_transport": mcp_transport,
                    "mesh_id": mesh_id,
                    "endpoint": endpoint,
                    "error": error,
                }
            )


def _percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    if p <= 0:
        return values[0]
    if p >= 100:
        return values[-1]
    k = int(round((p / 100.0) * (len(values) - 1)))
    return values[max(0, min(k, len(values) - 1))]

@app.post("/call", response_model=CallResponse)
async def call_function(request: CallRequest):
    start_time = time.time()
    resolve_resp = None
    resolved_function = None
    mcp_transport = None
    endpoint_str = None
    mesh_id = None
    service_name = None
    
    try:
        # 1. Call registry /resolve with function name
        resolve_resp = await resolve_function(request.function)
        
        if not resolve_resp.ok:
            duration_ms = int((time.time() - start_time) * 1000)
            _stats_record(function=request.function, ok=False, duration_ms=duration_ms, error=resolve_resp.error)
            return CallResponse(
                ok=False,
                error=resolve_resp.error or "Failed to resolve function"
            )

        # Try to avoid stdio endpoints: the router does not spawn workers.
        if (resolve_resp.mcp_transport or "stdio") == "stdio":
            for _ in range(3):
                resolve_try = await resolve_function(request.function)
                if resolve_try.ok and (resolve_try.mcp_transport or "stdio") != "stdio":
                    resolve_resp = resolve_try
                    break

        mcp_transport = resolve_resp.mcp_transport or "stdio"
        resolved_function = resolve_resp.resolved_function or request.function
        mesh_id = getattr(resolve_resp, "mesh_id", None)
        service_name = getattr(resolve_resp, "service_name", None)
        endpoint_str = None
        if resolve_resp.endpoint:
            if resolve_resp.endpoint.url:
                endpoint_str = resolve_resp.endpoint.url
            elif resolve_resp.endpoint.command:
                endpoint_str = " ".join([resolve_resp.endpoint.command] + (resolve_resp.endpoint.args or []))

        # 2. Validate basic ACL
        if resolve_resp.acl:
            validate_acl(resolve_resp.acl, request.context.roles)

        # 3 & 4. Based on mcp_transport, call tool
        if resolved_function != request.function:
            logger.info(
                "event=semantic_resolve requested_function=%s resolved_function=%s semantic_name=%s",
                request.function,
                resolved_function,
                resolve_resp.semantic_name,
            )

        if mcp_transport == "stdio":
            duration_ms = int((time.time() - start_time) * 1000)
            msg = (
                "MCP Tool Execution failed: stdio transport is not supported by the router "
                "(router must not spawn workers). Use streamable-http/sse worker endpoints instead."
            )
            _stats_record(
                function=request.function,
                ok=False,
                duration_ms=duration_ms,
                mcp_transport=mcp_transport,
                mesh_id=mesh_id,
                endpoint=endpoint_str,
                error=msg,
                resolved_function=resolved_function,
            )
            return CallResponse(ok=False, error=msg)
        
        tool_result = await execute_mcp_tool(
            mcp_transport=mcp_transport,
            endpoint=resolve_resp.endpoint,
            function=resolved_function,
            arguments=request.arguments
        )
        
        # 5. Return result
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Parse result from mcp.types.CallToolResult if it's an object
        # Often tool_result has a content attribute. We'll try to extract it as a dictionary
        # or return it as is.
        if hasattr(tool_result, "content"):
            # mcp.types.CallToolResult has content list
            # We will just serialize it using pydantic or dict
            result_data = {"content": [{"type": c.type, "text": getattr(c, "text", None)} for c in tool_result.content]}
        elif hasattr(tool_result, "model_dump"):
            result_data = tool_result.model_dump()
        else:
            result_data = tool_result

        meta = CallResponseMeta(
            function=request.function,
            runtime=resolve_resp.runtime or "python",
            transport=resolve_resp.transport or "mcp",
            mcp_transport=mcp_transport,
            durationMs=duration_ms,
            mesh_id=mesh_id,
            service_name=service_name,
            endpoint=endpoint_str,
            resolved_function=resolved_function,
        )
        _stats_record(
            function=request.function,
            ok=True,
            duration_ms=duration_ms,
            mcp_transport=mcp_transport,
            mesh_id=meta.mesh_id,
            endpoint=endpoint_str,
            resolved_function=resolved_function,
        )
        
        return CallResponse(
            ok=True,
            result=result_data,
            meta=meta
        )
        
    except RegistryClientError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        _stats_record(function=request.function, ok=False, duration_ms=duration_ms, error=str(e))
        return CallResponse(ok=False, error=str(e))
    except ACLError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        _stats_record(
            function=request.function,
            ok=False,
            duration_ms=duration_ms,
            error=str(e),
            mesh_id=mesh_id,
            endpoint=endpoint_str,
            resolved_function=(resolved_function or request.function),
        )
        return CallResponse(ok=False, error=str(e))
    except MCPExecutorError as e:
        if resolve_resp and getattr(resolve_resp, "mcp_transport", None) in ("sse", "streamable-http", "stdio"):
            logger.warning(
                "event=mcp_call_retry requested_function=%s resolved_function=%s mcp_transport=%s reason=%s",
                request.function,
                (resolve_resp.resolved_function or request.function),
                resolve_resp.mcp_transport,
                str(e),
            )
            try:
                resolve_resp2 = await resolve_function(request.function)
                if not resolve_resp2.ok:
                    return CallResponse(ok=False, error=resolve_resp2.error or str(e))

                if resolve_resp2.acl:
                    validate_acl(resolve_resp2.acl, request.context.roles)

                mcp_transport2 = resolve_resp2.mcp_transport or "stdio"
                resolved_function2 = resolve_resp2.resolved_function or request.function
                if mcp_transport2 == "stdio":
                    return CallResponse(
                        ok=False,
                        error=(
                            "MCP Tool Execution failed: stdio transport is not supported by the router "
                            "(router must not spawn workers). Use streamable-http/sse worker endpoints instead."
                        ),
                    )

                tool_result = await execute_mcp_tool(
                    mcp_transport=mcp_transport2,
                    endpoint=resolve_resp2.endpoint,
                    function=resolved_function2,
                    arguments=request.arguments,
                )

                duration_ms = int((time.time() - start_time) * 1000)
                if hasattr(tool_result, "content"):
                    result_data = {"content": [{"type": c.type, "text": getattr(c, "text", None)} for c in tool_result.content]}
                elif hasattr(tool_result, "model_dump"):
                    result_data = tool_result.model_dump()
                else:
                    result_data = tool_result

                endpoint_str = None
                if resolve_resp2.endpoint:
                    if resolve_resp2.endpoint.url:
                        endpoint_str = resolve_resp2.endpoint.url
                    elif resolve_resp2.endpoint.command:
                        endpoint_str = " ".join([resolve_resp2.endpoint.command] + (resolve_resp2.endpoint.args or []))

                meta = CallResponseMeta(
                    function=request.function,
                    runtime=resolve_resp2.runtime or "python",
                    transport=resolve_resp2.transport or "mcp",
                    mcp_transport=mcp_transport2,
                    durationMs=duration_ms,
                    mesh_id=getattr(resolve_resp2, "mesh_id", None),
                    service_name=getattr(resolve_resp2, "service_name", None),
                    endpoint=endpoint_str,
                    resolved_function=resolved_function2,
                )
                _stats_record(
                    function=request.function,
                    ok=True,
                    duration_ms=duration_ms,
                    mcp_transport=mcp_transport2,
                    mesh_id=meta.mesh_id,
                    endpoint=endpoint_str,
                    resolved_function=resolved_function2,
                )

                return CallResponse(ok=True, result=result_data, meta=meta)
            except Exception as e2:
                duration_ms = int((time.time() - start_time) * 1000)
                _stats_record(function=request.function, ok=False, duration_ms=duration_ms, error=f"{str(e)} | retry_failed={str(e2)}")
                return CallResponse(ok=False, error=f"{str(e)} | retry_failed={str(e2)}")

        duration_ms = int((time.time() - start_time) * 1000)
        _stats_record(function=request.function, ok=False, duration_ms=duration_ms, error=str(e))
        return CallResponse(ok=False, error=str(e))
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        _stats_record(function=request.function, ok=False, duration_ms=duration_ms, error=f"Internal Server Error: {str(e)}")
        return CallResponse(ok=False, error=f"Internal Server Error: {str(e)}")

@app.get("/health")
def health_check():
    uptime_s = int(time.time() - START_TS)
    registry_cb = registry_circuit_snapshot()
    mcp_cbs = mcp_circuits_snapshot()
    logger.info(
        "event=health service=mcprpc-router uptime_s=%s registry_cb_state=%s mcp_circuits=%s",
        uptime_s,
        registry_cb.get("state"),
        len(mcp_cbs),
    )
    return {
        "status": "ok",
        "service": "mcprpc-router",
        "version": "0.1.0",
        "uptime_s": uptime_s,
        "dependencies": {
            "registry_url": settings.registry_url,
        },
        "circuits": {
            "registry": registry_cb,
            "mcp": mcp_cbs,
        },
    }

@app.get("/heartbeat")
def heartbeat():
    logger.info("event=heartbeat service=mcprpc-router status=alive")
    return {"status": "alive", "ts": int(time.time())}

@app.get("/ready")
async def ready_check():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.registry_url}/ready", timeout=settings.registry_timeout_s)
            if resp.status_code >= 400:
                raise HTTPException(status_code=503, detail=f"Registry not ready: {resp.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Registry not ready: {str(e)}")

    return {"status": "ready"}


@app.get("/stats")
def stats():
    with STATS_LOCK:
        durations = sorted(list(STATS_DURATIONS_MS))
        top_functions = []
        for fn, total in STATS_BY_FUNCTION.most_common(20):
            top_functions.append(
                {
                    "function": fn,
                    "total": total,
                    "ok": STATS_BY_FUNCTION_OK.get(fn, 0),
                    "error": STATS_BY_FUNCTION_ERR.get(fn, 0),
                }
            )

        top_mesh = [{"mesh_id": k, "count": v} for k, v in STATS_BY_MESH_ID.most_common(20)]
        top_endpoints = [{"endpoint": k, "count": v} for k, v in STATS_BY_ENDPOINT.most_common(20)]
        by_transport = [{"mcp_transport": k, "count": v} for k, v in STATS_BY_MCP_TRANSPORT.most_common()]
        recent_errors = list(STATS_RECENT_ERRORS)
        total = STATS_TOTAL
        ok = STATS_OK
        err = STATS_ERR

    uptime_s = int(time.time() - STATS_START_TS)
    return {
        "service": "mcprpc-router",
        "uptime_s": uptime_s,
        "calls": {"total": total, "ok": ok, "error": err},
        "latency_ms": {
            "count": len(durations),
            "p50": _percentile(durations, 50),
            "p95": _percentile(durations, 95),
            "max": (durations[-1] if durations else None),
        },
        "by_function_top": top_functions,
        "by_mesh_id_top": top_mesh,
        "by_endpoint_top": top_endpoints,
        "by_mcp_transport": by_transport,
        "recent_errors": recent_errors,
    }

@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.time() - start) * 1000)
        logger.exception(
            f"request_id={request_id} method={request.method} path={request.url.path} status=500 duration_ms={duration_ms}"
        )
        raise

    duration_ms = int((time.time() - start) * 1000)
    logger.info(
        f"request_id={request_id} method={request.method} path={request.url.path} status={response.status_code} duration_ms={duration_ms}"
    )
    response.headers["x-request-id"] = request_id
    return response


def cli():
    import argparse
    import uvicorn
    import urllib.request

    parser = argparse.ArgumentParser(description="MCP RPC Router")
    parser.add_argument("command", choices=["run", "health"], help="Command")
    parser.add_argument("--port", type=int, default=8001, help="Port to run on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run on")
    parser.add_argument("--url", type=str, default="http://localhost:8001", help="Base URL for health command")

    args = parser.parse_args()

    if args.command == "run":
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=True)
        return

    if args.command == "health":
        try:
            with urllib.request.urlopen(f"{args.url.rstrip('/')}/health", timeout=5) as resp:
                sys.stdout.write(resp.read().decode("utf-8"))
                sys.stdout.write("\n")
        except Exception as e:
            sys.stderr.write(f"Health check failed: {str(e)}\n")
            sys.exit(1)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    cli()
