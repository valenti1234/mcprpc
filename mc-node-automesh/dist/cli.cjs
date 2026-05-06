"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// src/discovery.ts
var import_node_path = __toESM(require("path"), 1);
var import_promises = __toESM(require("fs/promises"), 1);
var import_node_url = require("url");
async function discoverFunctions(modulePath) {
  const absolutePath = import_node_path.default.resolve(modulePath);
  const parsed = import_node_path.default.parse(absolutePath);
  const moduleName = parsed.name;
  let mod;
  try {
    mod = await import((0, import_node_url.pathToFileURL)(absolutePath).href);
  } catch (err) {
    throw new Error(`Failed to load module ${absolutePath}: ${err}`);
  }
  const discovered = [];
  for (const [key, value] of Object.entries(mod)) {
    if (key === "default" || typeof value !== "function") {
      continue;
    }
    if (key.startsWith("_")) {
      continue;
    }
    const meta = value[/* @__PURE__ */ Symbol.for("mcprpc.metadata")];
    if (meta && meta.ignored) {
      continue;
    }
    discovered.push({
      functionName: key,
      fn: value,
      moduleName
    });
  }
  return discovered;
}
async function discoverPath(directoryPath) {
  const absoluteDir = import_node_path.default.resolve(directoryPath);
  const entries = await import_promises.default.readdir(absoluteDir, { withFileTypes: true });
  const discovered = [];
  for (const entry of entries) {
    const fullPath = import_node_path.default.join(absoluteDir, entry.name);
    if (entry.isDirectory()) {
      discovered.push(...await discoverPath(fullPath));
    } else if (entry.isFile() && (entry.name.endsWith(".js") || entry.name.endsWith(".ts") || entry.name.endsWith(".cjs") || entry.name.endsWith(".mjs"))) {
      if (!entry.name.endsWith(".d.ts")) {
        discovered.push(...await discoverFunctions(fullPath));
      }
    }
  }
  return discovered;
}

// src/schema.ts
var import_zod_to_json_schema = require("zod-to-json-schema");
function generateSchema(schema) {
  if (!schema) {
    return {
      type: "object",
      additionalProperties: true
    };
  }
  return (0, import_zod_to_json_schema.zodToJsonSchema)(schema, { target: "jsonSchema7" });
}
function extractMetadata(fn, moduleName, functionName, defaultVersion = "0.1.0") {
  const meta = fn[/* @__PURE__ */ Symbol.for("mcprpc.metadata")] || {};
  const name = meta.name || `${moduleName}.${functionName}`;
  const description = meta.description || `Auto-published function ${moduleName}.${functionName}`;
  const inputSchema = generateSchema(meta.inputSchema);
  const outputSchema = generateSchema(meta.outputSchema);
  const acl = meta.acl || {};
  const cost = meta.cost || {};
  const tags = meta.tags || [moduleName];
  const version = meta.version || defaultVersion;
  const inputMode = meta.inputMode || "object";
  const parameters = meta.parameters;
  return {
    name,
    description,
    inputSchema,
    outputSchema,
    acl,
    cost,
    tags,
    version,
    inputMode,
    parameters
  };
}

// src/registry-client.ts
var RegistryClient = class {
  registryUrl;
  constructor(registryUrl) {
    this.registryUrl = registryUrl;
  }
  /**
   * Publishes a tool to the registry.
   */
  async publish(payload) {
    const url = new URL("/register", this.registryUrl).href;
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`Registry responded with status ${response.status}: ${text}`);
      }
      console.warn(
        `event=registry_publish ok=true name=${payload.name} service_name=${payload.service_name} mesh_id=${payload.mesh_id}`
      );
    } catch (error) {
      console.warn(
        `event=registry_publish ok=false name=${payload.name} service_name=${payload.service_name} mesh_id=${payload.mesh_id} error=${error.message}`
      );
      throw new Error(`Failed to publish to registry: ${error.message}`);
    }
  }
  async heartbeat(payload) {
    const url = new URL("/heartbeat", this.registryUrl).href;
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`Registry responded with status ${response.status}: ${text}`);
      }
      console.warn(
        `event=registry_heartbeat ok=true service_name=${payload.service_name} mesh_id=${payload.mesh_id} health=${payload.health}`
      );
    } catch (error) {
      console.warn(
        `event=registry_heartbeat ok=false service_name=${payload.service_name} mesh_id=${payload.mesh_id} health=${payload.health} error=${error.message}`
      );
      throw new Error(`Failed to send heartbeat to registry: ${error.message}`);
    }
  }
};

