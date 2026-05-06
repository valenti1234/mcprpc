from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class CallContext(BaseModel):
    roles: List[str] = []
    tenant: Optional[str] = None

class CallRequest(BaseModel):
    function: str
    arguments: Dict[str, Any] = {}
    context: CallContext = CallContext()

class CallResponseMeta(BaseModel):
    function: str
    runtime: str
    transport: str
    mcp_transport: str
    durationMs: int
    mesh_id: Optional[str] = None
    service_name: Optional[str] = None
    endpoint: Optional[str] = None
    resolved_function: Optional[str] = None

class CallResponse(BaseModel):
    ok: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    meta: Optional[CallResponseMeta] = None

class ResolveRequest(BaseModel):
    function: str

class EndpointConfig(BaseModel):
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    env: Optional[Dict[str, str]] = None

class RegistryResolveResponse(BaseModel):
    ok: bool
    resolved_function: Optional[str] = None
    semantic_name: Optional[str] = None
    mesh_id: Optional[str] = None
    service_name: Optional[str] = None
    runtime: Optional[str] = None
    transport: Optional[str] = None
    mcp_transport: Optional[str] = None
    endpoint: Optional[EndpointConfig] = None
    acl: Optional[Dict[str, List[str]]] = None
    error: Optional[str] = None
