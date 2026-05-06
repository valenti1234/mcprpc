# mcprpc (monorepo)

[![CI](https://github.com/valenti1234/mcprpc/actions/workflows/ci.yml/badge.svg)](https://github.com/valenti1234/mcprpc/actions/workflows/ci.yml)
[![Release](https://github.com/valenti1234/mcprpc/actions/workflows/release.yml/badge.svg)](https://github.com/valenti1234/mcprpc/actions/workflows/release.yml)

mcprpc is a small set of services and SDKs to register, discover, and invoke MCP (Model Context Protocol) tools across runtimes.

This repository contains:

- `mr-registry`: MCP tool registry service (HTTP)
- `mr-router`: MCP router service (HTTP) that resolves tools via the registry and invokes MCP endpoints
- `mc-automesh`: Python AutoMesh (publish Python functions as MCP tools + register them)
- `mc-node-automesh`: Node.js/TypeScript AutoMesh (publish Node functions as MCP tools + register them)
- `mc-gui`: Web UI that proxies registry/router APIs
- `mr-html`: pure-frontend demo UI (no backend code) that talks to registry + router directly

## Quickstart (local)

1. Start the registry:

```bash
cd mr-registry
./run.sh
```

2. Start the router (defaults to port 7010, registry at `http://localhost:7000`):

```bash
cd mr-router
./run.sh
```

3. Start the pure frontend UI:

```bash
cd mr-html
./run.sh
```

Open:

- `mr-html`: http://127.0.0.1:8386/

## Publishing

This repo is a monorepo. Python packages are published independently:

- `mcprpc-registry` (from `mr-registry/`)
- `mcprpc-router` (from `mr-router/`)
- `mcprpc-gui` (from `mc-gui/`)
- `mc-automesh` (from `mc-automesh/`)

Node packages are published independently:

- `mcprpc` (from `mc-node-automesh/`)

See [PUBLISHING.md](./PUBLISHING.md) for release commands.

## License

MIT. See [LICENSE](./LICENSE).
