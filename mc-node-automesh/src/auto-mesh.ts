import { AutoMeshOptions, PublishPayload } from "./types.js";
import { discoverFunctions, discoverPath } from "./discovery.js";
import { extractMetadata } from "./schema.js";
import { RegistryClient } from "./registry-client.js";
import { MCPServer } from "./mcp-server.js";
import crypto from "node:crypto";
import path from "node:path";

export class AutoMesh {
  private options: AutoMeshOptions;
  private registryClient: RegistryClient;
  private mcpServer: MCPServer;
  private startTs: number = Date.now();
  private heartbeatTimer?: NodeJS.Timeout;
  private meshId: string;

  // Stored payloads for registry publishing
  private payloads: PublishPayload[] = [];

  constructor(options: AutoMeshOptions) {
    const envHeartbeatRaw = process.env.MCPRPC_HEARTBEAT_INTERVAL_MS;
    const envHeartbeat =
      envHeartbeatRaw !== undefined ? Number(envHeartbeatRaw) : 3000;
    const envMeshId = process.env.MCPRPC_MESH_ID;
    this.options = {
      runtime: "node",
      mcpTransport: "stdio",
      heartbeatIntervalMs: Number.isFinite(envHeartbeat) ? envHeartbeat : 3000,
      ...options,
    };
    if (this.options.endpoint) {
      this.options.endpoint = AutoMesh.normalizeEndpoint(this.options.endpoint);
      if (this.options.mcpTransport === "sse") {
        this.options.endpoint = AutoMesh.normalizeSseUrl(this.options.endpoint);
      }
    } else if (this.options.mcpTransport === "sse") {
      this.options.endpoint = AutoMesh.normalizeSseUrl(
        process.env.MCPRPC_SSE_URL || "http://localhost:7002/sse/"
      );
    } else if (this.options.mcpTransport === "streamable-http") {
      this.options.endpoint =
        process.env.MCPRPC_STREAMABLE_HTTP_URL || "http://localhost:7002/mcp";
    }
    this.meshId =
      this.options.meshId ?? envMeshId ?? crypto.randomUUID().replaceAll("-", "");
    this.registryClient = new RegistryClient(this.options.registryUrl);
    this.mcpServer = new MCPServer(this.options.serviceName, "0.1.0");
    this.registerBuiltinTools();
  }

  private static normalizeEndpoint(endpoint: string): string {
    const trimmed = endpoint.trim();
    if (!trimmed) return trimmed;

    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      return trimmed;
    }

    const parts = trimmed.split(/\s+/);
    if (parts.length < 2) return trimmed;

    const cmd = parts[0]!;
    const script = parts[1]!;
    const rest = parts.slice(2);

    if (script.startsWith("./") || script.startsWith("../") || (!path.isAbsolute(script) && script.includes("/"))) {
      const resolved = path.resolve(script);
      return [cmd, resolved, ...rest].join(" ");
    }

    return trimmed;
  }

  private static normalizeSseUrl(url: string): string {
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

  private registerBuiltinTools() {
    const inputSchema = {
      type: "object",
      additionalProperties: true,
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
          tools: this.payloads.length,
        };
      },
    });

    const heartbeatName = "system.heartbeat";
    this.mcpServer.registerTool(heartbeatName, {
      description: "Send heartbeat to registry",
      inputSchema: {
        type: "object",
        additionalProperties: false,
        properties: {
          health: { type: "string" },
        },
      },
      inputMode: "object",
      handler: async (args: any) => {
        const health = typeof args?.health === "string" ? args.health : "healthy";
        await this.heartbeatOnce(health).catch(() => undefined);
        return { ok: true };
      },
    });
  }

  async heartbeatOnce(health: string = "healthy") {
    try {
      const intervalMs = this.options.heartbeatIntervalMs ?? 3000;
      const heartbeatIntervalS = Math.max(0, Math.round(intervalMs / 1000));
      await this.registryClient.heartbeat({
        service_name: this.options.serviceName,
        mesh_id: this.meshId,
        runtime: this.options.runtime,
        health,
        tools: this.payloads.map((p) => p.name),
        heartbeat_interval_s: heartbeatIntervalS,
        registrations: this.payloads,
      });
    } catch (e: any) {
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
    this.heartbeatOnce("healthy").catch(() => undefined);
    this.heartbeatTimer = setInterval(() => {
      this.heartbeatOnce("healthy").catch(() => undefined);
    }, intervalMs);
    this.heartbeatTimer.unref?.();
  }

  stopHeartbeat() {
    if (!this.heartbeatTimer) return;
    clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = undefined;
  }

  /**
   * Discovers and prepares a module for publishing.
   */
  async publishModule(modulePath: string) {
    const discovered = await discoverFunctions(modulePath);
    this.prepareFunctions(discovered);
    console.warn(
      `event=publish_module ok=true service_name=${this.options.serviceName} module=${modulePath} discovered=${discovered.length}`
    );
  }

  /**
   * Discovers and prepares all modules in a directory.
   */
  async publishPath(directoryPath: string) {
    const discovered = await discoverPath(directoryPath);
    this.prepareFunctions(discovered);
    console.warn(
      `event=publish_path ok=true service_name=${this.options.serviceName} path=${directoryPath} discovered=${discovered.length}`
    );
  }

  private prepareFunctions(
    discovered: { functionName: string; fn: any; moduleName: string }[]
  ) {
    for (const { functionName, fn, moduleName } of discovered) {
      const meta = extractMetadata(fn, moduleName, functionName);

      const payload: PublishPayload = {
        name: meta.name,
        mesh_id: this.meshId,
        service_name: this.options.serviceName,
        runtime: this.options.runtime!,
        transport: "mcp",
        mcp_transport: this.options.mcpTransport!,
        endpoint: this.options.endpoint || "",
        description: meta.description,
        inputSchema: meta.inputSchema,
        outputSchema: meta.outputSchema,
        acl: meta.acl,
        cost: meta.cost,
        tags: meta.tags,
        version: meta.version,
        health: "healthy",
      };

      this.payloads.push(payload);

      // Register with MCP Server
      this.mcpServer.registerTool(meta.name, {
        description: meta.description,
        inputSchema: meta.inputSchema,
        inputMode: meta.inputMode,
        parameters: meta.parameters,
        handler: fn,
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
      } catch (err: any) {
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
}
