import sys
import asyncio
import os
import time
import uuid
import uvicorn
import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session
from typing import List, Optional

from app.db import init_db, get_session, engine
from app.repository import FunctionRepository
from app.schemas import (
    FunctionRegisterRequest, 
    FunctionResponse, 
    ResolveRequest, 
    ResolveResponse,
    ActionResponse,
    HeartbeatRequest,
    HeartbeatResponse,
)

# Setup logging
logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

START_TS = time.time()
HEARTBEATS: dict[str, dict[str, object]] = {}
HEARTBEAT_GRACE_MULTIPLIER = float(os.getenv("MCPRPC_HEARTBEAT_GRACE_MULTIPLIER", "2.0"))
RR_LOCK = threading.Lock()
RR_INDEX: dict[str, int] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    stop_event = asyncio.Event()

    async def _expiry_loop():
        while not stop_event.is_set():
            try:
                with Session(engine) as session:
                    repo = FunctionRepository(session)
                    expired_records = repo.get_expired_records()
                    if expired_records:
                        grouped: dict[str, list] = {}
                        for r in expired_records:
                            grouped.setdefault(f"{r.service_name}:{getattr(r, 'mesh_id', '')}", []).append(r)

                        for service_key, recs in grouped.items():
                            service_name, mesh_id = service_key.split(":", 1)
                            logger.warning(
                                "event=heartbeat_expire service_name=%s mesh_id=%s functions=%s",
                                service_name,
                                mesh_id,
                                [x.name for x in recs],
                            )
                            for x in recs:
                                logger.warning(
                                    "event=heartbeat_expire_detail service_name=%s mesh_id=%s name=%s runtime=%s mcp_transport=%s health=%s last_heartbeat_at=%s expires_at=%s heartbeat_interval_s=%s",
                                    x.service_name,
                                    getattr(x, "mesh_id", ""),
                                    x.name,
                                    x.runtime,
                                    x.mcp_transport,
                                    x.health,
                                    getattr(x, "last_heartbeat_at", None),
                                    getattr(x, "expires_at", None),
                                    getattr(x, "heartbeat_interval_s", None),
                                )

                    deleted_count, deleted_meshes = repo.expire_services()
                    if deleted_meshes:
                        for mesh_id in deleted_meshes:
                            HEARTBEATS.pop(mesh_id, None)
            except Exception as e:
                logger.exception("event=heartbeat_expire_error error=%s", str(e))
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

    expiry_task = asyncio.create_task(_expiry_loop())
    yield
    stop_event.set()
    expiry_task.cancel()
    try:
        await expiry_task
    except BaseException:
        pass
    logger.info("Shutting down...")

app = FastAPI(
    title="mcprpc-registry",
    description="MCP-native function registry for polyglot function mesh systems",
    version="0.1.0",
    lifespan=lifespan
)

_cors_origins_raw = os.getenv("MCPRPC_CORS_ORIGINS", "").strip()
_cors_origin_regex = os.getenv(
    "MCPRPC_CORS_ALLOW_ORIGIN_REGEX",
    r"^https?://(localhost|127\.0\.0\.1|\[::1\]|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$",
).strip()
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=None if _cors_origins else (_cors_origin_regex or None),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_repository(session: Session = Depends(get_session)) -> FunctionRepository:
    return FunctionRepository(session)

@app.get("/health", tags=["System"])
def health_check(repo: FunctionRepository = Depends(get_repository)):
    db_ok = True
    total_functions: Optional[int] = None
    try:
        total_functions = repo.count()
    except Exception:
        db_ok = False

    uptime_s = int(time.time() - START_TS)
    status = "ok" if db_ok else "degraded"
    logger.info(
        "event=health service=mcprpc-registry status=%s db_ok=%s total_functions=%s tracked_services=%s uptime_s=%s",
        status,
        db_ok,
        total_functions,
        len(HEARTBEATS),
        uptime_s,
    )

    return {
        "status": status,
        "service": "mcprpc-registry",
        "version": "0.1.0",
        "uptime_s": uptime_s,
        "db_ok": db_ok,
        "total_functions": total_functions,
        "heartbeats": {
            "tracked_services": len(HEARTBEATS),
        },
    }

@app.get("/ready", tags=["System"])
def ready_check(repo: FunctionRepository = Depends(get_repository)):
    try:
        repo.count()
    except Exception as e:
        logger.warning("event=ready service=mcprpc-registry ok=false reason=%s", str(e))
        raise HTTPException(status_code=503, detail=f"Database not ready: {str(e)}")
    logger.info("event=ready service=mcprpc-registry ok=true")
    return {"status": "ready"}