// src/mcp-server.ts
var import_server = require("@modelcontextprotocol/sdk/server/index.js");
var import_stdio = require("@modelcontextprotocol/sdk/server/stdio.js");
var import_sse = require("@modelcontextprotocol/sdk/server/sse.js");
var import_streamableHttp = require("@modelcontextprotocol/sdk/server/streamableHttp.js");
var import_types = require("@modelcontextprotocol/sdk/types.js");
var import_node_http = __toESM(require("http"), 1);
var MCPServer = class {
  server;
  tools = /* @__PURE__ */ new Map();
  constructor(serviceName, version) {
    this.server = new import_server.Server(
      {
        name: serviceName,
        version
      },
      {
        capabilities: {
          tools: {}
        }
      }
    );
    this.server.setRequestHandler(import_types.ListToolsRequestSchema, async () => {
      const toolList = Array.from(this.tools.entries()).map(([name, tool]) => ({
        name,
        description: tool.description,
        inputSchema: tool.inputSchema
      }));
      return {
        tools: toolList
      };
    });
    this.server.setRequestHandler(import_types.CallToolRequestSchema, async (request) => {
      const tool = this.tools.get(request.params.name);
      if (!tool) {
        throw new Error(`Tool not found: ${request.params.name}`);
      }
      const args = request.params.arguments || {};
      try {
        let result;
        if (tool.inputMode === "positional" && tool.parameters) {
          const posArgs = tool.parameters.map((param) => args[param]);
          result = await tool.handler(...posArgs);
        } else {
          result = await tool.handler(args);
        }
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(result)
            }
          ]
        };
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: `Error executing tool: ${error.message}`
            }
          ],
          isError: true
        };
      }
    });
  }
  /**
   * Registers a tool to the MCP server.
   */
  registerTool(name, toolConfig) {
    this.tools.set(name, toolConfig);
  }
  /**
   * Starts the server using stdio transport.
   */
  async serveStdio() {
    const transport = new import_stdio.StdioServerTransport();
    await this.server.connect(transport);
  }
  async serveSse(opts) {
    const endpoint = new URL(opts.endpointUrl);
    const port = endpoint.port ? Number(endpoint.port) : 7002;
    const ssePath = (endpoint.pathname || "/sse/").replace(/\/+$/, "") || "/sse";
    const messagesPath = "/messages";
    const sessions = /* @__PURE__ */ new Map();
    const server = import_node_http.default.createServer(async (req, res) => {
      const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
      const reqPath = (url.pathname || "/").replace(/\/+$/, "") || "/";
      const method = (req.method || "GET").toUpperCase();
      if (method === "GET" && reqPath === "/health") {
        const payload = JSON.stringify({
          status: "ok",
          tools: this.tools.size
        });
        res.writeHead(200, { "content-type": "application/json" });
        res.end(payload);
        return;
      }
      if (method === "GET" && reqPath === ssePath) {
        const transport = new import_sse.SSEServerTransport(messagesPath, res);
        await this.server.connect(transport);
        sessions.set(transport.sessionId, transport);
        transport.onclose = () => {
          sessions.delete(transport.sessionId);
        };
        transport.onerror = () => {
          sessions.delete(transport.sessionId);
        };
        return;
      }
      if (method === "POST" && reqPath === messagesPath) {
        const sessionId = url.searchParams.get("sessionId") || "";
        if (!sessionId) {
          res.writeHead(400).end("Missing sessionId");
          return;
        }
        const transport = sessions.get(sessionId);
        if (!transport) {
          res.writeHead(404).end("Unknown sessionId");
          return;
        }
        await transport.handlePostMessage(req, res);
        return;
      }
      res.writeHead(404).end("Not Found");
    });
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(port, opts.bindHost || process.env.MCPRPC_BIND_HOST || "0.0.0.0", () => resolve());
    });
    return server;
  }
  async serveStreamableHttp(opts) {
    const endpoint = new URL(opts.endpointUrl);
    const port = endpoint.port ? Number(endpoint.port) : 7002;
    const mcpPathRaw = endpoint.pathname || "/mcp";
    const mcpPath = mcpPathRaw.replace(/\/+$/, "") || "/";
    const transport = new import_streamableHttp.StreamableHTTPServerTransport();
    await this.server.connect(transport);
    const server = import_node_http.default.createServer(async (req, res) => {
      const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
      const method = (req.method || "GET").toUpperCase();
      const reqPath = (url.pathname || "/").replace(/\/+$/, "") || "/";
      if (method === "GET" && url.pathname === "/health") {
        const payload = JSON.stringify({
          status: "ok",
          tools: this.tools.size
        });
        res.writeHead(200, { "content-type": "application/json" });
        res.end(payload);
        return;
      }
      if (reqPath === mcpPath) {
        await transport.handleRequest(req, res);
        return;
      }
      res.writeHead(404).end("Not Found");
    });
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(port, opts.bindHost || process.env.MCPRPC_BIND_HOST || "0.0.0.0", () => resolve());
    });
    return server;
  }
};

