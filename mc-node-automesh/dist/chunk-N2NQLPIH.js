// src/discovery.ts
import path from "path";
import fs from "fs/promises";
import { pathToFileURL } from "url";
async function discoverFunctions(modulePath) {
  const absolutePath = path.resolve(modulePath);
  const parsed = path.parse(absolutePath);
  const moduleName = parsed.name;
  let mod;
  try {
    mod = await import(pathToFileURL(absolutePath).href);
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
  const absoluteDir = path.resolve(directoryPath);
  const entries = await fs.readdir(absoluteDir, { withFileTypes: true });
  const discovered = [];
  for (const entry of entries) {
    const fullPath = path.join(absoluteDir, entry.name);
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
import { zodToJsonSchema } from "zod-to-json-schema";
function generateSchema(schema) {
  if (!schema) {
    return {
      type: "object",
      additionalProperties: true
    };
  }
  return zodToJsonSchema(schema, { target: "jsonSchema7" });
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
        `event=registry_publish ok=true name=${payload.name} service_name=${payload.service_name}`
      );
    } catch (error) {
      console.warn(
        `event=registry_publish ok=false name=${payload.name} service_name=${payload.service_name} error=${error.message}`
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
        `event=registry_heartbeat ok=true service_name=${payload.service_name} health=${payload.health}`
      );
    } catch (error) {
      console.warn(
        `event=registry_heartbeat ok=false service_name=${payload.service_name} health=${payload.health} error=${error.message}`
      );
      throw new Error(`Failed to send heartbeat to registry: ${error.message}`);
    }
  }
};

// src/mcp-server.ts
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from "@modelcontextprotocol/sdk/types.js";
var MCPServer = class {
  server;
  tools = /* @__PURE__ */ new Map();
  constructor(serviceName, version) {
    this.server = new Server(
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
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      const toolList = Array.from(this.tools.entries()).map(([name, tool]) => ({
        name,
        description: tool.description,
        inputSchema: tool.inputSchema
      }));
      return {
        tools: toolList
      };
    });
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
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
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
  }
};

// src/auto-mesh.ts
var AutoMesh = class {
  options;
  registryClient;
  mcpServer;
  startTs = Date.now();
  heartbeatTimer;
  // Stored payloads for registry publishing
  payloads = [];
  constructor(options) {
    const envHeartbeatRaw = process.env.MCPRPC_HEARTBEAT_INTERVAL_MS;
    const envHeartbeat = envHeartbeatRaw !== void 0 ? Number(envHeartbeatRaw) : 3e3;
    this.options = {
      runtime: "node",
      mcpTransport: "stdio",
      heartbeatIntervalMs: Number.isFinite(envHeartbeat) ? envHeartbeat : 3e3,
      ...options
    };
    this.registryClient = new RegistryClient(this.options.registryUrl);
    this.mcpServer = new MCPServer(this.options.serviceName, "0.1.0");
    this.registerBuiltinTools();
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
    this.payloads.push({
      name: healthName,
      service_name: this.options.serviceName,
      runtime: this.options.runtime,
      transport: "mcp",
      mcp_transport: this.options.mcpTransport,
      endpoint: this.options.endpoint || "",
      description: "Service health status",
      inputSchema,
      outputSchema: {
        type: "object",
        additionalProperties: true
      },
      acl: {},
      cost: {},
      tags: ["system", "health"],
      version: "0.1.0",
      health: "healthy"
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
    this.payloads.push({
      name: heartbeatName,
      service_name: this.options.serviceName,
      runtime: this.options.runtime,
      transport: "mcp",
      mcp_transport: this.options.mcpTransport,
      endpoint: this.options.endpoint || "",
      description: "Send heartbeat to registry",
      inputSchema: {
        type: "object",
        additionalProperties: false,
        properties: {
          health: { type: "string" }
        }
      },
      outputSchema: {
        type: "object",
        additionalProperties: true
      },
      acl: {},
      cost: {},
      tags: ["system", "heartbeat"],
      version: "0.1.0",
      health: "healthy"
    });
  }
  async heartbeatOnce(health = "healthy") {
    try {
      const intervalMs = this.options.heartbeatIntervalMs ?? 3e3;
      const heartbeatIntervalS = Math.max(0, Math.round(intervalMs / 1e3));
      await this.registryClient.heartbeat({
        service_name: this.options.serviceName,
        runtime: this.options.runtime,
        health,
        tools: this.payloads.map((p) => p.name),
        heartbeat_interval_s: heartbeatIntervalS
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
    } else {
      throw new Error(`Unsupported MCP transport: ${this.options.mcpTransport}`);
    }
  }
};

export {
  discoverFunctions,
  discoverPath,
  generateSchema,
  extractMetadata,
  RegistryClient,
  MCPServer,
  AutoMesh
};
