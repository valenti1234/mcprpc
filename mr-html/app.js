/*
  MCP Router Web Client (pure frontend)

  This example demonstrates a minimal browser client that talks to:
    - a Registry HTTP server to discover available functions (tools)
    - a Router HTTP server to invoke a selected function and stream output

  Default mcprpc endpoints (direct-to-services, no proxy):
    - GET  {REGISTRY_URL}/functions
    - POST {ROUTER_URL}/call

  Streaming note:
    - The browser reads the response body incrementally via ReadableStream.getReader().
    - If the router/worker flushes incremental chunks (streamable-http), you see live updates.
    - If the server responds only at the end (common for JSON responses), you'll see the full payload at once.

  No backend code is included here by design.
*/

class MCPClient {
  constructor({
    registryBaseUrl = "",
    routerBaseUrl = "",
    connectTimeoutMs = 15000,
    invokeConnectTimeoutMs = 30000,
  } = {}) {
    this.registryBaseUrl = (registryBaseUrl || "").trim().replace(/\/+$/, "");
    this.routerBaseUrl = (routerBaseUrl || "").trim().replace(/\/+$/, "");
    this.connectTimeoutMs = connectTimeoutMs;
    this.invokeConnectTimeoutMs = invokeConnectTimeoutMs;
  }

  setRegistryBaseUrl(url) {
    this.registryBaseUrl = (url || "").trim().replace(/\/+$/, "");
  }

  setRouterBaseUrl(url) {
    this.routerBaseUrl = (url || "").trim().replace(/\/+$/, "");
  }

  async listRegistryFunctions() {
    const candidates = [
      { baseUrl: this.registryBaseUrl, path: "/functions" },
      { baseUrl: this.registryBaseUrl, path: "/api/registry/functions" },
      { baseUrl: this.registryBaseUrl, path: "/api/tools" },
    ];

    for (const c of candidates) {
      const url = this._url(c.baseUrl, c.path);
      const res = await this._fetchWithTimeout(url, { method: "GET" }, this.connectTimeoutMs);
      if (res.ok) return await this._safeReadJson(res);
      if (res.status !== 404) {
        const body = await this._safeReadText(res);
        throw new Error(
          `Tool discovery failed: HTTP ${res.status} ${res.statusText}${body ? ` — ${body}` : ""}`,
        );
      }
    }

    throw new Error("Tool discovery failed: no compatible registry endpoint found");
  }

  async callRouter({ function: fn, arguments: args, context }, { onChunk, signal } = {}) {
    const candidates = [
      { baseUrl: this.routerBaseUrl, path: "/call" },
      { baseUrl: this.routerBaseUrl, path: "/api/router/call" },
      { baseUrl: this.routerBaseUrl, path: "/api/invoke", legacy: true },
    ];

    const payload = {
      function: fn,
      arguments: args ?? {},
      context: context ?? {},
    };

    for (const c of candidates) {
      const url = this._url(c.baseUrl, c.path);
      const body = c.legacy
        ? JSON.stringify({ tool: fn, arguments: args ?? {} })
        : JSON.stringify(payload);

      const res = await this._fetchWithTimeout(
        url,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body,
          signal,
        },
        this.invokeConnectTimeoutMs,
      );

      if (res.ok) return await this._readStreamedResponse(res, onChunk);

      if (res.status !== 404) {
        const errText = await this._safeReadText(res);
        throw new Error(`Invocation failed: HTTP ${res.status} ${res.statusText}${errText ? ` — ${errText}` : ""}`);
      }
    }

