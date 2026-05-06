import { AnyFunction, ExposedFunction, MCPRPCMetadata, MCPRPC_SYMBOL } from "./types.js";

/**
 * Wraps a function to expose it via AutoMesh with metadata.
 */
export function expose<T extends AnyFunction>(metadata: MCPRPCMetadata, fn: T): T & ExposedFunction {
  const exposedFn = fn as T & ExposedFunction;
  exposedFn[MCPRPC_SYMBOL] = {
    ...metadata,
    ignored: false,
  };
  return exposedFn;
}

/**
 * Marks a function to be ignored by AutoMesh discovery.
 */
export function ignore<T extends AnyFunction>(fn: T): T & ExposedFunction {
  const exposedFn = fn as T & ExposedFunction;
  exposedFn[MCPRPC_SYMBOL] = {
    ignored: true,
  };
  return exposedFn;
}
