import os
import sys
import logging
import argparse
import socket
import subprocess
import time
import signal
from dataclasses import dataclass
from pathlib import Path

# Add the src folder to sys.path for testing example without installing
SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = (SCRIPT_DIR / ".." / "src").resolve()
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from mc_automesh import AutoMesh

logging.basicConfig(level=logging.INFO)


def _get_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _serve_one(service_name: str, module_name: str, registry_url: str, runtime: str, mcp_transport: str, endpoint: str | None):
    mesh = AutoMesh(
        service_name=service_name,
        registry_url=registry_url,
        runtime=runtime,
        mcp_transport=mcp_transport,
        endpoint=endpoint,
    )
    mod = __import__(module_name)
    mesh.publish_module(mod)
    mesh.serve()
    logging.info("%s published", service_name)


def _spawn_service(
    *,
    service_name: str,
    module_name: str,
    registry_url: str,
    runtime: str,
    mcp_transport: str,
    endpoint: str | None,
) -> tuple[subprocess.Popen, str | None]:
    env = dict(os.environ)
    env["AUTOMESH_REGISTRY_URL"] = registry_url
    env["AUTOMESH_RUNTIME"] = runtime
    env["AUTOMESH_TRANSPORT"] = mcp_transport

    used_endpoint: str | None = endpoint
    if endpoint:
        env["AUTOMESH_ENDPOINT"] = endpoint
    elif mcp_transport in ("sse", "streamable-http"):
        port = _get_free_port()
        used_endpoint = f"http://localhost:{port}/sse/"
        env["AUTOMESH_ENDPOINT"] = used_endpoint
    else:
        env.pop("AUTOMESH_ENDPOINT", None)

    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--service-name",
        service_name,
        "--module",
        module_name,
    ]
    return subprocess.Popen(cmd, cwd=str(SCRIPT_DIR), env=env), used_endpoint


def _stop_process(p: subprocess.Popen) -> None:
    try:
        if p.poll() is None:
            p.terminate()
    except Exception:
        return
    try:
        p.wait(timeout=5)
        return
    except Exception:
        pass
    try:
        if p.poll() is None:
            p.kill()
    except Exception:
        return
    try:
        p.wait(timeout=5)
    except Exception:
        pass


@dataclass
class _Service:
    service_name: str
    module_name: str
    endpoint: str | None
    module_file: Path | None
    module_mtime_ns: int | None
    proc: subprocess.Popen


def _module_file_for(module_name: str) -> Path | None:
    p = (SCRIPT_DIR / f"{module_name}.py").resolve()
    return p if p.exists() else None


def _mtime_ns(p: Path | None) -> int | None:
    if p is None:
        return None
    try:
        return int(p.stat().st_mtime_ns)
    except Exception:
        return None


def _start_service(
    *,
    service_name: str,
    module_name: str,
    registry_url: str,
    runtime: str,
    mcp_transport: str,
    endpoint: str | None,
) -> _Service:
    proc, used_endpoint = _spawn_service(
        service_name=service_name,
        module_name=module_name,
        registry_url=registry_url,
        runtime=runtime,
        mcp_transport=mcp_transport,
        endpoint=endpoint,
    )
    module_file = _module_file_for(module_name)
    return _Service(
        service_name=service_name,
        module_name=module_name,
        endpoint=used_endpoint,
        module_file=module_file,
        module_mtime_ns=_mtime_ns(module_file),
        proc=proc,
    )


def _respawn(
    svc: _Service,
    *,
    registry_url: str,
    runtime: str,
    mcp_transport: str,
) -> _Service:
    _stop_process(svc.proc)
    return _start_service(
        service_name=svc.service_name,
        module_name=svc.module_name,
        registry_url=registry_url,
        runtime=runtime,
        mcp_transport=mcp_transport,
        endpoint=svc.endpoint,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-url", default=os.environ.get("AUTOMESH_REGISTRY_URL", "http://localhost:7000"))
    parser.add_argument("--runtime", default=os.environ.get("AUTOMESH_RUNTIME", "python"))
    parser.add_argument("--mcp-transport", default=os.environ.get("AUTOMESH_TRANSPORT", "sse"))
    parser.add_argument("--endpoint", default=os.environ.get("AUTOMESH_ENDPOINT", None))
    parser.add_argument("--service-name", default=None)
    parser.add_argument("--module", default=None)
    args = parser.parse_args()

    if args.service_name and args.module:
        _serve_one(
            service_name=args.service_name,
            module_name=args.module,
            registry_url=args.registry_url,
            runtime=args.runtime,
            mcp_transport=args.mcp_transport,
            endpoint=args.endpoint,
        )
        return

    stop = {"requested": False}

    def _request_stop(_signum=None, _frame=None):
        stop["requested"] = True

    try:
        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)
    except Exception:
        pass

    services: list[_Service] = [
        _start_service(
            service_name="billing-service",
            module_name="billing",
            registry_url=args.registry_url,
            runtime=args.runtime,
            mcp_transport=args.mcp_transport,
            endpoint=None,
        ),
        _start_service(
            service_name="testing-service",
            module_name="testing",
            registry_url=args.registry_url,
            runtime=args.runtime,
            mcp_transport=args.mcp_transport,
            endpoint=None,
        ),
        _start_service(
            service_name="log-service",
            module_name="log",
            registry_url=args.registry_url,
            runtime=args.runtime,
            mcp_transport="streamable-http",
            endpoint=None,
        ),
    ]

    try:
        while not stop["requested"]:
            for i, svc in enumerate(list(services)):
                restarted = False
                if svc.proc.poll() is not None:
                    services[i] = _respawn(
                        svc,
                        registry_url=args.registry_url,
                        runtime=args.runtime,
                        mcp_transport=args.mcp_transport,
                    )
                    restarted = True

                cur_mtime = _mtime_ns(svc.module_file)
                if cur_mtime is not None and svc.module_mtime_ns is not None and cur_mtime != svc.module_mtime_ns:
                    services[i] = _respawn(
                        services[i],
                        registry_url=args.registry_url,
                        runtime=args.runtime,
                        mcp_transport=args.mcp_transport,
                    )
                    restarted = True

                if restarted:
                    services[i].module_mtime_ns = _mtime_ns(services[i].module_file)

            time.sleep(0.5)
    finally:
        for svc in services:
            _stop_process(svc.proc)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
