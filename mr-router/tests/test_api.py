import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.main import app
from app.schemas import RegistryResolveResponse, EndpointConfig

client = TestClient(app)

@pytest.fixture
def mock_resolve_success():
    with patch("app.main.resolve_function", new_callable=AsyncMock) as mock:
        mock.return_value = RegistryResolveResponse(
            ok=True,
            resolved_function="math.sum",
            semantic_name="math.sum",
            runtime="python",
            transport="mcp",
            mcp_transport="sse",
            endpoint=EndpointConfig(url="http://localhost:7002/sse/"),
            acl={"roles": ["admin"]}
        )
        yield mock

@pytest.fixture
def mock_resolve_failure():
    with patch("app.main.resolve_function", new_callable=AsyncMock) as mock:
        mock.return_value = RegistryResolveResponse(
            ok=False,
            error="Function not found"
        )
        yield mock

@pytest.fixture
def mock_execute_tool():
    with patch("app.main.execute_mcp_tool", new_callable=AsyncMock) as mock:
        # Just return a simple dict or object
        class MockContent:
            type = "text"
            text = "10"
        class MockResult:
            content = [MockContent()]
        mock.return_value = MockResult()
        yield mock

def test_call_request_validation():
    # Missing required 'function'
    response = client.post("/call", json={"arguments": {"a": 1}})
    assert response.status_code == 422

def test_registry_resolve_failure(mock_resolve_failure):
    response = client.post("/call", json={"function": "math.sum"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "Function not found"

def test_acl_denied(mock_resolve_success):
    # Context role 'user' is not in allowed 'admin'
    response = client.post("/call", json={
        "function": "math.sum",
        "context": {"roles": ["user"]}
    })
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert "Access denied" in data["error"]

def test_call_success(mock_resolve_success, mock_execute_tool):
    response = client.post("/call", json={
        "function": "math.sum",
        "arguments": {"a": 5, "b": 5},
        "context": {"roles": ["admin"]}
    })
    assert response.status_code == 200
    data = response.json()
    print("RESPONSE DATA:", data)
    assert data["ok"] is True
    assert data["result"]["content"][0]["text"] == "10"
    assert data["meta"]["function"] == "math.sum"
    assert data["meta"]["mcp_transport"] == "sse"
    assert data["meta"]["runtime"] == "python"

    stats_resp = client.get("/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["calls"]["total"] >= 1
    assert stats["calls"]["ok"] >= 1


def test_call_uses_resolved_function(mock_execute_tool):
    with patch("app.main.resolve_function", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = RegistryResolveResponse(
            ok=True,
            resolved_function="billing.calculate_vat",
            semantic_name="billing.calculate_vat",
            runtime="python",
            transport="mcp",
            mcp_transport="sse",
            endpoint=EndpointConfig(url="http://localhost:7002/sse/"),
            acl={"roles": ["admin"]},
        )

        response = client.post("/call", json={
            "function": "billing.calculateVat",
            "arguments": {"amount": 100, "country": "IT"},
            "context": {"roles": ["admin"]}
        })

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["meta"]["function"] == "billing.calculateVat"
        assert mock_execute_tool.await_args.kwargs["function"] == "billing.calculate_vat"
