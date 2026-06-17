# mcprpc — Project Overview

This repository contains a small ecosystem for publishing and executing “tools” (functions) across runtimes using the Model Context Protocol (MCP). It includes:

- Worker-side “AutoMesh” libraries that discover functions and expose them as MCP tools.
- A central registry service that stores tool metadata and resolves tool endpoints.
- A router service that resolves tool names and invokes the selected endpoint via MCP.
- A lightweight web UI that proxies and visualizes registry/router data.

## Top-Level Layout

The repo is a monorepo with these primary projects:

- `mc-automesh/` — Python AutoMesh (discover + publish + serve MCP tools)
- `mc-node-automesh/` — Node.js/TypeScript AutoMesh (discover + publish + serve MCP tools)
- `mc-java-automesh/` — Java AutoMesh (discover + publish + serve MCP tools over `stdio`, `sse`, `streamable-http`)
- `mr-registry/` — Function registry service (FastAPI + SQLite via SQLModel)
- `mr-router/` — Router service (FastAPI) that resolves and calls tools via MCP
- `mc-gui/` — Web UI + proxy (FastAPI + static assets)

Common non-product subfolders you may see:

- Python: `.venv/`, `venv/`, `__pycache__/`, `.pytest_cache/`
- Node: `node_modules/`, `dist/`

## Architecture (How the Pieces Fit)

### 1) Publishing (workers → registry)

1. A worker loads existing code (Python module / Node module).
2. AutoMesh discovers eligible functions.
3. AutoMesh extracts metadata (name, description, JSON schema, ACL/tags, transport endpoint).
4. AutoMesh registers each tool in the registry via `POST /register`.
5. Workers can also send periodic heartbeats to keep registrations “alive”.

### 2) Resolution + Invocation (client → router → registry → worker)

1. A client calls the router `POST /call` with a `function` name, `arguments`, and optional `context`.
2. The router calls the registry `POST /resolve` to get:
   - the resolved tool name (after semantic normalization)
   - the selected endpoint + MCP transport details
   - ACL metadata (if present)
3. The router validates ACL against `context.roles`.
4. The router invokes the MCP tool at the resolved endpoint and returns the result.

## Projects

### mc-automesh (Python AutoMesh)

Purpose: automatically expose existing Python functions as MCP tools and publish them to the registry.

Key capabilities:

- Function discovery:
  - module-based discovery (`publish_module`)
  - directory-based discovery (`publish_path`)
- Metadata extraction:
  - tool naming defaults to `<module>.<function>`
  - input JSON Schema generated from type hints via Pydantic model schema
  - optional ACL/tags via decorators
- Built-in tools:
  - `system.health`
  - `system.heartbeat`
- Transports:
  - `stdio`
  - `sse` (served via uvicorn)

Notable files:

- `mc-automesh/src/mc_automesh/core.py` — main AutoMesh implementation (MCP server, transports, heartbeat)
- `mc-automesh/src/mc_automesh/discovery.py` — discovery rules (skips private, lambdas, imports, ignored)
- `mc-automesh/src/mc_automesh/schema.py` — schema + metadata extraction
- `mc-automesh/src/mc_automesh/registry.py` — registry register + heartbeat client
- `mc-automesh/src/mc_automesh/decorators.py` — `expose`, `ignore`
- `mc-automesh/src/mc_automesh/__main__.py` — CLI entrypoint
- `mc-automesh/example/` — runnable examples, including a multi-service runner

### mc-node-automesh (Node.js / TypeScript AutoMesh)

Purpose: discover exported JS/TS functions, register them in the registry, and expose them as MCP tools (stdio).

Key capabilities:

- Module discovery via dynamic import:
  - discovers named exports that are functions
  - skips `default`, non-functions, `_private`, and `ignore()`-marked functions
- Metadata extraction:
  - optional `expose()` wrapper attaches name/description/schema/ACL/tags/version
  - uses Zod schemas and converts them to JSON Schema
  - supports input modes:
    - `object` (default): tool gets a single object argument
    - `positional`: maps an input object into positional arguments using `parameters`
- Built-in tools:
  - `system.health`
  - `system.heartbeat`
