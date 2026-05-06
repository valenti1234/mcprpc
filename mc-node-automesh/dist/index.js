import {
  AutoMesh,
  MCPServer,
  RegistryClient,
  discoverFunctions,
  discoverPath,
  extractMetadata,
  generateSchema
} from "./chunk-ZAZCH3QZ.js";

// src/types.ts
var MCPRPC_SYMBOL = /* @__PURE__ */ Symbol.for("mcprpc.metadata");

// src/decorators.ts
function expose(metadata, fn) {
  const exposedFn = fn;
  exposedFn[MCPRPC_SYMBOL] = {
    ...metadata,
    ignored: false
  };
  return exposedFn;
}
function ignore(fn) {
  const exposedFn = fn;
  exposedFn[MCPRPC_SYMBOL] = {
    ignored: true
  };
  return exposedFn;
}
export {
  AutoMesh,
  MCPRPC_SYMBOL,
  MCPServer,
  RegistryClient,
  discoverFunctions,
  discoverPath,
  expose,
  extractMetadata,
  generateSchema,
  ignore
};
