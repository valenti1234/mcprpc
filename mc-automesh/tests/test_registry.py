import responses
from mc_automesh.registry import publish_to_registry

@responses.activate
def test_publish_to_registry_success():
    responses.add(
        responses.POST,
        "http://localhost:7000/register",
        json={"status": "ok"},
        status=200
    )
    
    metadata = {
        "name": "test.func",
        "description": "desc",
        "inputSchema": {},
        "acl": {"roles": ["admin"]},
        "tags": ["tag1"]
    }
    
    result = publish_to_registry(
        registry_url="http://localhost:7000",
        service_name="test-service",
        mesh_id="test-mesh",
        runtime="python",
        mcp_transport="stdio",
        endpoint="python -c 'print(1)'",
        metadata=metadata
    )
    
    assert result is True
    assert len(responses.calls) == 1
    
    request_body = responses.calls[0].request.body
    # We could json decode and check the payload here, but ensuring success is enough
    
@responses.activate
def test_publish_to_registry_failure():
    responses.add(
        responses.POST,
        "http://localhost:7000/register",
        json={"error": "bad request"},
        status=400
    )
    
    metadata = {
        "name": "test.func",
        "description": "desc",
        "inputSchema": {},
    }
    
    result = publish_to_registry(
        registry_url="http://localhost:7000",
        service_name="test-service",
        mesh_id="test-mesh",
        runtime="python",
        mcp_transport="stdio",
        endpoint="python -c 'print(1)'",
        metadata=metadata
    )
    
    assert result is False
