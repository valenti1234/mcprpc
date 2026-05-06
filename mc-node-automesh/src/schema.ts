import { z } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";
import { MCPRPCMetadata } from "./types.js";

/**
 * Converts a Zod schema to JSON Schema.
 * If no schema is provided, returns a fallback schema.
 */
export function generateSchema(schema?: z.ZodType<any, any>): any {
  if (!schema) {
    return {
      type: "object",
      additionalProperties: true,
    };
  }

  return zodToJsonSchema(schema, { target: "jsonSchema7" });
}

export function extractMetadata(
  fn: any,
  moduleName: string,
  functionName: string,
  defaultVersion: string = "0.1.0"
): { name: string; description: string; inputSchema: any; outputSchema: any; acl: any; cost: any; tags: string[]; version: string; inputMode: "positional" | "object"; parameters?: string[] } {
  const meta = fn[Symbol.for("mcprpc.metadata")] || {};
  
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
    parameters,
  };
}
