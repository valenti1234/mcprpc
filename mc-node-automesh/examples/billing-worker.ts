import { AutoMesh } from "../src/index.js";
import path from "node:path";

async function main() {
  const registryUrl = process.env.REGISTRY_URL ?? "http://localhost:7000";
  const serviceName = process.env.SERVICE_NAME ?? "node-billing-worker";
  const endpoint =
    process.env.ENDPOINT ??
    `node ${path.resolve("dist/examples/billing-worker.js")}`;

  const mesh = new AutoMesh({
    serviceName,
    registryUrl,
    runtime: "node",
    mcpTransport: "stdio",
    endpoint,
  });

  await mesh.publishModule("./examples/services/billing.ts");

  // In a real scenario, registry must be running. We catch the error in registerAll
  await mesh.registerAll();
  await mesh.serve();
}

main().catch(console.error);
