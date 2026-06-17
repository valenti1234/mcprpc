package io.mcprpc.automesh;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class RegistryClient {
    private static final ObjectMapper MAPPER = SchemaUtils.MAPPER;
    private final HttpClient httpClient;
    private final String registryUrl;

    RegistryClient(String registryUrl) {
        this.registryUrl = registryUrl == null ? "" : registryUrl;
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .version(HttpClient.Version.HTTP_1_1)
            .build();
    }

    void publish(Map<String, Object> payload) throws IOException, InterruptedException {
        if (registryUrl.isBlank()) {
            return;
        }
        send("/register", payload);
    }

    void heartbeat(Map<String, Object> payload) throws IOException, InterruptedException {
        if (registryUrl.isBlank()) {
            return;
        }
        send("/heartbeat", payload);
    }

    Map<String, Object> buildPublishPayload(String serviceName, String meshId, String runtime, String mcpTransport, String endpoint, ToolMetadata metadata) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("name", metadata.name());
        payload.put("mesh_id", meshId);
        payload.put("service_name", serviceName);
        payload.put("runtime", runtime);
        payload.put("transport", "mcp");
        payload.put("mcp_transport", mcpTransport);
        payload.put("endpoint", endpoint);
        payload.put("description", metadata.description());
        payload.put("inputSchema", metadata.inputSchema());
        payload.put("outputSchema", metadata.outputSchema());
        payload.put("acl", metadata.acl());
        payload.put("cost", metadata.cost());
        payload.put("tags", metadata.tags());
        payload.put("version", metadata.version());
        payload.put("health", "healthy");
        return payload;
    }

    Map<String, Object> buildHeartbeatPayload(String serviceName, String meshId, String runtime, String health, int heartbeatIntervalSeconds, List<String> tools, List<Map<String, Object>> registrations) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("service_name", serviceName);
        payload.put("mesh_id", meshId);
        payload.put("runtime", runtime);
        payload.put("health", health);
        payload.put("heartbeat_interval_s", heartbeatIntervalSeconds);
        payload.put("tools", tools);
        payload.put("registrations", registrations);
        return payload;
    }

    private void send(String path, Map<String, Object> payload) throws IOException, InterruptedException {
        URI uri = URI.create(registryUrl.endsWith("/") ? registryUrl.substring(0, registryUrl.length() - 1) + path : registryUrl + path);
        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(toJson(payload)))
            .build();
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IOException("Registry responded with status " + response.statusCode() + ": " + response.body());
        }
    }

    private String toJson(Map<String, Object> payload) throws JsonProcessingException {
        return MAPPER.writeValueAsString(payload);
    }
}
