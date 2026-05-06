import { z } from "zod";

export interface MCPRPCMetadata {
  name?: string;
  description?: string;
  inputSchema?: z.ZodType<any, any>;
  outputSchema?: z.ZodType<any, any>;
  acl?: { roles?: string[]; [key: string]: any };
  cost?: { cpuWeight?: number; [key: string]: any };
  tags?: string[];
  inputMode?: "positional" | "object";
  parameters?: string[];
  ignored?: boolean;
}

export const MCPRPC_SYMBOL = Symbol.for("mcprpc.metadata");

export type AnyFunction = (...args: any[]) => any;

export interface ExposedFunction extends AnyFunction {
  [MCPRPC_SYMBOL]?: MCPRPCMetadata;
}

export interface AutoMeshOptions {
  serviceName: string;
  registryUrl: string;
  runtime?: string;
  mcpTransport?: "stdio" | "sse" | "streamable-http";
  endpoint?: string;
  heartbeatIntervalMs?: number;
  meshId?: string;
}

export interface PublishPayload {
  name: string;
  mesh_id: string;
  service_name: string;
  runtime: string;
  transport: string;
  mcp_transport: string;
  endpoint: string;
  description: string;
  inputSchema: any;
  outputSchema: any;
  acl: any;
  cost: any;
  tags: string[];
  version: string;
  health: string;
}
