const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let registryIndex = new Map();

function setOutput(el, data) {
  if (typeof data === "string") {
    el.textContent = data;
    return;
  }
  el.textContent = JSON.stringify(data, null, 2);
}

async function readJsonResponse(resp) {
  const ct = (resp.headers.get("content-type") || "").toLowerCase();
  if (ct.includes("application/json")) {
    return await resp.json();
  }
  return await resp.text();
}

async function apiGet(path) {
  const resp = await fetch(path, { headers: { accept: "application/json" } });
  const data = await readJsonResponse(resp);
  if (!resp.ok) {
    throw { status: resp.status, data };
  }
  return data;
}

async function apiSend(method, path, body) {
  const resp = await fetch(path, {
    method,
    headers: { "content-type": "application/json", accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await readJsonResponse(resp);
  if (!resp.ok) {
    throw { status: resp.status, data };
  }
  return data;
}

function parseJsonTextarea(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) return undefined;
  return JSON.parse(trimmed);
}

function parseTags(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) return undefined;
  const items = trimmed
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x.length > 0);
  return items.length ? items : undefined;
}

function badgeForHealth(health) {
  const h = (health || "").toLowerCase();
  if (h === "healthy") return `<span class="badge ok">${health}</span>`;
  if (h === "unhealthy" || h === "expired") return `<span class="badge bad">${health}</span>`;
  return `<span class="badge">${health || ""}</span>`;
}

function setTab(tab) {
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("#panel-registry").classList.toggle("hidden", tab !== "registry");
  $("#panel-router").classList.toggle("hidden", tab !== "router");
}

async function initConfig() {
  try {
    const cfg = await apiGet("/api/config");
    $("#cfg").textContent = `REGISTRY_URL=${cfg.registry_url} | ROUTER_URL=${cfg.router_url}`;
  } catch (e) {
    $("#cfg").textContent = "Errore lettura configurazione";
  }
}

function filterRows(rows, search) {
  const s = (search || "").trim().toLowerCase();
  if (!s) return rows;
  return rows.filter((r) => {
    const hay = [
      r.name,
      r.service_name,
      r.mesh_id,
      r.runtime,
      r.mcp_transport,
      r.endpoint,
      r.health,
    ]
      .map((x) => (x || "").toString().toLowerCase())
      .join(" ");
    return hay.includes(s);
  });
}

async function loadFunctions() {
  const out = $("#output");
  try {
    const tag = $("#reg-filter-tag").value.trim();
    const runtime = $("#reg-filter-runtime").value.trim();
    const qs = new URLSearchParams();
    if (tag) qs.set("tag", tag);
    if (runtime) qs.set("runtime", runtime);
    const data = await apiGet(`/api/registry/functions${qs.toString() ? "?" + qs.toString() : ""}`);
    const filtered = filterRows(data, $("#reg-search").value);
    renderFunctions(filtered);
    setOutput(out, { count: filtered.length, tag: tag || null, runtime: runtime || null });
  } catch (e) {
    setOutput(out, e.data || e);
  }
}

function buildArgsTemplate(inputSchema) {
  if (!inputSchema || typeof inputSchema !== "object") return {};
  const props = inputSchema.properties;
  if (!props || typeof props !== "object") return {};
  const out = {};
  for (const [k, v] of Object.entries(props)) {
    const t = v && typeof v === "object" ? v.type : undefined;
    if (t === "number" || t === "integer") out[k] = 0;
    else if (t === "boolean") out[k] = false;
    else if (t === "array") out[k] = [];
    else if (t === "object") out[k] = {};
    else out[k] = null;
  }
  return out;
}

function selectRegistryFunction(name) {
  const fn = registryIndex.get(name);
  if (!fn) return;

  $("#c-function").value = fn.name || "";

  const rolesFromAcl = fn.acl && Array.isArray(fn.acl.roles) ? fn.acl.roles : null;
  $("#c-roles").value = rolesFromAcl ? rolesFromAcl.join(", ") : "";
  $("#c-tenant").value = "";

  const argsTemplate = buildArgsTemplate(fn.inputSchema);
  $("#c-args").value = JSON.stringify(argsTemplate, null, 2);

  setTab("router");
  const out = $("#router-output");
  setOutput(out, {
    selected: fn.name,
    service_name: fn.service_name,
    mesh_id: fn.mesh_id,
    runtime: fn.runtime,
    mcp_transport: fn.mcp_transport,
    endpoint: fn.endpoint,
  });
  $("#call-form").scrollIntoView({ block: "start", behavior: "smooth" });
}

function renderFunctions(items) {
  const tbody = $("#reg-table tbody");
  tbody.innerHTML = "";
  registryIndex = new Map();
  for (const fn of items) {
    if (fn && fn.name) registryIndex.set(fn.name, fn);
    const tr = document.createElement("tr");
    tr.classList.add("clickable");
    tr.setAttribute("data-name", fn.name || "");
    tr.innerHTML = `
      <td class="mono">${escapeHtml(fn.name || "")}</td>
      <td>${escapeHtml(fn.service_name || "")}</td>
      <td class="mono">${escapeHtml(fn.mesh_id || "")}</td>
      <td>${escapeHtml(fn.runtime || "")}</td>
      <td>${escapeHtml(fn.mcp_transport || "")}</td>
      <td class="mono">${escapeHtml(fn.endpoint || "")}</td>
      <td>${badgeForHealth(fn.health)}</td>
      <td><button class="danger" data-del="${escapeHtml(fn.name || "")}">Delete</button></td>
    `;
    tr.addEventListener("click", (e) => {
      const t = e.target;
      if (t && (t.tagName === "BUTTON" || t.closest("button"))) return;
      const selectedName = tr.getAttribute("data-name");
      if (!selectedName) return;
      selectRegistryFunction(selectedName);
    });
    tbody.appendChild(tr);
  }

  $$("button[data-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.getAttribute("data-del");
      if (!name) return;
      await deleteFunction(name);
    });
  });
}