- Transport:
  - `stdio` (current `serve()` supports stdio only)

Notable files:

- `mc-node-automesh/src/auto-mesh.ts` — main AutoMesh implementation
- `mc-node-automesh/src/discovery.ts` — discovery logic
- `mc-node-automesh/src/schema.ts` — schema conversion + metadata extraction
- `mc-node-automesh/src/decorators.ts` — `expose`, `ignore`
- `mc-node-automesh/src/registry-client.ts` — HTTP client for `/register` and `/heartbeat`
- `mc-node-automesh/src/mcp-server.ts` — MCP server wrapper around the official SDK
- `mc-node-automesh/src/cli.ts` — CLI

### mc-java-automesh (Java AutoMesh)

Purpose: discover Java methods, register them in the registry, and expose them as MCP tools over `stdio` or HTTP transports.

Key capabilities:

- Reflection-based discovery:
  - instance method discovery via `publishInstance(...)`
  - static method discovery via `publishClass(...)`
  - package scanning via `publishPackage(...)`
- Metadata extraction:
  - default tool naming uses `<lowerCamelClassName>.<methodName>`
  - optional overrides via `@Expose`
  - `@Ignore` excludes methods from discovery
- Input JSON Schema generation from Java reflection metadata
- Built-in tools:
  - `system.health`
  - `system.heartbeat`
- Transport:
  - `stdio`
  - `sse`
  - `streamable-http`

Notable files:

- `mc-java-automesh/src/main/java/io/mcprpc/automesh/AutoMesh.java` — main AutoMesh implementation
- `mc-java-automesh/src/main/java/io/mcprpc/automesh/McpStdioServer.java` — minimal MCP stdio server
- `mc-java-automesh/src/main/java/io/mcprpc/automesh/HttpMcpServer.java` — minimal MCP HTTP server for `sse` and `streamable-http`
- `mc-java-automesh/src/main/java/io/mcprpc/automesh/MetadataExtractor.java` — metadata extraction
- `mc-java-automesh/src/main/java/io/mcprpc/automesh/SchemaUtils.java` — JSON Schema generation
- `mc-java-automesh/src/main/java/io/mcprpc/automesh/RegistryClient.java` — registry `/register` and `/heartbeat` client
- `mc-java-automesh/src/main/java/io/mcprpc/automesh/AutoMeshCli.java` — CLI entrypoint

Note: `mc-node-automesh/mc-node-automesh/` looks like a duplicated nested copy (it contains its own `package.json`, `src/`, `tests/`, and `node_modules/`). It does not appear to be required for the main package.

### mr-registry (Function Registry Service)

Purpose: store tool metadata and resolve tool endpoints for invocation.

Core responsibilities:

- Register tools (`POST /register`) and store:
  - tool identity (`name`, `semantic_name`, `mesh_id`, `service_name`, `runtime`)
  - transport (`transport`, `mcp_transport`, `endpoint`)
  - metadata (`description`, input/output schema, ACL, tags, version, health)
  - heartbeat fields (`heartbeat_interval_s`, `last_heartbeat_at`, `expires_at`)
- Resolve tools (`POST /resolve`) by semantic name:
  - semantic normalization produces a canonical name (e.g., case normalization, separators)
  - candidates are filtered to exclude expired/unavailable entries
  - selection uses round-robin among candidates with the same semantic name
- Heartbeat + expiry:
  - `POST /heartbeat` updates health and TTL
  - a background loop expires and deletes records whose TTL is exceeded

HTTP endpoints:

- System:
  - `GET /health`, `GET /ready`, `GET /stats`
  - `POST /heartbeat`, `GET /heartbeats`
- Registry:
  - `POST /register`
  - `GET /functions`, `GET /functions/{name}`
  - `POST /resolve`
  - `DELETE /functions/{name}`

Notable files:

- `mr-registry/app/main.py` — FastAPI app, endpoints, expiry loop, request-id middleware, CLI
- `mr-registry/app/db.py` — DB init and SQLite/WAL tuning
- `mr-registry/app/models.py` — SQLModel schema
- `mr-registry/app/repository.py` — semantic normalization, register/update, resolve candidate filtering
- `mr-registry/app/schemas.py` — request/response models

