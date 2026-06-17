import asyncio
import os
import signal
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    listen_host: str
    listen_port: int
    upstream_host: str
    upstream_port: int
    log_bytes: int
    log_level: str
    reload: bool


def _hexdump(data: bytes, max_bytes: int) -> str:
    b = data[:max_bytes]
    hex_part = " ".join(f"{x:02x}" for x in b)
    ascii_part = "".join(chr(x) if 32 <= x <= 126 else "." for x in b)
    return f"len={len(data)} shown={len(b)} hex={hex_part} ascii={ascii_part}"


def _guess_protocol_prefix(data: bytes) -> str:
    if len(data) >= 3 and data[0] == 0x16 and data[1] == 0x03:
        return "tls_handshake"
    if data.startswith(b"GET ") or data.startswith(b"POST ") or data.startswith(b"HEAD "):
        return "http_request"
    if data.startswith(b"PRI * HTTP/2.0"):
        return "http2_preface"
    return "unknown"


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                return
            writer.write(chunk)
            await writer.drain()
    except (asyncio.CancelledError, ConnectionError):
        raise
    except Exception:
        return


async def _handle_client(cfg: Config, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    peer = client_writer.get_extra_info("peername")
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(cfg.upstream_host, cfg.upstream_port)
    except Exception as e:
        sys.stderr.write(f"event=sniffer_upstream_connect ok=false peer={peer} error={e}\n")
        sys.stderr.flush()
        client_writer.close()
        await client_writer.wait_closed()
        return

    first = b""
    try:
        first = await asyncio.wait_for(client_reader.read(cfg.log_bytes), timeout=0.15)
    except TimeoutError:
        first = b""
    except Exception:
        first = b""

    if first:
        proto = _guess_protocol_prefix(first)
        sys.stderr.write(
            "event=sniffer_incoming peer="
            + str(peer)
            + " proto="
            + proto
            + " "
            + _hexdump(first, cfg.log_bytes)
            + "\n"
        )
        sys.stderr.flush()
        upstream_writer.write(first)
        await upstream_writer.drain()

    c2u = asyncio.create_task(_pipe(client_reader, upstream_writer))
    u2c = asyncio.create_task(_pipe(upstream_reader, client_writer))

    done, pending = await asyncio.wait({c2u, u2c}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        try:
            task.result()
        except Exception:
            pass

    upstream_writer.close()
    client_writer.close()
    try:
        await upstream_writer.wait_closed()
    except Exception:
        pass
    try:
        await client_writer.wait_closed()
    except Exception:
        pass


async def _run(cfg: Config) -> int:
    uvicorn_cmd = [
        "uvicorn",
        "app.main:app",
        "--host",
        cfg.listen_host,
        "--port",
        str(cfg.upstream_port),
        "--log-level",
        cfg.log_level,
    ]
    if cfg.reload:
        uvicorn_cmd.append("--reload")

    sys.stderr.write(
        "event=sniffer_start listen="
        + cfg.listen_host
        + ":"
        + str(cfg.listen_port)
        + " upstream="
        + cfg.upstream_host
        + ":"
        + str(cfg.upstream_port)
        + " reload="
        + str(cfg.reload).lower()
        + "\n"
    )
    sys.stderr.flush()

    proc = subprocess.Popen(uvicorn_cmd, cwd=os.path.dirname(__file__))

    server = await asyncio.start_server(
        lambda r, w: _handle_client(cfg, r, w),
        host=cfg.listen_host,
        port=cfg.listen_port,
        reuse_address=True,
        reuse_port=False,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _stop() -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    async with server:
        await stop_event.wait()

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    return proc.returncode or 0


def main() -> int:
    host = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("PORT", "7000"))
    upstream_port = int(os.getenv("UPSTREAM_PORT", str(port + 1)))
    upstream_host = os.getenv("UPSTREAM_HOST", "127.0.0.1").strip() or "127.0.0.1"
    log_level = os.getenv("LOG_LEVEL", "info").strip() or "info"
    reload_enabled = os.getenv("RELOAD", "1").strip().lower() in ("1", "true", "yes")
    log_bytes = int(os.getenv("SNIFF_BYTES", "2048"))

    cfg = Config(
        listen_host=host,
        listen_port=port,
        upstream_host=upstream_host,
        upstream_port=upstream_port,
        log_bytes=log_bytes,
        log_level=log_level,
        reload=reload_enabled,
    )
    try:
        return asyncio.run(_run(cfg))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