    throw new Error("Invocation failed: no compatible router endpoint found");
  }

  async _readStreamedResponse(res, onChunk) {
    if (!res.body) {
      const text = await res.text();
      if (onChunk) onChunk(text);
      return text;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let aggregated = "";

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        aggregated += chunk;
        if (onChunk) onChunk(chunk);
      }
      const tail = decoder.decode();
      if (tail) {
        aggregated += tail;
        if (onChunk) onChunk(tail);
      }
      return aggregated;
    } finally {
      try {
        reader.releaseLock();
      } catch {
        // ignore
      }
    }
  }

  _url(baseUrl, pathname) {
    const base = (baseUrl || "").trim().replace(/\/+$/, "");
    return `${base}${pathname}`;
  }

  async _fetchWithTimeout(url, init, timeoutMs) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(new DOMException("Timeout", "TimeoutError")), timeoutMs);

    const externalSignal = init?.signal;
    if (externalSignal) {
      if (externalSignal.aborted) controller.abort(externalSignal.reason);
      else externalSignal.addEventListener("abort", () => controller.abort(externalSignal.reason), { once: true });
    }

    try {
      const mergedInit = { ...init, signal: controller.signal };
      return await fetch(url, mergedInit);
    } catch (err) {
      if (err instanceof TypeError && (err.message || "").toLowerCase().includes("failed to fetch")) {
        throw new Error(
          "Connection error: Failed to fetch (service down, mixed hostnames like localhost vs 127.0.0.1, or CORS blocked).",
        );
      }
      if (controller.signal.aborted) {
        const reason = controller.signal.reason;
        if (reason?.name === "TimeoutError") throw new Error(`Request timed out after ${timeoutMs}ms`);
        throw new Error("Request aborted");
      }
      throw new Error(`Connection error: ${err?.message || String(err)}`);
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async _safeReadJson(res) {
    const text = await res.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (err) {
      throw new Error(`Invalid JSON from server: ${err?.message || String(err)}`);
    }
  }

  async _safeReadText(res) {
    try {
      return await res.text();
    } catch {
      return "";
    }
  }
}

class ToolDiscovery {
  constructor({ client, viewer }) {
    this.client = client;
    this.viewer = viewer;
    this.tools = [];
  }

  async refresh() {
    this.viewer.setStatus("Discovering tools…", "busy");
    this.viewer.log("info", "GET registry functions");

    const functions = await this.client.listRegistryFunctions();
    if (!Array.isArray(functions)) throw new Error("Registry response must be an array");

    this.tools = functions
      .filter((fn) => fn && typeof fn.name === "string")
      .map((fn) => normalizeRegistryFunctionToTool(fn))
      .sort((a, b) => a.name.localeCompare(b.name));

    this.viewer.setStatus("Tools loaded", "ok");
    this.viewer.log("ok", `Discovered ${this.tools.length} tool(s)`);
    return this.tools;
  }
}

function normalizeRegistryFunctionToTool(fn) {
  const inputSchema = fn.inputSchema ?? fn.schema ?? fn.input_schema ?? null;
  return {
    name: fn.name,
    description: typeof fn.description === "string" ? fn.description : "",
    schema: normalizeToolSchema(inputSchema),
  };
}

function normalizeToolSchema(schemaLike) {
  if (!schemaLike) return { type: "object", properties: {}, required: [] };

  if (looksLikeJsonSchemaObject(schemaLike)) {
    const s = schemaLike;
    const props = s.properties && typeof s.properties === "object" ? s.properties : {};
    const req = Array.isArray(s.required) ? s.required.filter((x) => typeof x === "string") : [];
    return { type: "object", properties: props, required: req };
  }

  if (typeof schemaLike === "object" && !Array.isArray(schemaLike)) {
    const properties = {};
    for (const [key, type] of Object.entries(schemaLike)) {
      properties[key] = { type: String(type || "string") };
    }
    return { type: "object", properties, required: [] };
  }

  return { type: "object", properties: {}, required: [] };
}

function looksLikeJsonSchemaObject(x) {
  if (!x || typeof x !== "object" || Array.isArray(x)) return false;
  if (typeof x.type === "string") return true;
  if (x.properties && typeof x.properties === "object") return true;
  if (Array.isArray(x.required)) return true;
  return false;
}

class ToolRenderer {
  constructor({ elements, viewer }) {
    this.el = elements;
    this.viewer = viewer;
    this.tools = [];
    this.selectedTool = null;
    this.fieldNodes = new Map();
  }

