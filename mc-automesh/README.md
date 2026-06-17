# AutoMesh

AutoMesh automatically exposes existing Python functions as MCP tools and publishes them into an MCP RPC registry, without writing manual wrapper code.

- Python: 3.10+
- Transports: `stdio`, `sse` (and `streamable-http` as an alias for `sse`)
- Registry: HTTP `POST /register`

## Why AutoMesh

If you already have a Python service layer (plain functions, or selected class methods), AutoMesh turns them into:

- Discoverable MCP tools (so an agent/client can call them)
- Registry entries (so other systems can find them)  

## Installation

From source (recommended during development):

```bash
cd mc-automesh
python -m venv venv
source venv/bin/activate
pip install -e .
```

Or install dependencies only (when running inside this repo without packaging):

```bash
pip install mcp pydantic requests
```

## Quickstart

```python
from mc_automesh import AutoMesh

mesh = AutoMesh(
    service_name="billing-service",
    registry_url="http://127.0.0.1:7000",
    runtime="python",
    mcp_transport="stdio",
)

mesh.publish_module("billing")
mesh.serve()
```

This will:

- Import `billing`
- Discover eligible functions
- Generate JSON Schema for each tool’s inputs from type hints
- Publish each tool to the registry at `http://127.0.0.1:7000/register`
- Start an MCP server over stdio exposing each tool under the same name that was published

## How It Works

### Function Discovery Rules

AutoMesh discovers functions using `inspect` + `importlib`:

Included:

- Top-level module functions
- Class methods (supported, but only if they pass the same filters)

Ignored automatically:

- Private functions: names starting with `_`
- Imported symbols: functions whose `__module__` does not match the scanned module
- Lambdas
- Any function decorated with `@ignore`

### Tool Naming

Default tool name format:

```text
<module_name>.<function_name>
```

Example:

```text
billing.calculate_vat
```

You can override the tool name via `@expose(name="...")`.

### Metadata Extraction

For each discovered function AutoMesh extracts:

- Name: default `<module>.<function>` or overridden via `@expose`
- Description: function docstring (`inspect.getdoc`)
- Input schema: derived from signature + type hints (Pydantic JSON Schema)
- Return type: extracted from the return annotation (stored as a string)
- Optional metadata: `acl`, `tags` from `@expose`

Input schema generation uses the function signature:

- Parameters with defaults are optional
- Parameters without defaults become required
- `self` / `cls` parameters are excluded

## Decorators

### `@expose`

Use `@expose` to override the published tool name and attach metadata:

```python
from mc_automesh import expose

@expose(
    name="billing.vat",
    acl={"roles": ["admin"]},
    tags=["billing"],
)
def custom_vat(amount: float) -> float:
    """Calculates a custom VAT."""
    return amount * 0.25
```

### `@ignore`

Use `@ignore` to prevent a function from being exported:

```python
from mc_automesh import ignore

@ignore
def internal_helper() -> bool:
    return True
```

## Publishing to the Registry

For every discovered function, AutoMesh sends:

```http
POST {registry_url}/register
Content-Type: application/json
```

Payload fields:

- `name`
- `service_name`
- `runtime`
- `transport` (`mcp`)
- `mcp_transport`
- `endpoint`
- Optional: `description`, `inputSchema`, `outputSchema`, `acl`, `cost`, `tags`, `version`, `health`

If `registry_url` is empty, publishing is skipped.

## MCP Exposure

AutoMesh uses the official `mcp` Python SDK server implementation and registers a tool for each discovered function.

- MCP tool name matches the registry tool name exactly
- Tool calls invoke the underlying Python function directly
- Return values are currently serialized as a text response using `str(result)`
- `async def` functions are supported

## System Tools (built-in)

AutoMesh always registers these built-in tools:

- `system.health`: returns status + uptime + number of tools
- `system.heartbeat`: sends a heartbeat to the registry

These tools are also published to the registry (so they will appear in `GET /functions`).

## Heartbeat (opt-in)

To send periodic heartbeats to the registry, set:

```bash
MCPRPC_HEARTBEAT_INTERVAL_S=5
```

The payload sent to the registry is:

```json
{
  "service_name": "billing-service",
  "runtime": "python",
  "health": "healthy",
  "tools": ["system.health", "system.heartbeat", "..."]
}
```

## API Reference

### `AutoMesh(...)`

```python
AutoMesh(
    service_name: str,
    registry_url: str,
    runtime: str = "python",
    mcp_transport: str = "stdio",
    endpoint: str | None = None,
)
```

If `endpoint` is not provided, AutoMesh defaults to the current process command line (based on `sys.executable` + `sys.argv`) so the registry has a runnable stdio entrypoint.

### `publish_module(module)`

Publish a module by:

- String import path (e.g. `"myapp.services.billing"`)
- Imported module object

```python
mesh.publish_module("myapp.services.billing")
```

### `publish_path(path)`

Recursively scan a folder for `.py` files and attempt to import them as modules (relative to the provided directory).

```python
mesh.publish_path("./myapp/services")
```

Note: Importing modules executes module-level code. Keep side effects minimal in scanned modules.

### `serve()`

Start the MCP server. Currently implemented transport:

- `stdio`: `mesh.serve()`

## Example

This repo includes an example module with three public functions and additional functions that are intentionally excluded:

- Included: `calculate_vat`, `custom_vat`, `generate_invoice`
- Excluded: `_private_func` (private), `internal_helper` (`@ignore`)

Files:

- `example/billing.py`
- `example/main.py`

Run the example:

```bash
cd mc-automesh
source venv/bin/activate
PYTHONPATH=src python example/main.py
```

## Testing

```bash
cd mc-automesh
source venv/bin/activate
PYTHONPATH=src pytest
```

The test suite covers:

- Function discovery rules
- Docstring extraction
- JSON Schema generation
- Registry publishing behavior
- `@ignore` and `@expose` behavior

## Development Notes

- Keep functions typed to get high-quality input schemas.
- If you want shorter tool names like `billing.calculate_vat`, ensure the module is imported as `billing` (module name affects the default tool name).

## CLI

Minimal CLI via module runner:

```bash
python -m mc_automesh publish-path --service-name billing-service --registry-url http://127.0.0.1:7000 --path ./myapp/services
python -m mc_automesh publish-module --service-name billing-service --registry-url http://127.0.0.1:7000 --module myapp.services.billing
python -m mc_automesh serve --service-name billing-service --registry-url http://127.0.0.1:7000
python -m mc_automesh run --service-name billing-service --registry-url http://127.0.0.1:7000 --path ./myapp/services
```