### mr-router (Router Service)

Purpose: provide a simple HTTP API for clients to call tools by name, resolving them via the registry and invoking via MCP.

Core responsibilities:

- `POST /call`:
  - resolves tool via registry `/resolve`
  - validates ACL using `context.roles`
  - invokes MCP tool and returns result + meta
- Resilience:
  - retries with exponential backoff + jitter
  - circuit breakers for registry calls and endpoint calls
- Observability:
  - request-id propagation (`x-request-id`)
  - `/stats` endpoint tracking counts and latency percentiles

Notable files:

- `mr-router/app/main.py` — FastAPI app, `/call`, `/health`, `/ready`, `/stats`, request-id middleware
- `mr-router/app/registry_client.py` — `/resolve` client, endpoint normalization
- `mr-router/app/mcp_executor.py` — MCP invocation + endpoint circuit breakers
- `mr-router/app/acl.py` — ACL validation against roles
- `mr-router/app/resilience.py` — retry + circuit breaker primitives
- `mr-router/app/config.py` — env-based settings

Transport note:

- The router currently rejects `stdio` tool execution in the executor and only implements `sse`/`streamable-http` execution. Treat code behavior as the source of truth.

### mc-gui (Web UI + Proxy)

Purpose: a web UI service that serves static assets and proxies API calls to the registry and router.

Core responsibilities:

- Serve a static frontend from `mc-gui/app/static/`:
  - `/` → `index.html`
  - `/assets/*` → static files
- Proxy endpoints:
  - `/api/registry/*` → forwards to `REGISTRY_URL`
  - `/api/router/*` → forwards to `ROUTER_URL`
- Preserves `x-request-id` when present.

Notable files:

- `mc-gui/app/main.py` — FastAPI app, proxy helpers, routes, CLI
- `mc-gui/app/config.py` — env-based settings
- `mc-gui/app/static/` — frontend assets

## Configuration Summary

### Registry (mr-registry)

- `DATABASE_URL` (default: `sqlite:///mcprpc_registry.db`)
- `MCPRPC_HEARTBEAT_GRACE_MULTIPLIER`
- `MCPRPC_REGISTRY_RESET_DB_ON_START`
- SQLite tuning: `MCPRPC_SQLITE_TIMEOUT_S`, `MCPRPC_SQLITE_BUSY_TIMEOUT_MS`

### Router (mr-router)

- `REGISTRY_URL` (default: `http://127.0.0.1:7000`)
- `REGISTRY_TIMEOUT_S`, `ROUTER_TIMEOUT_S`
- Retry: `ROUTER_RETRY_ATTEMPTS`, `ROUTER_RETRY_BASE_DELAY_S`, `ROUTER_RETRY_MAX_DELAY_S`
- Circuit breaker: `ROUTER_CB_FAILURE_THRESHOLD`, `ROUTER_CB_RECOVERY_TIMEOUT_S`, `ROUTER_CB_HALF_OPEN_SUCCESSES`

### Python AutoMesh (mc-automesh)

- `MCPRPC_HEARTBEAT_INTERVAL_S`
- `MCPRPC_MESH_ID`
- SSE hardening options:
  - `MCPRPC_SSE_DNS_REBINDING_PROTECTION`
  - `MCPRPC_SSE_ALLOWED_HOSTS`
  - `MCPRPC_SSE_ALLOWED_ORIGINS`

### Node AutoMesh (mc-node-automesh)

- `MCPRPC_HEARTBEAT_INTERVAL_MS`
- `MCPRPC_MESH_ID`

### GUI (mc-gui)

- `REGISTRY_URL`
- `ROUTER_URL`
- `GUI_TIMEOUT_S`

## Running Locally (Typical Setup)

One common workflow is:

1. Start the registry (`mr-registry/`).
2. Start the router (`mr-router/`) pointing to the registry.
3. Start one or more workers (Python or Node) and register tools to the registry.
4. Use the GUI (`mc-gui/`) to browse functions and call tools via the router.

This repo includes run scripts:

- `mr-registry/run.sh`
- `mr-router/run.sh`
- `mc-gui/run-mc-gui.sh`
- `mc-automesh/example/run-example.sh`
