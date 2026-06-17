# mcprpc-registry

MCP-native function registry for polyglot function mesh systems.

## What is mcprpc registry

The `mcprpc-registry` is a lightweight, Python-based registry service designed specifically for the `mcprpc` ecosystem. It acts as a central repository for function metadata, allowing services to discover and invoke functions across different runtimes (Python, Node, etc.) using the Model Context Protocol (MCP) as the primary transport.

Unlike a traditional API registry, this registry stores functions exposed via MCP, including their transport details, input/output schemas, Access Control Lists (ACLs), and other metadata.

## Why MCP-native

Using MCP as the native transport provides a standardized way for functions to communicate across boundaries without tight coupling to specific network protocols like HTTP or gRPC out of the box. By storing MCP transport details (`stdio`, `sse`, `streamable-http`), the registry allows routers and clients to seamlessly establish connections to the appropriate workers regardless of their underlying implementation.

## How it works

1. **Registration**: A worker or service registers its functions with the registry via `POST /register`, providing details like its runtime, endpoint, and MCP transport type.
2. **Discovery**: A client or router queries the registry via `GET /functions` or `POST /resolve` to find the target function's metadata and transport details.
3. **Invocation**: The client uses the resolved transport details to connect directly to the worker and invoke the function using the MCP protocol.

## System Endpoints

- `GET /health`: process + DB status (`degraded` if DB is not available)
- `GET /ready`: readiness (503 if DB is not ready)
- `POST /heartbeat`: updates `health` (and `updated_at`) for the functions registered under `service_name`
- `GET /heartbeats`: last heartbeat received per service (in memory)

### Heartbeat

Request:

```json
{
  "service_name": "billing-service",
  "runtime": "python",
  "health": "healthy",
  "tools": ["billing.createInvoice", "billing.calculateVat"]
}
```

Note:

- `tools` is optional: if present, only those tools are updated; if omitted, all functions for `service_name` are updated.
- For the update to take effect, functions must already have been registered via `POST /register`.

## Quickstart

### Run server

First, install the package and its dependencies:

```bash
pip install -e .
```

Then, run the server using the CLI:

```bash
mcprpc-registry run --port 7000
```

Alternatively, you can run it directly with `uvicorn`:

```bash
uvicorn app.main:app --reload --port 7000
```

### Register example

You can register a function using a simple `curl` request:

```bash
curl -X POST http://127.0.0.1:7000/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "math.sum",
    "service_name": "math-service",
    "runtime": "python",
    "transport": "mcp",
    "mcp_transport": "stdio",
    "endpoint": "python workers/math.py",
    "description": "Calculates the sum of numbers",
    "inputSchema": {
      "type": "object",
      "properties": {
        "a": {"type": "number"},
        "b": {"type": "number"}
      }
    },
    "tags": ["math", "calculator"]
  }'
```

### Resolve example

To resolve a function and get its connection details:

```bash
curl -X POST http://127.0.0.1:7000/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "name": "math.sum",
    "context": {}
  }'
```

## Observability

- Every response includes `x-request-id` (generated if not provided).
- Log format: `request_id=... method=... path=... status=... duration_ms=...`.

## CORS (browser clients)

If you call the registry from a browser UI (different origin/port), enable CORS:

- `MCPRPC_CORS_ORIGINS` (comma-separated list of allowed origins), or
- `MCPRPC_CORS_ALLOW_ORIGIN_REGEX` (defaults to allowing `http(s)://localhost:*` and `http(s)://127.0.0.1:*`)

### MCP Explanation

The registry specifically supports MCP transports. When registering a function, you specify:

- `transport: "mcp"`: Indicates that this function communicates via the Model Context Protocol.
- `mcp_transport`: Specifies the specific MCP transport mechanism used by the endpoint. Supported values include:
  - `stdio`: Standard input/output (often used for local processes).
  - `sse`: Server-Sent Events (often used for web-based streaming).
  - `streamable-http`: HTTP-based streaming.

For example, a Node.js worker might register as:
```json
{
  "name": "str.upper",
  "transport": "mcp",
  "mcp_transport": "stdio",
  "endpoint": "node workers/str.js"
}
```

While an HTTP-based service might register as:
```json
{
  "name": "billing.calculate_vat",
  "transport": "mcp",
  "mcp_transport": "streamable-http",
  "endpoint": "http://127.0.0.1:7002/mcp"
}
```

## CLI

Entry point in `app/main.py`:

```bash
python app/main.py run --port 7000
python app/main.py health --url http://127.0.0.1:7000
```