  renderToolList(tools) {
    this.tools = Array.isArray(tools) ? tools : [];
    this.el.toolsList.innerHTML = "";
    this.el.toolsEmpty.hidden = this.tools.length > 0;

    for (const tool of this.tools) {
      const li = document.createElement("li");
      const card = document.createElement("div");
      card.className = "tool";
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-selected", "false");
      card.dataset.toolName = tool.name;

      const name = document.createElement("div");
      name.className = "tool__name";
      name.textContent = tool.name;

      const desc = document.createElement("div");
      desc.className = "tool__desc";
      desc.textContent = tool.description || "No description";

      card.appendChild(name);
      card.appendChild(desc);
      li.appendChild(card);
      this.el.toolsList.appendChild(li);

      const select = () => this.selectTool(tool.name);
      card.addEventListener("click", select);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          select();
        }
      });
    }

    if (this.selectedTool) {
      const stillExists = this.tools.some((t) => t.name === this.selectedTool.name);
      if (!stillExists) this.clearSelection();
      else this.selectTool(this.selectedTool.name);
    } else {
      this.clearSelection();
    }
  }

  selectTool(toolName) {
    const tool = this.tools.find((t) => t.name === toolName);
    if (!tool) return;
    this.selectedTool = tool;

    const cards = this.el.toolsList.querySelectorAll(".tool");
    for (const card of cards) {
      const isSelected = card.dataset.toolName === toolName;
      card.setAttribute("aria-selected", isSelected ? "true" : "false");
    }

    this.el.selectedToolMeta.textContent = tool.description || tool.name;
    this._renderForm(tool);
    this.viewer.log("info", `Selected tool: ${tool.name}`);
  }

  clearSelection() {
    this.selectedTool = null;
    this.fieldNodes.clear();
    this.el.selectedToolMeta.textContent = "Select a tool on the left";
    this.el.formFields.hidden = true;
    this.el.contextFields.hidden = true;
    this.el.formActions.hidden = true;
    this.el.formEmpty.hidden = false;
  }

  getSelectedToolName() {
    return this.selectedTool?.name || null;
  }

  readArgumentsFromForm() {
    if (!this.selectedTool) throw new Error("No tool selected");
    const args = {};
    const schema = this.selectedTool.schema || { type: "object", properties: {}, required: [] };
    const properties = schema.properties && typeof schema.properties === "object" ? schema.properties : {};
    const required = Array.isArray(schema.required) ? schema.required : [];

    for (const [key, prop] of Object.entries(properties)) {
      const node = this.fieldNodes.get(key);
      if (!node) continue;

      const meta = this._normalizeProp(prop);

      if (meta.type === "boolean") {
        args[key] = Boolean(node.checked);
        continue;
      }

      const raw = (node.value ?? "").trim();
      if (raw === "") {
        if (required.includes(key)) throw new Error(`Missing required field "${key}"`);
        continue;
      }

      if (meta.type === "number") {
        const n = Number(raw);
        if (!Number.isFinite(n)) throw new Error(`Invalid number for "${key}"`);
        args[key] = meta.integer ? Math.trunc(n) : n;
        continue;
      }

      if (meta.type === "json") {
        try {
          args[key] = JSON.parse(raw);
        } catch (err) {
          throw new Error(`Invalid JSON for "${key}": ${err?.message || String(err)}`);
        }
        continue;
      }

      args[key] = raw;
    }

    return args;
  }

  _renderForm(tool) {
    this.fieldNodes.clear();
    this.el.formFields.innerHTML = "";

    const schema = tool.schema || { type: "object", properties: {}, required: [] };
    const properties = schema.properties && typeof schema.properties === "object" ? schema.properties : {};
    const required = Array.isArray(schema.required) ? schema.required : [];
    const entries = Object.entries(properties);

    if (entries.length === 0) {
      const note = document.createElement("div");
      note.className = "form__empty";
      note.textContent = "This tool has no parameters.";
      this.el.formFields.appendChild(note);
      this.el.formFields.hidden = false;
      this.el.contextFields.hidden = false;
      this.el.formActions.hidden = false;
      this.el.formEmpty.hidden = true;
      return;
    }

    for (const [key, prop] of entries) {
      const meta = this._normalizeProp(prop);
      const label = document.createElement("label");
      label.className = "field";

      const title = document.createElement("span");
      title.textContent = `${key}${required.includes(key) ? " *" : ""} (${meta.label})`;

      let input;
      if (meta.enum && meta.enum.length) {
        input = document.createElement("select");
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "Select…";
        input.appendChild(empty);
        for (const opt of meta.enum) {
          const o = document.createElement("option");
          o.value = String(opt);
          o.textContent = String(opt);
          input.appendChild(o);
        }
      } else if (meta.type === "number") {
        input = document.createElement("input");
        input.type = "number";
        input.inputMode = "decimal";
        input.step = meta.integer ? "1" : "any";
        input.placeholder = "e.g. 123";
      } else if (meta.type === "boolean") {
        input = document.createElement("input");
        input.type = "checkbox";
        input.style.width = "18px";
        input.style.height = "18px";
      } else if (meta.type === "json") {
        input = document.createElement("textarea");
        input.rows = 4;
        input.placeholder = 'e.g. {"key":"value"}';
      } else {
        input = document.createElement("input");
        input.type = "text";
        input.placeholder = "e.g. hello";
      }

      input.name = key;
      input.dataset.paramType = meta.type;

      if (meta.default !== undefined) {
        if (meta.type === "boolean") input.checked = Boolean(meta.default);
        else if (meta.type === "json") input.value = JSON.stringify(meta.default, null, 2);
        else input.value = String(meta.default);
      }

      label.appendChild(title);
      label.appendChild(input);
      this.el.formFields.appendChild(label);
      this.fieldNodes.set(key, input);
    }

    this.el.formFields.hidden = false;
    this.el.contextFields.hidden = false;
    this.el.formActions.hidden = false;
    this.el.formEmpty.hidden = true;
  }

  _normalizeProp(prop) {
    const p = prop && typeof prop === "object" && !Array.isArray(prop) ? prop : { type: prop };
    const typeRaw = p.type;
    const type = Array.isArray(typeRaw) ? typeRaw.find((x) => x && x !== "null") : typeRaw;
    const t = String(type || "string").toLowerCase();

    const enumValues = Array.isArray(p.enum) ? p.enum : null;
    const integer = t === "integer";

    if (t === "number" || t === "integer") {
      return { type: "number", integer, label: integer ? "integer" : "number", enum: enumValues, default: p.default };
    }
    if (t === "boolean") return { type: "boolean", integer: false, label: "boolean", enum: enumValues, default: p.default };
    if (t === "object" || t === "array") return { type: "json", integer: false, label: t, enum: enumValues, default: p.default };
    if (t === "json") return { type: "json", integer: false, label: "json", enum: enumValues, default: p.default };
    return { type: "string", integer: false, label: "string", enum: enumValues, default: p.default };
  }
}

