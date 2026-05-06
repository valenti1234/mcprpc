import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.main import app
from app.db import get_session
from app.models import FunctionRecord
from app.repository import FunctionRepository

# Use in-memory SQLite for testing
engine = create_engine(
    "sqlite://", 
    connect_args={"check_same_thread": False}, 
    poolclass=StaticPool
)

def get_session_override():
    with Session(engine) as session:
        yield session

app.dependency_overrides[get_session] = get_session_override

@pytest.fixture(name="client")
def client_fixture():
    SQLModel.metadata.create_all(engine)
    yield TestClient(app)
    SQLModel.metadata.drop_all(engine)

def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert data["service"] == "mcprpc-registry"
    assert "uptime_s" in data

def test_register_function(client: TestClient):
    payload = {
        "name": "math.sum",
        "mesh_id": "mesh-1",
        "service_name": "math-service",
        "runtime": "python",
        "transport": "mcp",
        "mcp_transport": "stdio",
        "endpoint": "python workers/math.py",
        "description": "Calculates sum of numbers",
        "inputSchema": {"type": "object"},
        "tags": ["math", "calc"]
    }
    response = client.post("/register", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "created"
    assert data["function"]["name"] == "math.sum"
    assert data["function"]["tags"] == ["math", "calc"]

def test_update_function(client: TestClient):
    payload = {
        "name": "math.sum",
        "mesh_id": "mesh-1",
        "service_name": "math-service",
        "runtime": "python",
        "transport": "mcp",
        "mcp_transport": "stdio",
        "endpoint": "python workers/math.py"
    }
    # Create first
    client.post("/register", json=payload)
    
    # Update
    payload["endpoint"] = "python workers/math_v2.py"
    response = client.post("/register", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "updated"
    assert data["function"]["endpoint"] == "python workers/math_v2.py"

def test_list_functions(client: TestClient):
    payload = {
        "name": "math.sum",
        "mesh_id": "mesh-1",
        "service_name": "math-service",
        "runtime": "python",
        "mcp_transport": "stdio",
        "endpoint": "python workers/math.py",
        "tags": ["math"]
    }
    client.post("/register", json=payload)
    
    payload2 = {
        "name": "str.upper",
        "mesh_id": "mesh-2",
        "service_name": "string-service",
        "runtime": "node",
        "mcp_transport": "stdio",
        "endpoint": "node workers/str.js",
        "tags": ["string"]
    }
    client.post("/register", json=payload2)

    # List all
    res = client.get("/functions")
    assert res.status_code == 200
    assert len(res.json()) == 2
    
    # Filter by runtime
    res = client.get("/functions?runtime=node")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == "str.upper"

    # Filter by tag
    res = client.get("/functions?tag=math")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == "math.sum"

def test_resolve_function(client: TestClient):
    payload = {
        "name": "math.sum",
        "mesh_id": "mesh-1",
        "service_name": "math-service",
        "runtime": "python",
        "mcp_transport": "stdio",
        "endpoint": "python workers/math.py"
    }
    client.post("/register", json=payload)
    
    resolve_payload = {
        "name": "math.sum",
        "context": {}
    }
    res = client.post("/resolve", json=resolve_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["name"] == "math.sum"
    assert data["transport_details"]["mcp_transport"] == "stdio"
    assert data["transport_details"]["endpoint"] == "python workers/math.py"

def test_resolve_round_robin(client: TestClient):
    payload1 = {
        "name": "rr.test",
        "mesh_id": "mesh-1",
        "service_name": "svc",
        "runtime": "python",
        "mcp_transport": "stdio",
        "endpoint": "python workers/a.py"
    }
    payload2 = {
        "name": "rr.test",
        "mesh_id": "mesh-2",
        "service_name": "svc",
        "runtime": "python",
        "mcp_transport": "stdio",
        "endpoint": "python workers/b.py"
    }
    client.post("/register", json=payload1)
    client.post("/register", json=payload2)

    resolve_payload = {
        "name": "rr.test",
        "context": {}
    }

    res1 = client.post("/resolve", json=resolve_payload)
    res2 = client.post("/resolve", json=resolve_payload)
    res3 = client.post("/resolve", json=resolve_payload)

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res3.status_code == 200

    ep1 = res1.json()["transport_details"]["endpoint"]
    ep2 = res2.json()["transport_details"]["endpoint"]
    ep3 = res3.json()["transport_details"]["endpoint"]

    assert ep1 == "python workers/a.py"
    assert ep2 == "python workers/b.py"
    assert ep3 == "python workers/a.py"

def test_delete_function(client: TestClient):
    payload = {
        "name": "math.sum",
        "mesh_id": "mesh-1",
        "service_name": "math-service",
        "runtime": "python",
        "mcp_transport": "stdio",
        "endpoint": "python workers/math.py"
    }
    client.post("/register", json=payload)
    
    res = client.delete("/functions/math.sum")
    assert res.status_code == 200
    
    res = client.get("/functions/math.sum")
    assert res.status_code == 404

def test_expired_mesh_is_removed_from_db(client: TestClient):
    payload1 = {
        "name": "math.sum",
        "mesh_id": "mesh-expired",
        "service_name": "math-service",
        "runtime": "python",
        "mcp_transport": "stdio",
        "endpoint": "python workers/math.py",
    }
    payload2 = {
        "name": "math.mul",
        "mesh_id": "mesh-expired",
        "service_name": "math-service",
        "runtime": "python",
        "mcp_transport": "stdio",
        "endpoint": "python workers/math.py",
    }
    payload_ok = {
        "name": "str.upper",
        "mesh_id": "mesh-ok",
        "service_name": "string-service",
        "runtime": "node",
        "mcp_transport": "stdio",
        "endpoint": "node workers/str.js",
    }
    client.post("/register", json=payload1)
    client.post("/register", json=payload2)
    client.post("/register", json=payload_ok)

    with Session(engine) as session:
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        statement = select(FunctionRecord).where(FunctionRecord.mesh_id == "mesh-expired")
        records = session.exec(statement).all()
        assert len(records) == 2
        for r in records:
            r.expires_at = past
            session.add(r)
        session.commit()

        repo = FunctionRepository(session)
        deleted_count, deleted_meshes = repo.expire_services(now=datetime.now(timezone.utc))
        assert deleted_count == 2
        assert deleted_meshes == ["mesh-expired"]

    res = client.get("/functions")
    assert res.status_code == 200
    names = [x["name"] for x in res.json()]
    assert "str.upper" in names
    assert "math.sum" not in names
    assert "math.mul" not in names
