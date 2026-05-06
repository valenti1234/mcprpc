# mcprpc-gui

Web UI for the mcprpc registry and router.

This service is a small FastAPI app that serves a static frontend and proxies:

- Registry API (default: `http://localhost:7000`)
- Router API (default: `http://localhost:7010`)

## Run

```bash
cd mc-gui
./run-mc-gui.sh
```

Open:

- http://localhost:8002/

## Configuration

Environment variables:

- `REGISTRY_URL` (default: `http://localhost:7000`)
- `ROUTER_URL` (default: `http://localhost:7010`)

