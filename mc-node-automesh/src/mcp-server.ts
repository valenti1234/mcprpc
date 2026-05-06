import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { AnyFunction } from "./types.js";
import http, { Server as HttpServer } from "node:http";

/**
 * MCPServer wraps the official MCP Server.
 */
export class MCPServer {
  private server: Server;
  private tools: Map<
    string,
    {
      description: string;
      inputSchema: any;
      inputMode: "positional" | "object";
      parameters?: string[];
      handler: AnyFunction;
    }
  > = new Map();

  constructor(serviceName: string, version: string) {
    this.server = new Server(
      {
        name: serviceName,
        version,
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      const toolList = Array.from(this.tools.entries()).map(([name, tool]) => ({
        name,
        description: tool.description,
        inputSchema: tool.inputSchema,
      }));

      return {
        tools: toolList,
      };
    });

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const tool = this.tools.get(request.params.name);

      if (!tool) {
        throw new Error(`Tool not found: ${request.params.name}`);
      }

      const args = request.params.arguments || {};

      try {
        let result: any;

        if (tool.inputMode === "positional" && tool.parameters) {
          // Map arguments object to positional array
          const posArgs = tool.parameters.map((param) => args[param]);
          result = await tool.handler(...posArgs);
        } else {
          // Default object-argument
          result = await tool.handler(args);
        }

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(result),
            },
          ],
        };
      } catch (error: any) {
        return {
          content: [
            {
              type: "text",
              text: `Error executing tool: ${error.message}`,
            },
          ],
          isError: true,
        };
      }
    });
  }

  /**
   * Registers a tool to the MCP server.
   */
  registerTool(
    name: string,
    toolConfig: {
      description: string;
      inputSchema: any;
      inputMode: "positional" | "object";
      parameters?: string[];
      handler: AnyFunction;
    }
  ) {
    this.tools.set(name, toolConfig);
  }

  /**
   * Starts the server using stdio transport.
   */
  async serveStdio() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
  }

  async serveSse(opts: { endpointUrl: string; bindHost?: string }): Promise<HttpServer> {
    const endpoint = new URL(opts.endpointUrl);
    const port = endpoint.port ? Number(endpoint.port) : 7002;
    const ssePath = (endpoint.pathname || "/sse/").replace(/\/+$/, "") || "/sse";
    const messagesPath = "/messages";
    const sessions = new Map<string, SSEServerTransport>();

    const server = http.createServer(async (req, res) => {
      const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
      const reqPath = (url.pathname || "/").replace(/\/+$/, "") || "/";
      const method = (req.method || "GET").toUpperCase();

      if (method === "GET" && reqPath === "/health") {
        const payload = JSON.stringify({
          status: "ok",
          tools: this.tools.size,
        });
        res.writeHead(200, { "content-type": "application/json" });
        res.end(payload);
        return;
      }

      if (method === "GET" && reqPath === ssePath) {
        const transport = new SSEServerTransport(messagesPath, res);
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
        await transport.handlePostMessage(req as any, res as any);
        return;
      }

      res.writeHead(404).end("Not Found");
    });

    await new Promise<void>((resolve, reject) => {
      server.once("error", reject);
      server.listen(port, opts.bindHost || process.env.MCPRPC_BIND_HOST || "0.0.0.0", () => resolve());
    });

    return server;
  }

  async serveStreamableHttp(opts: { endpointUrl: string; bindHost?: string }): Promise<HttpServer> {
    const endpoint = new URL(opts.endpointUrl);
    const port = endpoint.port ? Number(endpoint.port) : 7002;
    const mcpPathRaw = endpoint.pathname || "/mcp";
    const mcpPath = mcpPathRaw.replace(/\/+$/, "") || "/";
    const transport = new StreamableHTTPServerTransport();
    await this.server.connect(transport);

    const server = http.createServer(async (req, res) => {
      const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
      const method = (req.method || "GET").toUpperCase();
      const reqPath = (url.pathname || "/").replace(/\/+$/, "") || "/";

      if (method === "GET" && url.pathname === "/health") {
        const payload = JSON.stringify({
          status: "ok",
          tools: this.tools.size,
        });
        res.writeHead(200, { "content-type": "application/json" });
        res.end(payload);
        return;
      }

      if (reqPath === mcpPath) {
        await transport.handleRequest(req as any, res as any);
        return;
      }

      res.writeHead(404).end("Not Found");
    });

    await new Promise<void>((resolve, reject) => {
      server.once("error", reject);
      server.listen(port, opts.bindHost || process.env.MCPRPC_BIND_HOST || "0.0.0.0", () => resolve());
    });

    return server;
  }
}
