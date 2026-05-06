import asyncio
import json
import logging
import os
import shlex
import signal
import sys
import threading
import time
import uuid
from urllib.parse import urlparse
from urllib.parse import urlunparse
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Union

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport, TransportSecuritySettings
import mcp.types as types
import uvicorn
from starlette.responses import JSONResponse, PlainTextResponse

from .discovery import discover_module, discover_path
from .schema import extract_metadata
from .registry import publish_to_registry, send_heartbeat, build_register_payload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

class AutoMesh:
    def __init__(
        self,
        service_name: str,
        registry_url: str,
        runtime: str = "python",
        mcp_transport: str = "stdio",
        endpoint: Optional[str] = None,
        heartbeat_interval_s: Optional[int] = None,
        mesh_id: Optional[str] = None,
    ):
        self.service_name = service_name
        self.registry_url = registry_url
        self.runtime = runtime
        self.mcp_transport = mcp_transport
        if endpoint is not None:
            self.endpoint = endpoint
        elif self.mcp_transport in ("sse", "streamable-http"):
            self.endpoint = os.getenv("MCPRPC_SSE_URL") or "http://localhost:7002/sse/"
        else:
            self.endpoint = self._default_endpoint()

        if self.mcp_transport in ("sse", "streamable-http"):
            parsed = urlparse(self.endpoint)
            if parsed.scheme in ("http", "https"):
                path = parsed.path or "/sse/"
                if not path.endswith("/"):
                    path = path + "/"
                self.endpoint = urlunparse(
                    (
                        parsed.scheme,
                        parsed.netloc,
                        path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment,
                    )
                )
        self.mesh_id = mesh_id or os.getenv("MCPRPC_MESH_ID") or uuid.uuid4().hex
        self._start_ts = time.time()

        interval_env = os.getenv("MCPRPC_HEARTBEAT_INTERVAL_S")
        if heartbeat_interval_s is not None:
            self._heartbeat_interval_s = heartbeat_interval_s
        elif interval_env is not None:
            self._heartbeat_interval_s = int(interval_env)
        else:
            self._heartbeat_interval_s = 3
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        
        self.server = Server(self.service_name)
        self._functions: Dict[str, Callable] = {}
        self._tools: List[types.Tool] = []
        self._registrations: Dict[str, Dict[str, Any]] = {}
        
        self._setup_mcp_handlers()
        self._register_builtin_tools()
        
    def _default_endpoint(self) -> str:
        parts = [sys.executable] + (sys.argv or [])
        return " ".join(shlex.quote(p) for p in parts if p)

    def _is_system_tool(self, name: str) -> bool:
        return name.startswith("system.")

    def _register_builtin_tools(self):
        def system_health() -> str:
            payload = {
                "status": "ok",
                "service": self.service_name,
                "runtime": self.runtime,
                "version": "0.1.0",
                "uptime_s": int(time.time() - self._start_ts),
                "tools": len(self._tools),
            }
            return json.dumps(payload)

        def system_heartbeat() -> str:
            ok = False
            if self.registry_url:
                logger.info("Sending heartbeat to registry")
                ok = send_heartbeat(
                    registry_url=self.registry_url,
                    service_name=self.service_name,
                    mesh_id=self.mesh_id,
                    runtime=self.runtime,
                    health="healthy",
                    tools=list(self._registrations.keys()),
                    heartbeat_interval_s=self._heartbeat_interval_s,
                    registrations=list(self._registrations.values()),
                )
            return json.dumps({"ok": ok})

        system_health.__automesh_name__ = "system.health"
        system_health.__automesh_tags__ = ["system", "health"]
        self._register_function(system_health, publish=False)

        system_heartbeat.__automesh_name__ = "system.heartbeat"
        system_heartbeat.__automesh_tags__ = ["system", "heartbeat"]
        self._register_function(system_heartbeat, publish=False)

    def _setup_mcp_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            return self._tools
            
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            if name not in self._functions:
                raise ValueError(f"Unknown tool: {name}")
                
            func = self._functions[name]
            args = arguments or {}
            
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(**args)
                else:
                    result = func(**args)
                    
                return [types.TextContent(type="text", text=str(result))]
            except Exception as e:
                # Return error text per MCP spec
                return [types.TextContent(type="text", text=f"Error executing {name}: {str(e)}")]

    def _register_function(self, func: Callable, publish: bool = True):
        metadata = extract_metadata(func)
        tool_name = metadata["name"]
        
        if tool_name in self._functions:
            return
            
        self._functions[tool_name] = func
        logger.info("event=tool_register name=%s", tool_name)
        
        tool = types.Tool(
            name=tool_name,
            description=metadata["description"] or f"Tool {tool_name}",
            inputSchema=metadata["inputSchema"]
        )
        self._tools.append(tool)
        
        if self.registry_url and publish:
            self._registrations[tool_name] = build_register_payload(
                service_name=self.service_name,
                mesh_id=self.mesh_id,
                runtime=self.runtime,
                mcp_transport=self.mcp_transport,
                endpoint=self.endpoint,
                metadata=metadata,
            )
            publish_to_registry(
                registry_url=self.registry_url,
                service_name=self.service_name,
                mesh_id=self.mesh_id,
                runtime=self.runtime,
                mcp_transport=self.mcp_transport,
                endpoint=self.endpoint,
                metadata=metadata
            )

    def start_heartbeat(self):
        if not self.registry_url or not self._heartbeat_interval_s:
            logger.info(
                "event=heartbeat_start skipped=true service_name=%s registry_url=%s interval_s=%s",
                self.service_name,
                bool(self.registry_url),
                self._heartbeat_interval_s,
            )
            return
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._heartbeat_stop.clear()

        logger.info(
            "event=heartbeat_start skipped=false service_name=%s interval_s=%s",
            self.service_name,
            self._heartbeat_interval_s,
        )
        send_heartbeat(
            registry_url=self.registry_url,
            service_name=self.service_name,
            mesh_id=self.mesh_id,
            runtime=self.runtime,
            health="healthy",
            tools=list(self._registrations.keys()),
            heartbeat_interval_s=self._heartbeat_interval_s,
            registrations=list(self._registrations.values()),
        )

        def _loop():
            while not self._heartbeat_stop.wait(self._heartbeat_interval_s):
                send_heartbeat(
                    registry_url=self.registry_url,
                    service_name=self.service_name,
                    mesh_id=self.mesh_id,
                    runtime=self.runtime,
                    health="healthy",
                    tools=list(self._registrations.keys()),
                    heartbeat_interval_s=self._heartbeat_interval_s,
                    registrations=list(self._registrations.values()),
                )

        self._heartbeat_thread = threading.Thread(target=_loop, name="mcprpc-heartbeat", daemon=False)
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        t = self._heartbeat_thread
        if not t:
            return
        self._heartbeat_stop.set()
        try:
            if t.is_alive():
                t.join(timeout=max(0.0, float(self._heartbeat_interval_s) + 6.0))
        except BaseException:
            pass
        self._heartbeat_thread = None

    def publish_module(self, module: Union[str, ModuleType]):
        """
        Discover and publish all valid functions in a module.
        """
        functions = discover_module(module)
        for func in functions:
            self._register_function(func)
            
    def publish_path(self, path: str):
        """
        Discover and publish all valid functions in a directory.
        """
        functions = discover_path(path)
        for func in functions:
            self._register_function(func)
            
    async def _serve_async(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

    async def _serve_sse_app(self, host: str, port: int, sse_path: str, messages_path: str) -> None:
        dns_protect = os.getenv("MCPRPC_SSE_DNS_REBINDING_PROTECTION", "0").strip().lower() in ("1", "true", "yes")
        allowed_hosts_raw = os.getenv("MCPRPC_SSE_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*")
        allowed_hosts = [h.strip() for h in allowed_hosts_raw.split(",") if h.strip()]
        allowed_origins_raw = os.getenv("MCPRPC_SSE_ALLOWED_ORIGINS", "")
        allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=dns_protect,
            allowed_hosts=allowed_hosts if dns_protect else [],
            allowed_origins=allowed_origins if dns_protect else [],
        )
        sse_mount = sse_path.rstrip("/") or "/sse"
        messages_rel = messages_path.rstrip("/") or "/messages"
        transport = SseServerTransport(endpoint=messages_rel, security_settings=security)

        async def sse_endpoint(scope, receive, send):
            async with transport.connect_sse(scope, receive, send) as (read_stream, write_stream):
                await self.server.run(read_stream, write_stream, self.server.create_initialization_options())

        async def health(request):
            payload = {
                "status": "ok",
                "service": self.service_name,
                "runtime": self.runtime,
                "version": "0.1.0",
                "uptime_s": int(time.time() - self._start_ts),
                "tools": len(self._tools),
                "mcp_transport": "sse",
            }
            return JSONResponse(payload)

        async def app(scope, receive, send):
            if scope.get("type") != "http":
                return

            path = scope.get("path") or "/"
            method = (scope.get("method") or "GET").upper()

            if path == "/health" and method == "GET":
                resp = await health(None)
                return await resp(scope, receive, send)

            if path == sse_mount or path == f"{sse_mount}/":
                if method != "GET":
                    return await PlainTextResponse("Method not allowed", status_code=405)(scope, receive, send)
                scope2 = dict(scope)
                scope2["root_path"] = sse_mount
                scope2["path"] = "/"
                return await sse_endpoint(scope2, receive, send)

            if path == f"{sse_mount}{messages_rel}":
                if method != "POST":
                    return await PlainTextResponse("Method not allowed", status_code=405)(scope, receive, send)
                scope2 = dict(scope)
                scope2["root_path"] = sse_mount
                scope2["path"] = messages_rel
                return await transport.handle_post_message(scope2, receive, send)

            return await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)

        config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config=config)
        await server.serve()
            
    def serve(self):
        """
        Start the MCP server.
        """
        if self.mcp_transport == "stdio":
            self.start_heartbeat()
            try:
                asyncio.run(self._serve_async())
            except KeyboardInterrupt:
                try:
                    signal.signal(signal.SIGINT, signal.SIG_IGN)
                except Exception:
                    pass
                return
            finally:
                self.stop_heartbeat()
        elif self.mcp_transport in ("sse", "streamable-http"):
            parsed = urlparse(self.endpoint)
            port = parsed.port or 7002
            sse_path = parsed.path or "/sse/"
            if not sse_path.startswith("/"):
                sse_path = "/" + sse_path
            if not sse_path.endswith("/"):
                sse_path = sse_path + "/"
            host = os.getenv("MCPRPC_BIND_HOST") or "0.0.0.0"
            self.start_heartbeat()
            try:
                asyncio.run(self._serve_sse_app(host=host, port=port, sse_path=sse_path, messages_path="/messages"))
            except KeyboardInterrupt:
                try:
                    signal.signal(signal.SIGINT, signal.SIG_IGN)
                except Exception:
                    pass
                return
            finally:
                self.stop_heartbeat()
        else:
            raise NotImplementedError(f"Transport {self.mcp_transport} not implemented yet.")