async function deleteFunction(name) {
  const out = $("#output");
  try {
    const data = await apiSend("DELETE", `/api/registry/functions/${encodeURIComponent(name)}`);
    setOutput(out, data);
    await loadFunctions();
  } catch (e) {
    setOutput(out, e.data || e);
  }
}

async function registryAction(path) {
  const out = $("#output");
  try {
    const data = await apiGet(path);
    setOutput(out, data);
  } catch (e) {
    setOutput(out, e.data || e);
  }
}

async function routerAction(path) {
  const out = $("#router-output");
  try {
    const data = await apiGet(path);
    setOutput(out, data);
  } catch (e) {
    setOutput(out, e.data || e);
  }
}

async function registerFromForm(e) {
  e.preventDefault();
  const out = $("#output");
  try {
    const payload = {
      name: $("#f-name").value.trim(),
      mesh_id: $("#f-mesh").value.trim(),
      service_name: $("#f-service").value.trim(),
      runtime: $("#f-runtime").value.trim(),
      transport: "mcp",
      mcp_transport: $("#f-mcp-transport").value,
      endpoint: $("#f-endpoint").value.trim(),
    };

    const description = $("#f-description").value.trim();
    if (description) payload.description = description;

    const health = $("#f-health").value.trim();
    if (health) payload.health = health;

    const version = $("#f-version").value.trim();
    if (version) payload.version = version;

    const tags = parseTags($("#f-tags").value);
    if (tags) payload.tags = tags;

    const acl = parseJsonTextarea($("#f-acl").value);
    if (acl !== undefined) payload.acl = acl;

    const inputSchema = parseJsonTextarea($("#f-input").value);
    if (inputSchema !== undefined) payload.inputSchema = inputSchema;

    const outputSchema = parseJsonTextarea($("#f-output").value);
    if (outputSchema !== undefined) payload.outputSchema = outputSchema;

    const cost = parseJsonTextarea($("#f-cost").value);
    if (cost !== undefined) payload.cost = cost;

    const data = await apiSend("POST", "/api/registry/register", payload);
    setOutput(out, data);
    await loadFunctions();
  } catch (e2) {
    if (e2 instanceof SyntaxError) {
      setOutput(out, { error: "JSON non valido in uno dei campi textarea" });
      return;
    }
    setOutput(out, e2.data || e2);
  }
}

function clearRegisterForm() {
  ["#f-name", "#f-mesh", "#f-service", "#f-runtime", "#f-endpoint", "#f-description", "#f-health", "#f-version", "#f-tags", "#f-acl", "#f-input", "#f-output", "#f-cost"].forEach(
    (id) => {
      const el = $(id);
      if (el) el.value = "";
    }
  );
  $("#f-mcp-transport").value = "stdio";
}

async function callRouter(e) {
  e.preventDefault();
  const out = $("#router-output");
  try {
    const fn = $("#c-function").value.trim();
    const roles = parseTags($("#c-roles").value) || [];
    const tenant = $("#c-tenant").value.trim();
    const args = parseJsonTextarea($("#c-args").value) || {};

    const payload = {
      function: fn,
      arguments: args,
      context: {
        roles,
      },
    };
    if (tenant) payload.context.tenant = tenant;

    const data = await apiSend("POST", "/api/router/call", payload);
    setOutput(out, data);
  } catch (e2) {
    if (e2 instanceof SyntaxError) {
      setOutput(out, { error: "Arguments JSON non valido" });
      return;
    }
    setOutput(out, e2.data || e2);
  }
}

function escapeHtml(s) {
  return (s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function wireUi() {
  $$(".tab").forEach((b) =>
    b.addEventListener("click", () => {
      setTab(b.dataset.tab);
    })
  );

  $("#reg-refresh").addEventListener("click", loadFunctions);
  $("#reg-health").addEventListener("click", () => registryAction("/api/registry/health"));
  $("#reg-ready").addEventListener("click", () => registryAction("/api/registry/ready"));
  $("#reg-stats").addEventListener("click", () => registryAction("/api/registry/stats"));
  $("#reg-heartbeats").addEventListener("click", () => registryAction("/api/registry/heartbeats"));

  $("#reg-filter-tag").addEventListener("change", loadFunctions);
  $("#reg-filter-runtime").addEventListener("change", loadFunctions);
  $("#reg-search").addEventListener("input", loadFunctions);

  $("#reg-form").addEventListener("submit", registerFromForm);
  $("#reg-form-clear").addEventListener("click", clearRegisterForm);

  $("#rt-health").addEventListener("click", () => routerAction("/api/router/health"));
  $("#rt-ready").addEventListener("click", () => routerAction("/api/router/ready"));
  $("#rt-stats").addEventListener("click", () => routerAction("/api/router/stats"));

  $("#call-form").addEventListener("submit", callRouter);
}

async function boot() {
  wireUi();
  await initConfig();
  await loadFunctions();
}

boot();
