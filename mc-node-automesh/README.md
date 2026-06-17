# AutoMesh for Node.js (`mcprpc`)

AutoMesh automatically discovers your Node.js/TypeScript functions, registers them in the `mcprpc-registry`, and exposes them directly as MCP (Model Context Protocol) tools without requiring manual server boilerplate.

## Quickstart

```bash
npm install mcprpc zod
```

### 1. Write Your Service

```typescript
// services/billing.ts
import { expose } from "mcprpc";
import { z } from "zod";

// Regular object-argument functions work out-of-the-box
export async function createInvoice({ customerId }: { customerId: string }) {
  return {
    invoiceId: "INV-001",
    customerId
  };
}

// For positional arguments and rich metadata, use `expose` wrapper
export const calculateVat = expose({
  name: "billing.calculateVat",
  description: "Calculate VAT",
  inputSchema: z.object({
    amount: z.number(),
    rate: z.number().optional()
  }),
  inputMode: "positional",
  parameters: ["amount", "rate"],
  acl: { roles: ["admin"] },
  tags: ["billing"]
}, (amount: number, rate = 0.22) => {
  return {
    vat: amount * rate
  };
});
```

### 2. Create Your Worker

```typescript
// billing-worker.ts
import { AutoMesh } from "mcprpc";

async function main() {
  const mesh = new AutoMesh({
    serviceName: "node-billing-worker",
    registryUrl: "http://127.0.0.1:7000",
    runtime: "node",
    mcpTransport: "stdio",
    endpoint: "node dist/examples/billing-worker.js"
  });

  // Automatically discover and publish exported functions
  await mesh.publishModule("./services/billing.js");
  
  // Register everything with mcprpc-registry
  await mesh.registerAll();
  
  // Start the MCP stdio server
  await mesh.serve();
}

main().catch(console.error);
```

## Existing Code

AutoMesh is designed to work with your existing code. If you have an existing file with exported functions, AutoMesh will discover them and attempt to infer fallback schemas.

```typescript
// existing-math.ts
export function add(a, b) {
  return a + b;
}
```

Functions prefixed with `_` or wrapped in the `ignore` decorator are skipped during discovery.

## Metadata & Zod Schemas

Because runtime type inference in Node.js (especially for TypeScript) can be difficult or inexact, AutoMesh provides the `expose` wrapper. This lets you attach Zod schemas, descriptions, and calling modes without complex AST parsing:

- Use `inputSchema` with `zod` to declare strict API contracts.
- By default, AutoMesh assumes a single object parameter is passed.
- Use `inputMode: "positional"` and provide an array of `parameters` to map the single MCP tool input object into your positional function arguments.

## Running with Registry and Router

1. Ensure the `mcprpc-registry` is running on `http://127.0.0.1:7000`.
2. Start your worker (`tsx billing-worker.ts` or `node dist/billing-worker.js`).
3. AutoMesh will register tools to the registry and start listening via `stdio`.
4. Connect via an MCP client or the `mcprpc-router`.

## System Tools (built-in)

AutoMesh always registers these built-in tools:

- `system.health`: returns status + uptime + number of tools
- `system.heartbeat`: sends a heartbeat to the registry

These tools are also published to the registry (so they will appear in `GET /functions`).

## Heartbeat (opt-in)

To send periodic heartbeats to the registry:

- via env: `MCPRPC_HEARTBEAT_INTERVAL_MS=5000`
- or via option: `heartbeatIntervalMs` in the constructor

The payload sent to the registry is:

```json
{
  "service_name": "node-billing-worker",
  "runtime": "node",
  "health": "healthy",
  "tools": ["system.health", "system.heartbeat", "..."]
}
```

## CLI

This package exposes a CLI:

```bash
mcprpc run --service-name node-billing-worker --registry-url http://127.0.0.1:7000 --module ./examples/services/billing.ts
mcprpc publish-module --service-name node-billing-worker --registry-url http://127.0.0.1:7000 --module ./examples/services/billing.ts
mcprpc serve --service-name node-billing-worker --registry-url http://127.0.0.1:7000
mcprpc heartbeat --service-name node-billing-worker --registry-url http://127.0.0.1:7000
```