// src/auto-mesh.ts
var import_node_crypto = __toESM(require("crypto"), 1);
var import_node_path2 = __toESM(require("path"), 1);
var AutoMesh = class _AutoMesh {
  options;
  registryClient;
  mcpServer;
  startTs = Date.now();
  heartbeatTimer;
  meshId;
  // Stored payloads for registry publishing
  payloads = [];
  constructor(options) {
    const envHeartbeatRaw = process.env.MCPRPC_HEARTBEAT_INTERVAL_MS;
    const envHeartbeat = envHeartbeatRaw !== void 0 ? Number(envHeartbeatRaw) : 3e3;
    const envMeshId = process.env.MCPRPC_MESH_ID;
    this.options = {
      runtime: "node",
      mcpTransport: "stdio",
      heartbeatIntervalMs: Number.isFinite(envHeartbeat) ? envHeartbeat : 3e3,
      ...options
    };
    if (this.options.endpoint) {
      this.options.endpoint = _AutoMesh.normalizeEndpoint(this.options.endpoint);
      if (this.options.mcpTransport === "sse") {
        this.options.endpoint = _AutoMesh.normalizeSseUrl(this.options.endpoint);
      }
    } else if (this.options.mcpTransport === "sse") {
      this.options.endpoint = _AutoMesh.normalizeSseUrl(
        process.env.MCPRPC_SSE_URL || "http://localhost:7002/sse/"
      );
    } else if (this.options.mcpTransport === "streamable-http") {
      this.options.endpoint = process.env.MCPRPC_STREAMABLE_HTTP_URL || "http://localhost:7002/mcp";
    }
    this.meshId = this.options.meshId ?? envMeshId ?? import_node_crypto.default.randomUUID().replaceAll("-", "");
    this.registryClient = new RegistryClient(this.options.registryUrl);
    this.mcpServer = new MCPServer(this.options.serviceName, "0.1.0");
    this.registerBuiltinTools();
  }
  static normalizeEndpoint(endpoint) {
    const trimmed = endpoint.trim();
    if (!trimmed) return trimmed;
    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      return trimmed;
    }
    const parts = trimmed.split(/\s+/);
    if (parts.length < 2) return trimmed;
    const cmd = parts[0];
    const script = parts[1];
    const rest = parts.slice(2);
    if (script.startsWith("./") || script.startsWith("../") || !import_node_path2.default.isAbsolute(script) && script.includes("/")) {
      const resolved = import_node_path2.default.resolve(script);
      return [cmd, resolved, ...rest].join(" ");
    }
    return trimmed;
  }
  static normalizeSseUrl(url) {
    const trimmed = url.trim();
    if (!trimmed) return trimmed;
    if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
      return trimmed;
    }
    try {
      const u = new URL(trimmed);
      if (!u.pathname.endsWith("/")) {
        u.pathname = u.pathname + "/";
      }
      return u.toString();
    } catch {
      return trimmed;
    }
  }
  registerBuiltinTools() {
    const inputSchema = {
      type: "object",
      additionalProperties: true
    };
    const healthName = "system.health";
    this.mcpServer.registerTool(healthName, {
      description: "Service health status",
      inputSchema,
      inputMode: "object",
      handler: async () => {
        return {
          status: "ok",
          service: this.options.serviceName,
          runtime: this.options.runtime,
          version: "0.1.0",
          uptime_ms: Date.now() - this.startTs,
          tools: this.payloads.length
        };
      }
    });
    const heartbeatName = "system.heartbeat";
    this.mcpServer.registerTool(heartbeatName, {
      description: "Send heartbeat to registry",
      inputSchema: {
        type: "object",
        additionalProperties: false,
        properties: {
          health: { type: "string" }
        }
      },
      inputMode: "object",
      handler: async (args) => {
        const health = typeof args?.health === "string" ? args.health : "healthy";
        await this.heartbeatOnce(health).catch(() => void 0);
        return { ok: true };
      }
    });
  }
  async heartbeatOnce(health = "healthy") {
    try {
      const intervalMs = this.options.heartbeatIntervalMs ?? 3e3;
      const heartbeatIntervalS = Math.max(0, Math.round(intervalMs / 1e3));
      await this.registryClient.heartbeat({
        service_name: this.options.serviceName,
        mesh_id: this.meshId,
        runtime: this.options.runtime,
        health,
        tools: this.payloads.map((p) => p.name),
        heartbeat_interval_s: heartbeatIntervalS,
        registrations: this.payloads
      });
    } catch (e) {
      console.warn(
        `event=heartbeat_once ok=false service_name=${this.options.serviceName} error=${e?.message ?? String(e)}`
      );
      throw e;
    }
  }
  startHeartbeat() {
    const intervalMs = this.options.heartbeatIntervalMs;
    if (!intervalMs || intervalMs <= 0) return;
    if (this.heartbeatTimer) return;
    console.warn(
      `event=heartbeat_start service_name=${this.options.serviceName} interval_ms=${intervalMs}`
    );
    this.heartbeatOnce("healthy").catch(() => void 0);
    this.heartbeatTimer = setInterval(() => {
      this.heartbeatOnce("healthy").catch(() => void 0);
    }, intervalMs);
    this.heartbeatTimer.unref?.();
  }
  stopHeartbeat() {
    if (!this.heartbeatTimer) return;
    clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = void 0;
  }
  /**
   * Discovers and prepares a module for publishing.
   */
  async publishModule(modulePath) {
    const discovered = await discoverFunctions(modulePath);
    this.prepareFunctions(discovered);
    console.warn(
      `event=publish_module ok=true service_name=${this.options.serviceName} module=${modulePath} discovered=${discovered.length}`
    );
  }
  /**
   * Discovers and prepares all modules in a directory.
   */
  async publishPath(directoryPath) {
    const discovered = await discoverPath(directoryPath);
    this.prepareFunctions(discovered);
    console.warn(
      `event=publish_path ok=true service_name=${this.options.serviceName} path=${directoryPath} discovered=${discovered.length}`
    );
  }
  prepareFunctions(discovered) {
    for (const { functionName, fn, moduleName } of discovered) {
      const meta = extractMetadata(fn, moduleName, functionName);
      const payload = {
        name: meta.name,
        mesh_id: this.meshId,
        service_name: this.options.serviceName,
        runtime: this.options.runtime,
        transport: "mcp",
        mcp_transport: this.options.mcpTransport,
        endpoint: this.options.endpoint || "",
        description: meta.description,
        inputSchema: meta.inputSchema,
        outputSchema: meta.outputSchema,
        acl: meta.acl,
        cost: meta.cost,
        tags: meta.tags,
        version: meta.version,
        health: "healthy"
      };
      this.payloads.push(payload);
      this.mcpServer.registerTool(meta.name, {
        description: meta.description,
        inputSchema: meta.inputSchema,
        inputMode: meta.inputMode,
        parameters: meta.parameters,
        handler: fn
      });
    }
  }
  /**
   * Registers all prepared functions to the registry.
   */
  async registerAll() {
    console.warn(
      `event=register_all start=true service_name=${this.options.serviceName} tools=${this.payloads.length}`
    );
    for (const payload of this.payloads) {
      try {
        await this.registryClient.publish(payload);
      } catch (err) {
        console.error(`Failed to register ${payload.name}:`, err.message);
      }
    }
    console.warn(
      `event=register_all done=true service_name=${this.options.serviceName} tools=${this.payloads.length}`
    );
  }
  /**
   * Starts the MCP server to serve the tools.
   */
  async serve() {
    if (this.options.mcpTransport === "stdio") {
      this.startHeartbeat();
      await this.mcpServer.serveStdio();
      return;
    }
    if (this.options.mcpTransport === "sse") {
      this.startHeartbeat();
      if (!this.options.endpoint) {
        throw new Error("Missing endpoint for SSE transport");
      }
      await this.mcpServer.serveSse({ endpointUrl: this.options.endpoint });
      return;
    }
    if (this.options.mcpTransport === "streamable-http") {
      this.startHeartbeat();
      if (!this.options.endpoint) {
        throw new Error("Missing endpoint for streamable-http transport");
      }
      await this.mcpServer.serveStreamableHttp({ endpointUrl: this.options.endpoint });
      return;
    }
    throw new Error(`Unsupported MCP transport: ${this.options.mcpTransport}`);
  }
};

// src/cli.ts
function parseArgs(argv) {
  const [command = "help", ...rest] = argv;
  const args = {};
  for (let i = 0; i < rest.length; i++) {
    const token = rest[i];
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
      ""
    ].join("\n")
  );
}
function getString(args, key, fallback) {
  const v = args[key];
  if (typeof v === "string") return v;
  return fallback;
}
function getNumber(args, key) {
  const v = args[key];
  if (typeof v !== "string") return void 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : void 0;
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
  const mcpTransport = getString(args, "mcp-transport", "stdio") ?? "stdio";
  const heartbeatIntervalMs = getNumber(args, "heartbeat-interval-ms") ?? (process.env.MCPRPC_HEARTBEAT_INTERVAL_MS ? Number(process.env.MCPRPC_HEARTBEAT_INTERVAL_MS) : void 0);
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
    meshId
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