class StreamViewer {
  constructor({ streamOutput, logOutput, streamMeta, logMeta, statusPill }) {
    this.streamOutput = streamOutput;
    this.logOutput = logOutput;
    this.streamMeta = streamMeta;
    this.logMeta = logMeta;
    this.statusPill = statusPill;
    this.logCount = 0;
    this._setStatusClass("idle");
  }

  clearOutput() {
    this.streamOutput.textContent = "";
    this.streamMeta.textContent = "Cleared";
  }

  clearLogs() {
    this.logOutput.textContent = "";
    this.logCount = 0;
    this._updateLogMeta();
  }

  appendChunk(chunk) {
    this.streamOutput.textContent += chunk;
    this.streamOutput.scrollTop = this.streamOutput.scrollHeight;
  }

  setStreamMeta(text) {
    this.streamMeta.textContent = text;
  }

  setStatus(text, state = "idle") {
    this.statusPill.textContent = text;
    this._setStatusClass(state);
  }

  log(level, message) {
    const ts = new Date().toISOString();
    const lvl = String(level || "info").toUpperCase().padEnd(5, " ");
    this.logOutput.textContent += `[${ts}] ${lvl} ${message}\n`;
    this.logOutput.scrollTop = this.logOutput.scrollHeight;
    this.logCount += 1;
    this._updateLogMeta();
  }