@app.post("/heartbeat", response_model=HeartbeatResponse, tags=["System"])
def heartbeat(req: HeartbeatRequest, repo: FunctionRepository = Depends(get_repository)):
    interval_s = req.heartbeat_interval_s if req.heartbeat_interval_s is not None else 3
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=max(0, int(interval_s * HEARTBEAT_GRACE_MULTIPLIER)))

    registered = 0
    if req.registrations:
        for reg in req.registrations:
            reg2 = reg.model_copy(
                update={
                    "mesh_id": req.mesh_id,
                    "service_name": req.service_name,
                    "health": req.health,
                }
            )
            repo.register_or_update(reg2)
            registered += 1

    tool_names = req.tools
    if tool_names is None and req.registrations:
        tool_names = [r.name for r in req.registrations]

    updated = repo.update_health_for_service(
        service_name=req.service_name,
        mesh_id=req.mesh_id,
        health=req.health,
        tool_names=tool_names,
        heartbeat_interval_s=interval_s,
        last_heartbeat_at=now,
        expires_at=expires_at,
    )
    logger.info(
        "event=heartbeat service=mcprpc-registry service_name=%s mesh_id=%s health=%s registered=%s updated=%s tools=%s",
        req.service_name,
        req.mesh_id,
        req.health,
        registered,
        updated,
        len(tool_names) if tool_names else 0,
    )

    HEARTBEATS[req.mesh_id] = {
        "service_name": req.service_name,
        "mesh_id": req.mesh_id,
        "runtime": req.runtime,
        "health": req.health,
        "updated": updated,
        "heartbeat_interval_s": interval_s,
        "expires_at": expires_at.isoformat(),
        "ts": now.isoformat(),
    }

    return HeartbeatResponse(
        ok=True,
        updated=updated,
        service_name=req.service_name,
        mesh_id=req.mesh_id,
        health=req.health,
        ts=now,
        heartbeat_interval_s=interval_s,
        expires_at=expires_at,
    )

@app.get("/heartbeats", tags=["System"])
def list_heartbeats():
    return {
        "items": sorted(HEARTBEATS.values(), key=lambda x: str(x.get("mesh_id", ""))),
        "count": len(HEARTBEATS),
    }

@app.get("/stats", tags=["System"])
def get_stats(repo: FunctionRepository = Depends(get_repository)):
    count = repo.count()
    return {"total_functions": count}

@app.post("/register", response_model=ActionResponse, tags=["Registry"])
def register_function(req: FunctionRegisterRequest, repo: FunctionRepository = Depends(get_repository)):
    logger.info(f"Registering function: {req.name} ({req.mcp_transport})")
    action, record = repo.register_or_update(req)
    return ActionResponse(
        action=action,
        function=FunctionResponse.from_record(record)
    )

@app.get("/functions", response_model=List[FunctionResponse], tags=["Registry"])
def list_functions(
    tag: Optional[str] = Query(None, description="Filter by tag"),
    runtime: Optional[str] = Query(None, description="Filter by runtime"),
    repo: FunctionRepository = Depends(get_repository)
):
    records = repo.list_functions(tag=tag, runtime=runtime)
    return [FunctionResponse.from_record(r) for r in records]

@app.get("/functions/{name}", response_model=FunctionResponse, tags=["Registry"])
def get_function(name: str, repo: FunctionRepository = Depends(get_repository)):
    record = repo.get_by_name(name)
    if not record:
        raise HTTPException(status_code=404, detail="Function not found")
    return FunctionResponse.from_record(record)

@app.post("/resolve", response_model=ResolveResponse, tags=["Registry"])
def resolve_function(req: ResolveRequest, repo: FunctionRepository = Depends(get_repository)):
    logger.info(f"Resolving function: {req.name}")
    semantic = repo.semanticize(req.name)
    now = datetime.now(timezone.utc)
    candidates = repo.list_candidates(req.name, now=now)
    if not candidates:
        records = repo.list_by_semantic(semantic)
        if records:
            items = []
            for r in records:
                items.append(
                    {
                        "name": r.name,
                        "semantic_name": getattr(r, "semantic_name", None),
                        "service_name": r.service_name,
                        "mesh_id": getattr(r, "mesh_id", ""),
                        "health": r.health,
                        "last_heartbeat_at": getattr(r, "last_heartbeat_at", None),
                        "expires_at": getattr(r, "expires_at", None),
                        "heartbeat_interval_s": getattr(r, "heartbeat_interval_s", None),
                    }
                )
            logger.info(
                "event=resolve_unavailable name=%s semantic_name=%s records=%s",
                req.name,
                semantic,
                len(items),
            )
            raise HTTPException(
                status_code=410,
                detail={
                    "error": "Function unavailable (expired or unhealthy)",
                    "name": req.name,
                    "semantic_name": semantic,
                    "records": items,
                },
            )

        raise HTTPException(status_code=404, detail="Function not found")

    candidates = sorted(
        candidates,
        key=lambda r: (
            getattr(r, "mesh_id", ""),
            getattr(r, "endpoint", ""),
        ),
    )
    with RR_LOCK:
        idx = RR_INDEX.get(semantic, 0) % len(candidates)
        RR_INDEX[semantic] = RR_INDEX.get(semantic, 0) + 1
    selected = candidates[idx]
    logger.info(
        "event=resolve_selected name=%s semantic_name=%s mesh_id=%s candidates=%s rr_index=%s",
        req.name,
        semantic,
        getattr(selected, "mesh_id", ""),
        len(candidates),
        idx,
    )
        
    return ResolveResponse(
        metadata=FunctionResponse.from_record(selected),
        transport_details={
            "transport": selected.transport,
            "mcp_transport": selected.mcp_transport,
            "endpoint": selected.endpoint,
        },
    )

