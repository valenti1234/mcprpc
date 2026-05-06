import httpx
import shlex
import logging
from typing import Optional
from urllib.parse import urlparse, urlunparse
from .schemas import RegistryResolveResponse, EndpointConfig
from .config import settings
from .resilience import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError, retry_async

class RegistryClientError(Exception):
    pass

logger = logging.getLogger(__name__)

_registry_cb = CircuitBreaker(
    CircuitBreakerConfig(
        failure_threshold=settings.cb_failure_threshold,
        recovery_timeout_s=settings.cb_recovery_timeout_s,
        half_open_successes=settings.cb_half_open_successes,
    )
)

def registry_circuit_snapshot() -> dict:
    return _registry_cb.snapshot()

def _normalize_endpoint_url(url: str, mcp_transport: str) -> str:
    if mcp_transport != "sse":
        return url
    if not (url.startswith("http://") or url.startswith("https://")):
        return url
    parsed = urlparse(url)
    path = parsed.path or "/"
    if not path.endswith("/"):
        path = path + "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))

async def resolve_function(function_name: str) -> RegistryResolveResponse:
    """
    Call the registry /resolve endpoint to get the configuration for a function.
    """
    async def _do_call() -> RegistryResolveResponse:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.registry_url}/resolve",
                json={"name": function_name},
                timeout=settings.registry_timeout_s,
            )

            if response.status_code == 404:
                logger.info("event=registry_resolve function=%s ok=false status=404", function_name)
                return RegistryResolveResponse(ok=False, error="Function not found")

            if response.status_code == 410:
                msg = "Function unavailable (expired or unhealthy)"
                try:
                    payload = response.json()
                    detail = payload.get("detail")
                    if isinstance(detail, str) and detail:
                        msg = detail
                    if isinstance(detail, dict):
                        msg = detail.get("error") or msg
                except Exception:
                    pass
                logger.info("event=registry_resolve function=%s ok=false status=410", function_name)
                return RegistryResolveResponse(ok=False, error=msg)

            response.raise_for_status()
            data = response.json()

            transport_details = data.get("transport_details") or {}
            metadata = data.get("metadata") or {}

            mcp_transport = transport_details.get("mcp_transport") or "stdio"
            endpoint_raw = transport_details.get("endpoint") or ""

            endpoint: Optional[EndpointConfig] = None
            if endpoint_raw:
                if mcp_transport in ("sse", "streamable-http") or endpoint_raw.startswith("http://") or endpoint_raw.startswith("https://"):
                    endpoint = EndpointConfig(url=_normalize_endpoint_url(endpoint_raw, mcp_transport))
                else:
                    parts = shlex.split(endpoint_raw)
                    if parts:
                        endpoint = EndpointConfig(command=parts[0], args=parts[1:])

            resp = RegistryResolveResponse(
                ok=True,
                resolved_function=metadata.get("name"),
                semantic_name=metadata.get("semantic_name"),
                mesh_id=metadata.get("mesh_id"),
                service_name=metadata.get("service_name"),
                runtime=metadata.get("runtime"),
                transport=transport_details.get("transport"),
                mcp_transport=mcp_transport,
                endpoint=endpoint,
                acl=metadata.get("acl"),
            )
            logger.info(
                "event=registry_resolve function=%s ok=true mcp_transport=%s endpoint=%s",
                function_name,
                resp.mcp_transport,
                "url" if (resp.endpoint and resp.endpoint.url) else ("stdio" if resp.endpoint else "none"),
            )
            return resp

    try:
        async def _wrapped():
            return await _registry_cb.call(_do_call)

        return await retry_async(
            _wrapped,
            attempts=max(1, settings.retry_attempts),
            base_delay_s=settings.retry_base_delay_s,
            max_delay_s=settings.retry_max_delay_s,
            retry_on=(httpx.TimeoutException, httpx.TransportError, httpx.HTTPError),
            timeout_s=None,
        )
    except CircuitBreakerOpenError as e:
        logger.warning(
            "event=registry_resolve_blocked function=%s reason=%s cb_state=%s",
            function_name,
            str(e),
            _registry_cb.state,
        )
        raise RegistryClientError(f"Failed to resolve function {function_name}: {str(e)}")
    except Exception as e:
        logger.exception("event=registry_resolve_error function=%s", function_name)
        raise RegistryClientError(f"Failed to resolve function {function_name}: {str(e)}")