  _updateLogMeta() {
    this.logMeta.textContent = `${this.logCount} entr${this.logCount === 1 ? "y" : "ies"}`;
  }

  _setStatusClass(state) {
    const s = String(state || "idle");
    const colors = {
      idle: "rgba(156, 163, 175, 0.85)",
      busy: "rgba(251, 191, 36, 0.95)",
      ok: "rgba(52, 211, 153, 0.95)",
      error: "rgba(248, 113, 113, 0.95)",
    };
    this.statusPill.style.color = colors[s] || colors.idle;
  }
}

function getEl(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing element #${id}`);
  return el;
}

function readBaseUrlInput(inputEl) {
  const raw = String(inputEl.value || "").trim();
  return raw.replace(/\/+$/, "");
}

function parseCommaList(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return [];
  return trimmed
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x.length > 0);
}

async function main() {
  const elements = {
    registryBase: getEl("registryBase"),
    routerBase: getEl("routerBase"),
    statusPill: getEl("statusPill"),

    refreshTools: getEl("refreshTools"),
    toolsMeta: getEl("toolsMeta"),
    toolsEmpty: getEl("toolsEmpty"),
    toolsList: getEl("toolsList"),

    selectedToolMeta: getEl("selectedToolMeta"),
    toolForm: getEl("toolForm"),
    formEmpty: getEl("formEmpty"),
    formFields: getEl("formFields"),
    contextFields: getEl("contextFields"),
    ctxRoles: getEl("ctxRoles"),
    ctxTenant: getEl("ctxTenant"),
    formActions: getEl("formActions"),
    executeTool: getEl("executeTool"),
    cancelStream: getEl("cancelStream"),

    clearOutput: getEl("clearOutput"),
    clearLogs: getEl("clearLogs"),

    streamOutput: getEl("streamOutput"),
    logOutput: getEl("logOutput"),
    streamMeta: getEl("streamMeta"),
    logMeta: getEl("logMeta"),
  };

  const viewer = new StreamViewer({
    streamOutput: elements.streamOutput,
    logOutput: elements.logOutput,
    streamMeta: elements.streamMeta,
    logMeta: elements.logMeta,
    statusPill: elements.statusPill,
  });

  const storedRegistryBase = localStorage.getItem("mcp.registryBase") || "";
  const storedRouterBase = localStorage.getItem("mcp.routerBase") || "";

  const host = window.location.hostname || "localhost";
  const defaultRegistryBase = `http://${host}:7000`;
  const defaultRouterBase = `http://${host}:7010`;

  const normalizeStoredBase = (stored, defaultBase, currentHost) => {
    const s = String(stored || "").trim();
    if (!s) return "";
    try {
      const u = new URL(s);
      if (u.hostname === "localhost" && currentHost !== "localhost") {
        return defaultBase;
      }
      if (u.hostname === "127.0.0.1" && currentHost === "localhost") {
        return defaultBase;
      }
      return s;
    } catch {
      return s;
    }
  };

  const normalizedStoredRegistryBase = normalizeStoredBase(storedRegistryBase, defaultRegistryBase, host);
  const normalizedStoredRouterBase = normalizeStoredBase(storedRouterBase, defaultRouterBase, host);

  elements.registryBase.value = normalizedStoredRegistryBase || elements.registryBase.value || defaultRegistryBase;
  elements.routerBase.value = normalizedStoredRouterBase || elements.routerBase.value || defaultRouterBase;

  localStorage.setItem("mcp.registryBase", readBaseUrlInput(elements.registryBase));
  localStorage.setItem("mcp.routerBase", readBaseUrlInput(elements.routerBase));

  const client = new MCPClient({
    registryBaseUrl: readBaseUrlInput(elements.registryBase),
    routerBaseUrl: readBaseUrlInput(elements.routerBase),
  });
  const discovery = new ToolDiscovery({ client, viewer });
  const renderer = new ToolRenderer({ elements, viewer });

  let currentInvocation = null;

  const setBusy = (isBusy) => {
    elements.refreshTools.disabled = isBusy;
    elements.executeTool.disabled = isBusy;
    elements.cancelStream.disabled = !isBusy;
    elements.registryBase.disabled = isBusy;
    elements.routerBase.disabled = isBusy;
  };

  const refresh = async () => {
    try {
      setBusy(true);
      viewer.setStreamMeta("Waiting");
      const tools = await discovery.refresh();
      elements.toolsMeta.textContent = `${tools.length} tool(s)`;
      renderer.renderToolList(tools);
    } catch (err) {
      viewer.setStatus("Error", "error");
      viewer.log("error", err?.message || String(err));
      elements.toolsMeta.textContent = "Failed to load";
      renderer.renderToolList([]);
    } finally {
      setBusy(false);
    }
  };

  elements.registryBase.addEventListener("change", () => {
    const baseUrl = readBaseUrlInput(elements.registryBase);
    localStorage.setItem("mcp.registryBase", baseUrl);
    client.setRegistryBaseUrl(baseUrl);
    viewer.log("info", `Registry URL: ${baseUrl || "(same origin)"}`);
  });

  elements.routerBase.addEventListener("change", () => {
    const baseUrl = readBaseUrlInput(elements.routerBase);
    localStorage.setItem("mcp.routerBase", baseUrl);
    client.setRouterBaseUrl(baseUrl);
    viewer.log("info", `Router URL: ${baseUrl || "(same origin)"}`);
  });

  elements.refreshTools.addEventListener("click", async () => {
    await refresh();
  });

  elements.clearOutput.addEventListener("click", () => viewer.clearOutput());
  elements.clearLogs.addEventListener("click", () => viewer.clearLogs());

  elements.cancelStream.addEventListener("click", () => {
    if (currentInvocation?.controller) {
      currentInvocation.controller.abort(new DOMException("User cancelled", "AbortError"));
    }
  });

  elements.toolForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const toolName = renderer.getSelectedToolName();
    if (!toolName) return;

    let args;
    try {
      args = renderer.readArgumentsFromForm();
    } catch (err) {
      viewer.setStatus("Invalid input", "error");
      viewer.log("error", err?.message || String(err));
      return;
    }

    if (currentInvocation?.controller) {
      currentInvocation.controller.abort(new DOMException("Superseded", "AbortError"));
    }

    const controller = new AbortController();
    const encoder = new TextEncoder();
    currentInvocation = { controller, startedAt: Date.now(), bytes: 0, encoder };

    viewer.setStatus("Streaming…", "busy");
    viewer.setStreamMeta("Starting…");
    const roles = parseCommaList(elements.ctxRoles.value);
    const tenant = String(elements.ctxTenant.value || "").trim();
    const context = { roles };
    if (tenant) context.tenant = tenant;
    viewer.log(
      "info",
      `POST router call url="${readBaseUrlInput(elements.routerBase)}/call" function="${toolName}" args=${JSON.stringify(args)} ctx=${JSON.stringify(context)}`,
    );

    setBusy(true);

    try {
      await client.callRouter(
        { function: toolName, arguments: args, context },
        {
          signal: controller.signal,
          onChunk: (chunk) => {
            currentInvocation.bytes += currentInvocation.encoder.encode(chunk).byteLength;
            viewer.appendChunk(chunk);
            const elapsedMs = Date.now() - currentInvocation.startedAt;
            viewer.setStreamMeta(`${currentInvocation.bytes} bytes • ${Math.max(0, elapsedMs)}ms`);
          },
        },
      );
      viewer.setStatus("Done", "ok");
      viewer.log("ok", `Completed: ${toolName}`);
    } catch (err) {
      if (controller.signal.aborted) {
        viewer.setStatus("Cancelled", "idle");
        viewer.log("warn", "Stream cancelled");
      } else {
        viewer.setStatus("Error", "error");
        viewer.log("error", err?.message || String(err));
      }
    } finally {
      setBusy(false);
      currentInvocation = null;
    }
  });

  await refresh();
}

main().catch((err) => {
  const fallback = document.getElementById("logOutput");
  if (fallback) fallback.textContent += `Fatal error: ${err?.message || String(err)}\n`;
});