@app.delete("/functions/{name}", tags=["Registry"])
def delete_function(name: str, repo: FunctionRepository = Depends(get_repository)):
    success = repo.delete(name)
    if not success:
        raise HTTPException(status_code=404, detail="Function not found")
    logger.info(f"Deleted function: {name}")
    return {"detail": "Function deleted"}

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
    """CLI entrypoint"""
    import argparse
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    parser = argparse.ArgumentParser(description="MCP-native registry service")
    mode = parser.add_subparsers(dest="mode", required=True)

    p_run = mode.add_parser("run")
    p_run.add_argument("--port", type=int, default=7000)
    p_run.add_argument("--host", type=str, default="0.0.0.0")
    p_run.add_argument("--reload", action="store_true", default=True)

    def add_url(p: argparse.ArgumentParser):
        p.add_argument("--url", type=str, default="http://localhost:7000")
        p.add_argument("--timeout-s", type=float, default=5.0)

    p_remote = mode.add_parser("remote", help="Remote client commands (no server start)")
    remote = p_remote.add_subparsers(dest="command", required=True)

    p_health = remote.add_parser("health")
    add_url(p_health)

    p_ready = remote.add_parser("ready")
    add_url(p_ready)

    p_stats = remote.add_parser("stats")
    add_url(p_stats)

    p_heartbeats = remote.add_parser("heartbeats")
    add_url(p_heartbeats)

    p_functions = remote.add_parser("functions")
    add_url(p_functions)
    p_functions.add_argument("--tag", default=None)
    p_functions.add_argument("--runtime", default=None)

    p_get_function = remote.add_parser("get-function")
    add_url(p_get_function)
    p_get_function.add_argument("name")

    p_resolve = remote.add_parser("resolve")
    add_url(p_resolve)
    p_resolve.add_argument("name")

    p_register = remote.add_parser("register")
    add_url(p_register)
    p_register.add_argument("--json", dest="json_payload", required=True)

    p_delete = remote.add_parser("delete-function")
    add_url(p_delete)
    p_delete.add_argument("name")

    args = parser.parse_args()

    if args.mode == "run":
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=bool(args.reload))
        return

    base = args.url.rstrip("/")

    def http_json(method: str, path: str, payload: object | None = None) -> tuple[int, str]:
        url = f"{base}{path}"
        data = None
        headers = {"accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["content-type"] = "application/json"
        req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=float(args.timeout_s)) as resp:
                return int(resp.status), resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if getattr(e, "fp", None) is not None else str(e)
            return int(getattr(e, "code", 0) or 0), body

    if args.command == "health":
        status, body = http_json("GET", "/health")
        sys.stdout.write(body + "\n")
        sys.exit(0 if status and status < 400 else 1)

    if args.command == "ready":
        status, body = http_json("GET", "/ready")
        sys.stdout.write(body + "\n")
        sys.exit(0 if status and status < 400 else 1)

    if args.command == "stats":
        status, body = http_json("GET", "/stats")
        sys.stdout.write(body + "\n")
        sys.exit(0 if status and status < 400 else 1)

    if args.command == "heartbeats":
        status, body = http_json("GET", "/heartbeats")
        sys.stdout.write(body + "\n")
        sys.exit(0 if status and status < 400 else 1)

    if args.command == "functions":
        q = {}
        if args.tag:
            q["tag"] = args.tag
        if args.runtime:
            q["runtime"] = args.runtime
        qs = ("?" + urllib.parse.urlencode(q)) if q else ""
        status, body = http_json("GET", f"/functions{qs}")
        sys.stdout.write(body + "\n")
        sys.exit(0 if status and status < 400 else 1)

    if args.command == "get-function":
        name = urllib.parse.quote(args.name, safe="")
        status, body = http_json("GET", f"/functions/{name}")
        sys.stdout.write(body + "\n")
        sys.exit(0 if status and status < 400 else 1)

    if args.command == "resolve":
        status, body = http_json("POST", "/resolve", {"name": args.name})
        sys.stdout.write(body + "\n")
        sys.exit(0 if status and status < 400 else 1)

    if args.command == "register":
        try:
            payload = json.loads(args.json_payload)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"invalid json: {str(e)}\n")
            sys.exit(2)
        status, body = http_json("POST", "/register", payload)
        sys.stdout.write(body + "\n")
        sys.exit(0 if status and status < 400 else 1)

    if args.command == "delete-function":
        name = urllib.parse.quote(args.name, safe="")
        status, body = http_json("DELETE", f"/functions/{name}")
        sys.stdout.write(body + "\n")
        sys.exit(0 if status and status < 400 else 1)

if __name__ == "__main__":
    cli()
