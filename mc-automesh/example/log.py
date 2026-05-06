from mc_automesh import expose, ignore
import sys
import logging
import os
from pathlib import Path
from datetime import datetime, timezone

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)

logger = logging.getLogger(__name__)

_FILE_HANDLERS: dict[str, logging.Handler] = {}


def _log_file_path(path: str | None = None) -> str:
    if path and path.strip():
        return path.strip()
    env_path = os.getenv("AUTOMESH_LOG_FILE") or os.getenv("LOG_FILE")
    if env_path and env_path.strip():
        return env_path.strip()
    return str((Path(__file__).resolve().parent / "example.log").resolve())


def _ensure_file_handler(path: str) -> None:
    p = Path(path).expanduser()
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    key = str(p.resolve())
    if key in _FILE_HANDLERS:
        return
    handler = logging.FileHandler(key, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    _FILE_HANDLERS[key] = handler


def log_write(message: str, level: str = "info", path: str | None = None) -> dict:
    log_path = _log_file_path(path)
    _ensure_file_handler(log_path)
    lvl = (level or "info").strip().lower()
    if lvl == "debug":
        logger.debug(message)
    elif lvl == "warning" or lvl == "warn":
        logger.warning(message)
    elif lvl == "error":
        logger.error(message)
    else:
        logger.info(message)
    return {
        "ok": True,
        "path": log_path,
        "level": lvl,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def log_tail(lines: int = 50, path: str | None = None) -> dict:
    log_path = _log_file_path(path)
    p = Path(log_path).expanduser()
    if not p.exists():
        return {"ok": False, "path": log_path, "error": "log file not found"}
    try:
        n = int(lines)
    except Exception:
        n = 50
    n = max(1, min(n, 5000))
    content = p.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = content[-n:]
    return {"ok": True, "path": log_path, "lines": len(tail), "text": "\n".join(tail)}

def delete_log_file(path: str | None = None) -> dict:
    log_path = _log_file_path(path)
    p = Path(log_path).expanduser()
    if p.exists():
        p.unlink()
    return {"ok": True, "path": log_path}