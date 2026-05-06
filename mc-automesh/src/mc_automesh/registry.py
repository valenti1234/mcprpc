import requests
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def build_register_payload(
    service_name: str,
    mesh_id: str,
    runtime: str,
    mcp_transport: str,
    endpoint: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "name": metadata["name"],
        "mesh_id": mesh_id,
        "service_name": service_name,
        "runtime": runtime,
        "transport": "mcp",
        "mcp_transport": mcp_transport,
        "endpoint": endpoint,
        "description": metadata.get("description") or "",
        "inputSchema": metadata.get("inputSchema"),
        "outputSchema": metadata.get("outputSchema"),
        "acl": metadata.get("acl"),
        "cost": metadata.get("cost"),
        "tags": metadata.get("tags"),
        "version": metadata.get("version") or "0.1.0",
        "health": metadata.get("health") or "healthy",
    }

def publish_to_registry(
    registry_url: str,
    service_name: str,
    mesh_id: str,
    runtime: str,
    mcp_transport: str,
    endpoint: str,
    metadata: Dict[str, Any]
) -> bool:
    """
    Publish tool metadata to the MCP RPC registry.
    """
    url = f"{registry_url.rstrip('/')}/register"
    payload = build_register_payload(
        service_name=service_name,
        mesh_id=mesh_id,
        runtime=runtime,
        mcp_transport=mcp_transport,
        endpoint=endpoint,
        metadata=metadata,
    )
        
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(
            "event=registry_publish ok=true name=%s service_name=%s mesh_id=%s",
            metadata.get("name"),
            service_name,
            mesh_id,
        )
        return True
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        logger.warning(
            "event=registry_publish ok=false name=%s service_name=%s mesh_id=%s status=%s error=%s",
            metadata.get("name"),
            service_name,
            mesh_id,
            status,
            str(e),
        )
        return False


def send_heartbeat(
    registry_url: str,
    service_name: str,
    mesh_id: str,
    *,
    runtime: Optional[str] = None,
    health: str = "healthy",
    tools: Optional[list[str]] = None,
    heartbeat_interval_s: Optional[int] = None,
    registrations: Optional[list[Dict[str, Any]]] = None,
) -> bool:
    url = f"{registry_url.rstrip('/')}/heartbeat"
    payload: Dict[str, Any] = {
        "service_name": service_name,
        "mesh_id": mesh_id,
        "health": health,
    }
    if runtime:
        payload["runtime"] = runtime
    if tools:
        payload["tools"] = tools
    if heartbeat_interval_s is not None:
        payload["heartbeat_interval_s"] = heartbeat_interval_s
    if registrations:
        payload["registrations"] = registrations

    try:
        resp = requests.post(url, json=payload, timeout=5)
        resp.raise_for_status()
        logger.info(
            "event=registry_heartbeat ok=true service_name=%s mesh_id=%s health=%s",
            service_name,
            mesh_id,
            health,
        )
        return True
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        logger.warning(
            "event=registry_heartbeat ok=false service_name=%s mesh_id=%s health=%s status=%s error=%s",
            service_name,
            mesh_id,
            health,
            status,
            str(e),
        )
        return False
