import { AutoMesh } from "./auto-mesh.js";

type Args = Record<string, string | boolean | undefined>;

function parseArgs(argv: string[]): { command: string; args: Args } {
  const [command = "help", ...rest] = argv;
  const args: Args = {};
  for (let i = 0; i < rest.length; i++) {
    const token = rest[i]!;
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = rest[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i++;
    }
  }
  return { command, args };
}

function usage() {
  process.stderr.write(
    [
      "mcprpc <command> [--flags]",
      "",
      "Commands:",
      "  publish-module   --module <path>",
      "  publish-path     --path <dir>",
      "  serve",
      "  run              (publish + register + serve)",
      "  heartbeat        (send heartbeat to registry)",
      "",
      "Common flags:",
      "  --service-name <name>",
      "  --registry-url <url>",
      "  --endpoint <string>",
      "  --runtime <node>",
      "  --mcp-transport <stdio|sse|streamable-http>",
      "  --heartbeat-interval-ms <ms>",
      "  --mesh-id <id>",
      "",
    ].join("\n")
  );
}

function getString(args: Args, key: string, fallback?: string): string | undefined {
  const v = args[key];
  if (typeof v === "string") return v;
  return fallback;
}

function getNumber(args: Args, key: string): number | undefined {
  const v = args[key];
  if (typeof v !== "string") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

async function main() {
  const { command, args } = parseArgs(process.argv.slice(2));
  if (command === "help") {
    usage();
    process.exit(0);
  }

  const serviceName = getString(args, "service-name", process.env.SERVICE_NAME) ?? "";
  const registryUrl = getString(args, "registry-url", process.env.REGISTRY_URL) ?? "";
  const endpoint = getString(args, "endpoint", process.env.ENDPOINT);
  const runtime = getString(args, "runtime", "node");
  const mcpTransport =
    (getString(args, "mcp-transport", "stdio") as "stdio" | "sse" | "streamable-http") ?? "stdio";
  const heartbeatIntervalMs =
    getNumber(args, "heartbeat-interval-ms") ??
    (process.env.MCPRPC_HEARTBEAT_INTERVAL_MS ? Number(process.env.MCPRPC_HEARTBEAT_INTERVAL_MS) : undefined);
  const meshId = getString(args, "mesh-id", process.env.MCPRPC_MESH_ID);

  if (!serviceName && command !== "help") {
    process.stderr.write("--service-name richiesto\n");
    process.exit(2);
  }
  if (!registryUrl && command !== "help") {
    process.stderr.write("--registry-url richiesto\n");
    process.exit(2);
  }

  const mesh = new AutoMesh({
    serviceName,
    registryUrl,
    runtime,
    mcpTransport,
    endpoint,
    heartbeatIntervalMs,
    meshId,
  });

  if (command === "publish-module" || command === "run") {
    const modulePath = getString(args, "module");
    if (!modulePath) {
      process.stderr.write("--module richiesto\n");
      process.exit(2);
    }
    await mesh.publishModule(modulePath);
  }

  if (command === "publish-path" || command === "run") {
    const dirPath = getString(args, "path");
    if (!dirPath) {
      process.stderr.write("--path richiesto\n");
      process.exit(2);
    }
    await mesh.publishPath(dirPath);
  }

  if (command === "serve") {
    await mesh.serve();
    return;
  }

  if (command === "run") {
    await mesh.registerAll();
    await mesh.serve();
    return;
  }

  if (command === "heartbeat") {
    await mesh.heartbeatOnce("healthy");
    process.stdout.write("ok\n");
    return;
  }

  usage();
  process.exit(2);
}

main().catch((err) => {
  process.stderr.write(String(err?.stack || err?.message || err));
  process.stderr.write("\n");
  process.exit(1);
});
