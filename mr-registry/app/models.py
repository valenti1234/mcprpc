from typing import Optional
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel

class FunctionRecord(SQLModel, table=True):
    __tablename__ = "function_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, description="Function name (not unique across mesh instances)")
    semantic_name: str = Field(index=True, description="Canonical semantic function name for lookup")
    mesh_id: str = Field(index=True, description="Unique id for a mesh instance")
    service_name: str
    runtime: str
    
    transport: str = Field(default="mcp")
    mcp_transport: str = Field(description="stdio | sse | streamable-http")
    endpoint: str
    
    description: Optional[str] = None
    
    # JSON strings
    input_schema: Optional[str] = None
    output_schema: Optional[str] = None
    acl: Optional[str] = None
    cost: Optional[str] = None
    tags: Optional[str] = None
    
    version: Optional[str] = "0.1.0"
    health: Optional[str] = "unknown"

    heartbeat_interval_s: Optional[int] = None
    last_heartbeat_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
