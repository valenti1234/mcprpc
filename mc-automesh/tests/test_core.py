import asyncio
import pytest
from mc_automesh import AutoMesh
from mc_automesh.decorators import expose, ignore

def test_automesh_init():
    mesh = AutoMesh("test-service", "http://localhost:7000")
    assert mesh.service_name == "test-service"
    assert mesh.registry_url == "http://localhost:7000"
    assert mesh.runtime == "python"
    assert mesh.mcp_transport == "stdio"

def sample_function(x: int) -> int:
    return x * 2

def test_automesh_register():
    mesh = AutoMesh("test-service", "") # Empty registry_url to skip publishing
    mesh._register_function(sample_function)
    
    assert "test_core.sample_function" in mesh._functions
    tool = next(t for t in mesh._tools if t.name == "test_core.sample_function")
    assert tool.description == "Tool test_core.sample_function"

@pytest.mark.asyncio
async def test_automesh_execution():
    mesh = AutoMesh("test-service", "")
    mesh._register_function(sample_function)
    
    # We simulate MCP call manually by getting the registered func
    func = mesh._functions["test_core.sample_function"]
    assert func(x=5) == 10
