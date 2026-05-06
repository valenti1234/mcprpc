import path from "node:path";
import fs from "node:fs/promises";
import { pathToFileURL } from "node:url";

/**
 * Discovers exported functions from a module file.
 */
export async function discoverFunctions(modulePath: string) {
  const absolutePath = path.resolve(modulePath);
  const parsed = path.parse(absolutePath);
  const moduleName = parsed.name;

  let mod: any;
  try {
    mod = await import(pathToFileURL(absolutePath).href);
  } catch (err) {
    throw new Error(`Failed to load module ${absolutePath}: ${err}`);
  }

  const discovered: { functionName: string; fn: any; moduleName: string }[] = [];

  for (const [key, value] of Object.entries(mod)) {
    // Ignore default export or non-functions
    if (key === "default" || typeof value !== "function") {
      continue;
    }

    // Ignore private names starting with _
    if (key.startsWith("_")) {
      continue;
    }

    // Check for ignored metadata
    const meta = (value as any)[Symbol.for("mcprpc.metadata")];
    if (meta && meta.ignored) {
      continue;
    }

    discovered.push({
      functionName: key,
      fn: value,
      moduleName,
    });
  }

  return discovered;
}

/**
 * Discovers functions recursively from a directory path.
 */
export async function discoverPath(directoryPath: string) {
  const absoluteDir = path.resolve(directoryPath);
  const entries = await fs.readdir(absoluteDir, { withFileTypes: true });

  const discovered: { functionName: string; fn: any; moduleName: string }[] = [];

  for (const entry of entries) {
    const fullPath = path.join(absoluteDir, entry.name);
    if (entry.isDirectory()) {
      discovered.push(...(await discoverPath(fullPath)));
    } else if (entry.isFile() && (entry.name.endsWith(".js") || entry.name.endsWith(".ts") || entry.name.endsWith(".cjs") || entry.name.endsWith(".mjs"))) {
      if (!entry.name.endsWith(".d.ts")) {
        discovered.push(...(await discoverFunctions(fullPath)));
      }
    }
  }

  return discovered;
}
