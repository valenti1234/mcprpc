import os
import sys
import importlib.util
from pathlib import Path

# Add the src folder to sys.path for testing example without installing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from mc_automesh import AutoMesh

def main():
    service_name = os.environ.get("AUTOMESH_SERVICE_NAME", "math-service")
    registry_url = os.environ.get("AUTOMESH_REGISTRY_URL", "http://localhost:7000")
    runtime = os.environ.get("AUTOMESH_RUNTIME", "python")
    mcp_transport = os.environ.get("AUTOMESH_TRANSPORT", "sse")
    endpoint = os.environ.get("AUTOMESH_ENDPOINT", None)

    mesh = AutoMesh(
        service_name=service_name,
        registry_url=registry_url,
        runtime=runtime,
        mcp_transport=mcp_transport,
        endpoint=endpoint,
    )

    import math
    mesh.publish_module(math)
  
    #math_path = Path(__file__).resolve().parent / "math.py"
    #spec = importlib.util.spec_from_file_location("example_math", str(math_path))
    #if spec is None or spec.loader is None:
    #    raise RuntimeError(f"Failed to load module from {math_path}")
    #mod = importlib.util.module_from_spec(spec)
    #spec.loader.exec_module(mod)
    #mesh.publish_module(mod)
    
    # Or by path
    # mesh.publish_path(os.path.dirname(__file__))

    # Starts MCP server
    mesh.serve()

if __name__ == "__main__":
    main()
