import os
import time
import asyncio
import logging
import traceback
import shutil
from dataclasses import dataclass
from typing import Any, Dict, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from .schemas import EndpointConfig
from .config import settings
from .resilience import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError, retry_async

class MCPExecutorError(Exception):
    pass

logger = logging.getLogger(__name__)

def _resolve_command(command: str) -> str:
    if "/" in command:
        if os.path.exists(command) and os.access(command, os.X_OK):
            return command
        raise MCPExecutorError(f"Command not executable: {command}")

    found = shutil.which(command)
    if found:
        return found

    if command == "python":
        fallback = shutil.which("python3")
        if fallback:
            logger.warning("event=stdio_command_fallback from=python to=python3")
            return fallback

    raise MCPExecutorError(f"Command not found in PATH: {command}")

def _format_exception(e: BaseException) -> str:
    if isinstance(e, BaseExceptionGroup):
        parts: list[str] = []
        for sub in e.exceptions:
            parts.append(_format_exception(sub))
        return " | ".join(p for p in parts if p) or str(e)
    if isinstance(e, Exception):
        msg = str(e)
        if msg:
            return msg
        return repr(e)
    return repr(e)

_cb_config = CircuitBreakerConfig(
    failure_threshold=settings.cb_failure_threshold,
    recovery_timeout_s=settings.cb_recovery_timeout_s,
    half_open_successes=settings.cb_half_open_successes,
)
_endpoint_breakers: dict[str, CircuitBreaker] = {}

def mcp_circuits_snapshot() -> dict[str, dict]:
    return {k: cb.snapshot() for k, cb in _endpoint_breakers.items()}

def _breaker_for(key: str) -> CircuitBreaker:
    cb = _endpoint_breakers.get(key)
    if cb is None:
        cb = CircuitBreaker(_cb_config)
        _endpoint_breakers[key] = cb
    return cb


@dataclass
class _StdioCall:
    function: str
    arguments: Dict[str, Any]
    fut: asyncio.Future


@dataclass
class _StdioWorker:
    key: str
    server_params: StdioServerParameters
    queue: asyncio.Queue
    task: asyncio.Task
    last_used_ts: float


_stdio_workers: dict[str, _StdioWorker] = {}
_stdio_lock = asyncio.Lock()


def start_stdio_pool() -> None:
    if not settings.stdio_persistent:
        return
    return


async def shutdown_stdio_pool() -> None:
    async with _stdio_lock:
        workers = list(_stdio_workers.values())
        _stdio_workers.clear()
    for w in workers:
        try:
            w.queue.put_nowait(None)
        except Exception:
            pass
    for w in workers:
        try:
            await w.task
        except Exception:
            logger.exception("event=stdio_pool_shutdown_error key=%s", w.key)


def _stdio_key(command: str, args: list[str], env: dict[str, str]) -> str:
    env_items = sorted(env.items())
    env_sig = "|".join([f"{k}={v}" for k, v in env_items])
    return f"stdio:{command}:{' '.join(args)}:{env_sig}"


async def _stdio_worker_loop(key: str, server_params: StdioServerParameters, queue: asyncio.Queue) -> None:
    idle_timeout = float(getattr(settings, "stdio_idle_timeout_s", 60.0))
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                while True:
                    try:
                        if idle_timeout > 0:
                            item = await asyncio.wait_for(queue.get(), timeout=idle_timeout)
                        else:
                            item = await queue.get()
                    except asyncio.TimeoutError:
                        break

                    if item is None:
                        break

                    if isinstance(item, _StdioCall):
                        try:
                            result = await session.call_tool(item.function, item.arguments)
                            if not item.fut.done():
                                item.fut.set_result(result)
                        except Exception as e:
                            if not item.fut.done():
                                item.fut.set_exception(e)
    except Exception as e:
        while True:
            try:
                item = queue.get_nowait()
            except Exception:
                break
            if isinstance(item, _StdioCall) and not item.fut.done():
                item.fut.set_exception(e)
        raise
    finally:
        while True:
            try:
                item = queue.get_nowait()
            except Exception:
                break
            if isinstance(item, _StdioCall) and not item.fut.done():
                item.fut.set_exception(MCPExecutorError("Worker closed"))


