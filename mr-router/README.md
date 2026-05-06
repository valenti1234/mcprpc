# MCP RPC Router

A lightweight API router that dynamically resolves Model Context Protocol (MCP) functions from a registry and calls them using the standard MCP SDK.

## Features

- Supports dynamically resolving endpoints via `mcprpc-registry`.
- Validates Access Control Lists (ACLs) using Context Roles.
- Executes MCP tools seamlessly using Python `mcp` SDK.
- Supports both `stdio` and `sse` (streamable-http) transports.
- Extensible and modular design with FastAPI.
- Retry + circuit breaker for registry calls and MCP invocations.
- `/health`, `/ready`, `/heartbeat` + request-id (`x-request-id`) and latency logging.

## Project Structure

```
mcprpc-router/
  app/
    main.py           # FastAPI app and /call endpoint
    schemas.py        # Pydantic models for request/response
    registry_client.py# Client to call registry /resolve
    acl.py            # ACL validation logic
    mcp_executor.py   # MCP execution logic via stdio/sse
    config.py         # App configuration
  tests/              # Pytest cases
  pyproject.toml      # Project dependencies
```

## Setup

1. Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[test]"
```

2. Run the tests:
```bash
pytest tests/
```

## Local Demo

Here is how you can test the `mcprpc-router` locally with a registry and a dummy worker:

### 1. Start the Registry

Assuming you have a registry running locally on `http://localhost:7000`:
*(Check your registry project instructions to start it)*

### 2. Register `math.sum` stdio worker

You can register the function in the registry with a curl command:

```bash
curl -X POST http://localhost:7000/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "math.sum",
    "service_name": "math-service",
    "runtime": "python",
    "transport": "mcp",
    "mcp_transport": "stdio",
    "endpoint": "python workers/math.py",
    "description": "Sum numbers",
    "inputSchema": {"type":"object","additionalProperties":true},
    "acl": {
      "roles": ["admin"]
    },
    "tags": ["math"]
  }'
```

### 3. Start the Router

Start the router locally on port 7010:

```bash
REGISTRY_URL="http://localhost:7000" uvicorn app.main:app --port 7010 --reload
```

### 4. POST `/call` `math.sum`

Call the router using the following `curl` command:

```bash
curl -X POST http://localhost:7010/call \
  -H "Content-Type: application/json" \
  -d '{
    "function": "math.sum",
    "arguments": { "a": 10, "b": 20 },
    "context": {
      "roles": ["admin"],
      "tenant": "demo"
    }
  }'
```

**Expected Response:**

```json
{
  "ok": true,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "30"
      }
    ]
  },
  "meta": {
    "function": "math.sum",
    "runtime": "python",
    "transport": "mcp",
    "mcp_transport": "stdio",
    "durationMs": 45
  }
}
```

## System Endpoints

- `GET /health`: includes circuit snapshots (registry + per-endpoint MCP)
- `GET /ready`: checks registry readiness (`GET {REGISTRY_URL}/ready`)
- `GET /heartbeat`: minimal liveness

## Resilience Configuration (env)

- Registry:
  - `REGISTRY_URL` (default `http://localhost:8000`)
  - `REGISTRY_TIMEOUT_S` (default `5.0`)
- Router (timeouts):
  - `ROUTER_TIMEOUT_S` (default `15.0`)
- Retry:
  - `ROUTER_RETRY_ATTEMPTS` (default `3`)
  - `ROUTER_RETRY_BASE_DELAY_S` (default `0.2`)
  - `ROUTER_RETRY_MAX_DELAY_S` (default `2.0`)
- Circuit breaker:
  - `ROUTER_CB_FAILURE_THRESHOLD` (default `5`)
  - `ROUTER_CB_RECOVERY_TIMEOUT_S` (default `30.0`)
  - `ROUTER_CB_HALF_OPEN_SUCCESSES` (default `2`)

## Observability

- Every response includes `x-request-id` (generated if not provided).
- Log format: `request_id=... method=... path=... status=... duration_ms=...`.

## CORS (browser clients)

If you call the router from a browser UI (different origin/port), enable CORS:

- `MCPRPC_CORS_ORIGINS` (comma-separated list of allowed origins), or
- `MCPRPC_CORS_ALLOW_ORIGIN_REGEX` (defaults to allowing `http(s)://localhost:*` and `http(s)://127.0.0.1:*`)

## CLI

Entry point in `app/main.py`:

```bash
python app/main.py run --port 7010
python app/main.py health --url http://localhost:7010
```
