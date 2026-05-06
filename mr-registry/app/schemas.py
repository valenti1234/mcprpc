from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import json
from datetime import datetime

class FunctionRegisterRequest(BaseModel):
    name: str
    mesh_id: str
    service_name: str
    runtime: str
    transport: str = "mcp"
    mcp_transport: str
    endpoint: str
    
    description: Optional[str] = None
    inputSchema: Optional[Dict[str, Any]] = None
    outputSchema: Optional[Dict[str, Any]] = None
    acl: Optional[Dict[str, Any]] = None
    cost: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    
    version: Optional[str] = "0.1.0"
    health: Optional[str] = "unknown"


class ResolveRequest(BaseModel):
    name: str
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)


class FunctionResponse(BaseModel):
    id: int
    name: str
    semantic_name: str
    mesh_id: str
    service_name: str
    runtime: str
    transport: str
    mcp_transport: str
    endpoint: str
    description: Optional[str] = None
    
    inputSchema: Optional[Dict[str, Any]] = None
    outputSchema: Optional[Dict[str, Any]] = None
    acl: Optional[Dict[str, Any]] = None
    cost: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    
    version: Optional[str] = None
    health: Optional[str] = None
    heartbeat_interval_s: Optional[int] = None
    last_heartbeat_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record):
        def parse_json(val: Optional[str]) -> Any:
            if not val:
                return None
            try:
                return json.loads(val)
            except Exception:
                return None

        return cls(
            id=record.id,
            name=record.name,
            semantic_name=getattr(record, "semantic_name", record.name),
            mesh_id=getattr(record, "mesh_id", ""),
            service_name=record.service_name,
            runtime=record.runtime,
            transport=record.transport,
            mcp_transport=record.mcp_transport,
            endpoint=record.endpoint,
            description=record.description,
            inputSchema=parse_json(record.input_schema),
            outputSchema=parse_json(record.output_schema),
            acl=parse_json(record.acl),
            cost=parse_json(record.cost),
            tags=parse_json(record.tags),
            version=record.version,
            health=record.health,
            heartbeat_interval_s=getattr(record, "heartbeat_interval_s", None),
            last_heartbeat_at=getattr(record, "last_heartbeat_at", None),
            expires_at=getattr(record, "expires_at", None),
            created_at=record.created_at,
            updated_at=record.updated_at
        )

class ResolveResponse(BaseModel):
    metadata: FunctionResponse
    transport_details: Dict[str, str]

class ActionResponse(BaseModel):
    action: str
    function: FunctionResponse


class HeartbeatRequest(BaseModel):
    service_name: str
    mesh_id: str
    runtime: Optional[str] = None
    health: str = "healthy"
    tools: Optional[List[str]] = None
    heartbeat_interval_s: Optional[int] = None
    registrations: Optional[List[FunctionRegisterRequest]] = None


class HeartbeatResponse(BaseModel):
    ok: bool
    updated: int
    service_name: str
    mesh_id: str
    health: str
    ts: datetime
    heartbeat_interval_s: Optional[int] = None
    expires_at: Optional[datetime] = None
