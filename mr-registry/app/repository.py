import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlmodel import Session, select
from app.models import FunctionRecord
from app.schemas import FunctionRegisterRequest

class FunctionRepository:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def semanticize(name: str) -> str:
        parts = [p for p in name.strip().split(".") if p]
        out_parts: list[str] = []
        for part in parts:
            s = part.replace("-", "_").replace(" ", "_")
            buf: list[str] = []
            prev_lower = False
            prev_alpha = False
            for ch in s:
                if ch.isupper():
                    if prev_lower:
                        buf.append("_")
                    buf.append(ch.lower())
                    prev_lower = True
                    prev_alpha = True
                    continue
                if ch.isalnum() or ch == "_":
                    buf.append(ch.lower())
                    prev_lower = ch.islower() or ch.isdigit()
                    prev_alpha = ch.isalpha()
                    continue
                buf.append("_")
                prev_lower = False
                prev_alpha = False
            normalized = "".join(buf)
            normalized = "_".join([p for p in normalized.split("_") if p])
            out_parts.append(normalized)
        return ".".join([p for p in out_parts if p]) or name.strip()

    @staticmethod
    def _coerce_datetime(value: object) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return None
        return None

    def get_by_name(self, name: str) -> Optional[FunctionRecord]:
        statement = (
            select(FunctionRecord)
            .where(FunctionRecord.name == name)
            .order_by(FunctionRecord.updated_at.desc())
        )
        return self.session.exec(statement).first()

    def get_by_name_and_mesh(self, name: str, mesh_id: str) -> Optional[FunctionRecord]:
        statement = select(FunctionRecord).where(
            FunctionRecord.name == name,
            FunctionRecord.mesh_id == mesh_id,
        )
        return self.session.exec(statement).first()

    def get_by_semantic_and_mesh(self, semantic_name: str, mesh_id: str) -> Optional[FunctionRecord]:
        statement = select(FunctionRecord).where(
            FunctionRecord.semantic_name == semantic_name,
            FunctionRecord.mesh_id == mesh_id,
        )
        return self.session.exec(statement).first()

    def list_candidates(self, name: str, now: Optional[datetime] = None) -> List[FunctionRecord]:
        semantic = self.semanticize(name)
        current = now or datetime.now(timezone.utc)
        statement = select(FunctionRecord).where(
            FunctionRecord.semantic_name == semantic,
            FunctionRecord.health != "unavailable",
        )
        records = self.session.exec(statement).all()
        candidates: List[FunctionRecord] = []
        for r in records:
            exp_raw = getattr(r, "expires_at", None)
            exp = self._coerce_datetime(exp_raw)
            if exp is None or exp >= current:
                candidates.append(r)
        return candidates

    def list_by_semantic(self, semantic_name: str) -> List[FunctionRecord]:
        statement = select(FunctionRecord).where(FunctionRecord.semantic_name == semantic_name)
        return self.session.exec(statement).all()

    def list_functions(self, tag: Optional[str] = None, runtime: Optional[str] = None) -> List[FunctionRecord]:
        statement = select(FunctionRecord)
        if runtime:
            statement = statement.where(FunctionRecord.runtime == runtime)
        # Note: filtering by JSON string tag natively in SQLite is a bit tricky,
        # we'll do basic LIKE for tags if provided.
        if tag:
            statement = statement.where(FunctionRecord.tags.contains(f'"{tag}"'))
            
        return self.session.exec(statement).all()

    def register_or_update(self, req: FunctionRegisterRequest) -> Tuple[str, FunctionRecord]:
        semantic_name = self.semanticize(req.name)
        record = self.get_by_semantic_and_mesh(semantic_name, req.mesh_id)
        action = "updated" if record else "created"
        
        if not record:
            record = FunctionRecord(name=req.name, semantic_name=semantic_name, mesh_id=req.mesh_id)
            
        record.mesh_id = req.mesh_id
        record.semantic_name = semantic_name
        record.service_name = req.service_name
        record.runtime = req.runtime
        record.transport = req.transport
        record.mcp_transport = req.mcp_transport
        record.endpoint = req.endpoint
        record.description = req.description
        
        # Serialize JSON fields
        record.input_schema = json.dumps(req.inputSchema) if req.inputSchema is not None else None
        record.output_schema = json.dumps(req.outputSchema) if req.outputSchema is not None else None
        record.acl = json.dumps(req.acl) if req.acl is not None else None
        record.cost = json.dumps(req.cost) if req.cost is not None else None
        record.tags = json.dumps(req.tags) if req.tags is not None else None
        
        record.version = req.version
        record.health = req.health
        record.updated_at = datetime.now(timezone.utc)
        
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        
        return action, record

    def delete(self, name: str) -> bool:
        record = self.get_by_name(name)
        if record:
            self.session.delete(record)
            self.session.commit()
            return True
        return False
        
    def count(self) -> int:
        statement = select(FunctionRecord)
        return len(self.session.exec(statement).all())

    def update_health_for_service(
        self,
        service_name: str,
        mesh_id: str,
        health: str,
        tool_names: Optional[List[str]] = None,
        heartbeat_interval_s: Optional[int] = None,
        last_heartbeat_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> int:
        statement = select(FunctionRecord).where(
            FunctionRecord.service_name == service_name,
            FunctionRecord.mesh_id == mesh_id,
        )

        records = self.session.exec(statement).all()
        now = datetime.now(timezone.utc)
        last_hb = last_heartbeat_at or now
        for r in records:
            r.health = health
            r.updated_at = now
            if heartbeat_interval_s is not None:
                r.heartbeat_interval_s = heartbeat_interval_s
            r.last_heartbeat_at = last_hb
            if expires_at is not None:
                r.expires_at = expires_at
            self.session.add(r)

        self.session.commit()
        return len(records)

    def expire_services(self, now: Optional[datetime] = None) -> tuple[int, list[str]]:
        current = now or datetime.now(timezone.utc)
        statement = select(FunctionRecord).where(
            (FunctionRecord.expires_at.is_not(None)) | (FunctionRecord.health == "unavailable")
        )
        records = self.session.exec(statement).all()
        mesh_ids: set[str] = set()
        for r in records:
            if r.health == "unavailable":
                mesh_ids.add(r.mesh_id)
                continue
            exp = self._coerce_datetime(getattr(r, "expires_at", None))
            if exp is not None and exp < current:
                mesh_ids.add(r.mesh_id)

        if not mesh_ids:
            return 0, []

        delete_stmt = select(FunctionRecord).where(FunctionRecord.mesh_id.in_(sorted(mesh_ids)))
        to_delete = self.session.exec(delete_stmt).all()
        for r in to_delete:
            self.session.delete(r)
        self.session.commit()
        return len(to_delete), sorted(mesh_ids)

    def get_expired_records(self, now: Optional[datetime] = None) -> List[FunctionRecord]:
        current = now or datetime.now(timezone.utc)
        statement = select(FunctionRecord).where(
            FunctionRecord.expires_at.is_not(None),
            FunctionRecord.health != "unavailable",
        )
        records = self.session.exec(statement).all()
        expired: list[FunctionRecord] = []
        for r in records:
            exp = self._coerce_datetime(getattr(r, "expires_at", None))
            if exp is not None and exp < current:
                expired.append(r)
        return expired
