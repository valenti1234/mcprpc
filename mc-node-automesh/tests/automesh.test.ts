import { describe, it, expect, vi } from "vitest";
import { AutoMesh, discoverFunctions, extractMetadata, RegistryClient } from "../src/index.js";
import path from "node:path";

describe("AutoMesh discovery", () => {
  it("discovers exported functions and ignores private/ignored", async () => {
    const discovered = await discoverFunctions(path.resolve(__dirname, "../examples/services/billing.ts"));
    
    const names = discovered.map(d => d.functionName);
    expect(names).toContain("createInvoice");
    expect(names).toContain("calculateVat");
    
    // Should ignore
    expect(names).not.toContain("_privateFunction");
    expect(names).not.toContain("dangerousFunction");
  });

  it("reads expose metadata", async () => {
    const discovered = await discoverFunctions(path.resolve(__dirname, "../examples/services/billing.ts"));
    const calcVat = discovered.find(d => d.functionName === "calculateVat")!;
    
    const meta = extractMetadata(calcVat.fn, calcVat.moduleName, calcVat.functionName);
    expect(meta.name).toBe("billing.calculateVat");
    expect(meta.description).toBe("Calculate VAT");
    expect(meta.inputMode).toBe("positional");
    expect(meta.parameters).toEqual(["amount", "rate"]);
    expect(meta.acl).toEqual({ roles: ["billing", "admin"] });
    expect(meta.cost).toEqual({ cpuWeight: 1 });
    expect(meta.tags).toEqual(["billing"]);
    
    // Zod to JSON Schema check
    expect(meta.inputSchema.type).toBe("object");
    expect(meta.inputSchema.properties).toHaveProperty("amount");
    expect(meta.inputSchema.properties).toHaveProperty("rate");
  });

  it("provides fallback schema", async () => {
    const discovered = await discoverFunctions(path.resolve(__dirname, "../examples/services/billing.ts"));
    const createInv = discovered.find(d => d.functionName === "createInvoice")!;
    
    const meta = extractMetadata(createInv.fn, createInv.moduleName, createInv.functionName);
    expect(meta.name).toBe("billing.createInvoice"); // Fallback name
    expect(meta.inputSchema).toEqual({ type: "object", additionalProperties: true });
  });
});

describe("AutoMesh class", () => {
  it("prepares functions and publishes them to registry", async () => {
    const mesh = new AutoMesh({
      serviceName: "test-service",
      registryUrl: "http://localhost:7000",
      meshId: "mesh-1",
    });

    await mesh.publishModule(path.resolve(__dirname, "../examples/services/billing.ts"));

    // Mock registry client
    const publishSpy = vi.spyOn(RegistryClient.prototype, "publish").mockResolvedValue(undefined);
    
    await mesh.registerAll();
    
    expect(publishSpy).toHaveBeenCalledTimes(2); // calculateVat, createInvoice
    
    // Validate payload
    const calls = publishSpy.mock.calls;
    const calcVatCall = calls.find(call => call[0].name === "billing.calculateVat");
    expect(calcVatCall).toBeDefined();
    expect(calcVatCall![0].service_name).toBe("test-service");
    expect(calcVatCall![0].runtime).toBe("node");
    expect(calcVatCall![0].mcp_transport).toBe("stdio");
  });

  it("supports SSE transport payload defaults", async () => {
    const mesh = new AutoMesh({
      serviceName: "test-service",
      registryUrl: "http://localhost:7000",
      meshId: "mesh-1",
      mcpTransport: "sse",
    });

    await mesh.publishModule(path.resolve(__dirname, "../examples/services/billing.ts"));

    const publishSpy = vi.spyOn(RegistryClient.prototype, "publish").mockResolvedValue(undefined);
    await mesh.registerAll();

    const calls = publishSpy.mock.calls.map((c) => c[0]);
    expect(calls.length).toBe(2);
    for (const payload of calls) {
      expect(payload.mcp_transport).toBe("sse");
      expect(payload.endpoint).toMatch(/^https?:\/\/.+\/sse\/$/);
    }
  });

  it("supports streamable-http transport payload defaults", async () => {
    const mesh = new AutoMesh({
      serviceName: "test-service",
      registryUrl: "http://localhost:7000",
      meshId: "mesh-1",
      mcpTransport: "streamable-http",
    });

    await mesh.publishModule(path.resolve(__dirname, "../examples/services/billing.ts"));

    const publishSpy = vi.spyOn(RegistryClient.prototype, "publish").mockResolvedValue(undefined);
    await mesh.registerAll();

    const calls = publishSpy.mock.calls.map((c) => c[0]);
    expect(calls.length).toBe(2);
    for (const payload of calls) {
      expect(payload.mcp_transport).toBe("streamable-http");
      expect(payload.endpoint).toMatch(/^https?:\/\/.+\/mcp$/);
    }
  });
});
