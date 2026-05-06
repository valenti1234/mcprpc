import { PublishPayload } from "./types.js";

/**
 * RegistryClient handles publishing tools to the MCPRPC registry.
 */
export class RegistryClient {
  private registryUrl: string;

  constructor(registryUrl: string) {
    this.registryUrl = registryUrl;
  }

  /**
   * Publishes a tool to the registry.
   */
  async publish(payload: PublishPayload): Promise<void> {
    const url = new URL("/register", this.registryUrl).href;

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`Registry responded with status ${response.status}: ${text}`);
      }
      console.warn(
        `event=registry_publish ok=true name=${payload.name} service_name=${payload.service_name} mesh_id=${payload.mesh_id}`
      );
    } catch (error: any) {
      console.warn(
        `event=registry_publish ok=false name=${payload.name} service_name=${payload.service_name} mesh_id=${payload.mesh_id} error=${error.message}`
      );
      throw new Error(`Failed to publish to registry: ${error.message}`);
    }
  }

  async heartbeat(payload: {
    service_name: string;
    mesh_id: string;
    runtime?: string;
    health: string;
    tools?: string[];
    heartbeat_interval_s?: number;
    registrations?: PublishPayload[];
  }): Promise<void> {
    const url = new URL("/heartbeat", this.registryUrl).href;

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`Registry responded with status ${response.status}: ${text}`);
      }
      console.warn(
        `event=registry_heartbeat ok=true service_name=${payload.service_name} mesh_id=${payload.mesh_id} health=${payload.health}`
      );
    } catch (error: any) {
      console.warn(
        `event=registry_heartbeat ok=false service_name=${payload.service_name} mesh_id=${payload.mesh_id} health=${payload.health} error=${error.message}`
      );
      throw new Error(`Failed to send heartbeat to registry: ${error.message}`);
    }
  }
}
