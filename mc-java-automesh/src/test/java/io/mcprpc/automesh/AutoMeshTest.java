package io.mcprpc.automesh;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.mcprpc.automesh.fixtures.BillingService;
import io.mcprpc.automesh.fixtures.UtilityTools;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class AutoMeshTest {
    @Test
    void discoversInstanceAndStaticMethods() {
        AutoMesh mesh = AutoMesh.builder()
            .serviceName("test-service")
            .build();

        mesh.publishInstance(new BillingService());
        mesh.publishClass(UtilityTools.class);

        assertTrue(mesh.tools().containsKey("billing.calculateVat"));
        assertTrue(mesh.tools().containsKey("billingService.createInvoice"));
        assertTrue(mesh.tools().containsKey("utilityTools.add"));
        assertFalse(mesh.tools().containsKey("billingService.dangerousFunction"));
        assertFalse(mesh.tools().containsKey("billingService._privateStyleMethod"));
    }

    @Test
    void extractsAnnotationMetadataAndSchema() {
        AutoMesh mesh = AutoMesh.builder()
            .serviceName("test-service")
            .build();

        mesh.publishInstance(new BillingService());
        ToolMetadata metadata = mesh.tools().get("billing.calculateVat").metadata();

        assertEquals("Calculate VAT", metadata.description());
        assertEquals(List.of("billing"), metadata.tags());
        assertEquals(List.of("amount", "rate"), metadata.parameters());
        assertEquals(List.of("billing", "admin"), metadata.acl().get("roles"));
        assertEquals(1, metadata.cost().get("cpuWeight"));
        assertEquals("object", metadata.inputSchema().get("type").asText());
        assertNotNull(metadata.inputSchema().get("properties").get("amount"));
        assertNotNull(metadata.inputSchema().get("properties").get("rate"));
    }

    @Test
    void invokesToolAndSerializesResult() throws Exception {
        AutoMesh mesh = AutoMesh.builder()
            .serviceName("test-service")
            .build();
        mesh.publishInstance(new BillingService());
        mesh.publishClass(UtilityTools.class);

        ObjectNode invoiceArgs = SchemaUtils.MAPPER.createObjectNode().put("customerId", "cust-1");
        Object invoice = mesh.invoke("billingService.createInvoice", invoiceArgs);
        String invoiceText = mesh.stringifyResult(invoice);
        assertTrue(invoiceText.contains("invoiceId"));

        ObjectNode addArgs = SchemaUtils.MAPPER.createObjectNode().put("a", 2).put("b", 3);
        Object sum = mesh.invoke("utilityTools.add", addArgs);
        assertEquals("5", mesh.stringifyResult(sum));
    }

    @Test
    void publishesToRegistry() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(0), 0);
        List<String> registerBodies = new ArrayList<>();
        List<String> heartbeatBodies = new ArrayList<>();
        server.createContext("/register", exchange -> writeOk(exchange, readBody(exchange, registerBodies)));
        server.createContext("/heartbeat", exchange -> writeOk(exchange, readBody(exchange, heartbeatBodies)));
        server.start();
        try {
            AutoMesh mesh = AutoMesh.builder()
                .serviceName("test-service")
                .registryUrl("http://127.0.0.1:" + server.getAddress().getPort())
                .meshId("mesh-1")
                .heartbeatIntervalSeconds(1)
                .build();
            mesh.publishInstance(new BillingService());

            mesh.registerAll();
            mesh.heartbeatOnce("healthy");

            assertFalse(registerBodies.isEmpty());
            assertFalse(heartbeatBodies.isEmpty());
            JsonNode publish = SchemaUtils.MAPPER.readTree(registerBodies.get(0));
            assertEquals("test-service", publish.get("service_name").asText());
            assertEquals("java", publish.get("runtime").asText());
            assertEquals("mcp", publish.get("transport").asText());
            assertEquals("stdio", publish.get("mcp_transport").asText());

            JsonNode heartbeat = SchemaUtils.MAPPER.readTree(heartbeatBodies.get(0));
            assertEquals("mesh-1", heartbeat.get("mesh_id").asText());
            assertEquals("healthy", heartbeat.get("health").asText());
            assertTrue(heartbeat.get("tools").isArray());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void scansPackage() {
        AutoMesh mesh = AutoMesh.builder()
            .serviceName("test-service")
            .build();

        mesh.publishPackage("io.mcprpc.automesh.fixtures");

        assertTrue(mesh.tools().containsKey("billing.calculateVat"));
        assertTrue(mesh.tools().containsKey("utilityTools.add"));
    }

    private static String readBody(HttpExchange exchange, List<String> bodies) throws IOException {
        try (InputStream stream = exchange.getRequestBody()) {
            String body = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            bodies.add(body);
            return body;
        }
    }

    private static void writeOk(HttpExchange exchange, String ignored) throws IOException {
        byte[] response = "{}".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, response.length);
        exchange.getResponseBody().write(response);
        exchange.close();
    }
}