async def _stop_stdio_worker(worker: _StdioWorker) -> None:
    try:
        worker.queue.put_nowait(None)
    except Exception:
        pass
    try:
        await worker.task
    except Exception:
        logger.exception("event=stdio_worker_stop_error key=%s", worker.key)


async def _get_or_start_stdio_worker(key: str, server_params: StdioServerParameters) -> _StdioWorker:
    to_stop: Optional[_StdioWorker] = None
    async with _stdio_lock:
        existing = _stdio_workers.get(key)
        if existing is not None and not existing.task.done():
            existing.last_used_ts = time.time()
            return existing
        if existing is not None and existing.task.done():
            _stdio_workers.pop(key, None)

        max_sessions = int(getattr(settings, "stdio_max_sessions", 64))
        if max_sessions > 0 and len(_stdio_workers) >= max_sessions:
            oldest = min(_stdio_workers.values(), key=lambda w: w.last_used_ts)
            _stdio_workers.pop(oldest.key, None)
            to_stop = oldest

        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(_stdio_worker_loop(key, server_params, queue))
        worker = _StdioWorker(
            key=key,
            server_params=server_params,
            queue=queue,
            task=task,
            last_used_ts=time.time(),
        )
        _stdio_workers[key] = worker

    if to_stop is not None:
        await _stop_stdio_worker(to_stop)

    return worker

async def execute_mcp_tool(
    mcp_transport: str,
    endpoint: Optional[EndpointConfig],
    function: str,
    arguments: Dict[str, Any]
) -> Any:
    try:
        async def _do_call() -> Any:
            if mcp_transport == "stdio":
                raise MCPExecutorError(
                    "stdio transport is not supported by the router (router must not spawn workers). "
                    "Use streamable-http/sse worker endpoints instead."
                )

            if mcp_transport in ("sse", "streamable-http"):
                if endpoint is None or not endpoint.url:
                    raise MCPExecutorError(f"Missing url for {mcp_transport} transport")

                async with sse_client(endpoint.url) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        return await session.call_tool(function, arguments)

            raise MCPExecutorError(f"Unsupported MCP transport: {mcp_transport}")

        key = ""
        if mcp_transport == "stdio":
            if endpoint is None or not endpoint.command:
                key = "stdio:missing"
            else:
                resolved_command = _resolve_command(endpoint.command)
                env = os.environ.copy()
                if endpoint.env:
                    env.update(endpoint.env)
                key = _stdio_key(resolved_command, endpoint.args or [], env)
        else:
            key = f"{mcp_transport}:{endpoint.url if endpoint else ''}"

        cb = _breaker_for(key)

        async def _wrapped():
            return await cb.call(_do_call)

        result = await retry_async(
            _wrapped,
            attempts=max(1, settings.retry_attempts),
            base_delay_s=settings.retry_base_delay_s,
            max_delay_s=settings.retry_max_delay_s,
            retry_on=(asyncio.TimeoutError, MCPExecutorError, OSError),
            timeout_s=settings.router_timeout_s,
        )
        logger.info("event=mcp_call ok=true function=%s key=%s", function, key)
        return result

    except CircuitBreakerOpenError as e:
        logger.warning("event=mcp_call_blocked function=%s key=%s reason=%s", function, key if "key" in locals() else "", str(e))
        raise MCPExecutorError(f"MCP Tool Execution failed: {_format_exception(e)}")
    except Exception as e:
        logger.exception("event=mcp_call_error function=%s key=%s", function, key if "key" in locals() else "")
        reason = _format_exception(e)
        if reason == "Connection closed" and "key" in locals():
            reason = f"{reason} (endpoint={key})"
        raise MCPExecutorError(f"MCP Tool Execution failed: {reason}")
