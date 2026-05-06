import { z } from 'zod';
import { Server } from 'node:http';

interface MCPRPCMetadata {
    name?: string;
    description?: string;
    inputSchema?: z.ZodType<any, any>;
    outputSchema?: z.ZodType<any, any>;
    acl?: {
        roles?: string[];
        [key: string]: any;
    };
    cost?: {
        cpuWeight?: number;
        [key: string]: any;
    };
    tags?: string[];
    inputMode?: "positional" | "object";
    parameters?: string[];
    ignored?: boolean;
}
declare const MCPRPC_SYMBOL: unique symbol;
type AnyFunction = (...args: any[]) => any;
interface ExposedFunction extends AnyFunction {
    [MCPRPC_SYMBOL]?: MCPRPCMetadata;
}
interface AutoMeshOptions {
    serviceName: string;
    registryUrl: string;
    runtime?: string;
    mcpTransport?: "stdio" | "sse" | "streamable-http";
    endpoint?: string;
    heartbeatIntervalMs?: number;
    meshId?: string;
}
interface PublishPayload {
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

/**
 * Wraps a function to expose it via AutoMesh with metadata.
 */
declare function expose<T extends AnyFunction>(metadata: MCPRPCMetadata, fn: T): T & ExposedFunction;
/**
 * Marks a function to be ignored by AutoMesh discovery.
 */
declare function ignore<T extends AnyFunction>(fn: T): T & ExposedFunction;

/**
 * Converts a Zod schema to JSON Schema.
 * If no schema is provided, returns a fallback schema.
 */
declare function generateSchema(schema?: z.ZodType<any, any>): any;
declare function extractMetadata(fn: any, moduleName: string, functionName: string, defaultVersion?: string): {
    name: string;
    description: string;
    inputSchema: any;
    outputSchema: any;
    acl: any;
    cost: any;
    tags: string[];
    version: string;
    inputMode: "positional" | "object";
    parameters?: string[];
};

/**
 * Discovers exported functions from a module file.
 */
declare function discoverFunctions(modulePath: string): Promise<{
    functionName: string;
    fn: any;
    moduleName: string;
}[]>;
/**
 * Discovers functions recursively from a directory path.
 */
declare function discoverPath(directoryPath: string): Promise<{
    functionName: string;
    fn: any;
    moduleName: string;
}[]>;

declare class AutoMesh {
    private options;
    private registryClient;
    private mcpServer;
    private startTs;
    private heartbeatTimer?;
    private meshId;
    private payloads;
    constructor(options: AutoMeshOptions);
    private static normalizeEndpoint;
    private static normalizeSseUrl;
    private registerBuiltinTools;
    heartbeatOnce(health?: string): Promise<void>;
    startHeartbeat(): void;
    stopHeartbeat(): void;
    /**
     * Discovers and prepares a module for publishing.
     */
    publishModule(modulePath: string): Promise<void>;
    /**
     * Discovers and prepares all modules in a directory.
     */
    publishPath(directoryPath: string): Promise<void>;
    private prepareFunctions;
    /**
     * Registers all prepared functions to the registry.
     */
    registerAll(): Promise<void>;
    /**
     * Starts the MCP server to serve the tools.
     */
    serve(): Promise<void>;
}

/**
 * RegistryClient handles publishing tools to the MCPRPC registry.
 */
declare class RegistryClient {
    private registryUrl;
    constructor(registryUrl: string);
    /**
     * Publishes a tool to the registry.
     */
    publish(payload: PublishPayload): Promise<void>;
    heartbeat(payload: {
        service_name: string;
        mesh_id: string;
        runtime?: string;
        health: string;
        tools?: string[];
        heartbeat_interval_s?: number;
        registrations?: PublishPayload[];
    }): Promise<void>;
}

/**
 * MCPServer wraps the official MCP Server.
 */
declare class MCPServer {
    private server;
    private tools;
    constructor(serviceName: string, version: string);
    /**
     * Registers a tool to the MCP server.
     */
    registerTool(name: string, toolConfig: {
        description: string;
        inputSchema: any;
        inputMode: "positional" | "object";
        parameters?: string[];
        handler: AnyFunction;
    }): void;
    /**
     * Starts the server using stdio transport.
     */
    serveStdio(): Promise<void>;
    serveSse(opts: {
        endpointUrl: string;
        bindHost?: string;
    }): Promise<Server>;
    serveStreamableHttp(opts: {
        endpointUrl: string;
        bindHost?: string;
    }): Promise<Server>;
}

export { type AnyFunction, AutoMesh, type AutoMeshOptions, type ExposedFunction, type MCPRPCMetadata, MCPRPC_SYMBOL, MCPServer, type PublishPayload, RegistryClient, discoverFunctions, discoverPath, expose, extractMetadata, generateSchema, ignore };
