package io.mcprpc.automesh.examples;

import io.mcprpc.automesh.AutoMesh;
import java.util.logging.Logger;

public final class BillingApiExampleMain {
    private static final Logger LOGGER = Logger.getLogger(BillingApiExampleMain.class.getName());

    private BillingApiExampleMain() {
    }

    public static void main(String[] args) throws Exception {
        String registryUrl = System.getenv().getOrDefault("REGISTRY_URL", "");
        String transport = System.getenv().getOrDefault("MCP_TRANSPORT", "sse");
        String endpoint = System.getenv().get("AUTOMESH_ENDPOINT");

        LOGGER.info(() -> "example_start service=java-billing-api transport=" + transport + " endpoint=" + endpoint + " registryUrl=" + registryUrl);

        AutoMesh mesh = AutoMesh.builder()
            .serviceName("java-billing-api")
            .registryUrl(registryUrl)
            .mcpTransport(transport)
            .endpoint(endpoint)
            .build();

        mesh.publishInstance(new BillingApi());
        LOGGER.info(() -> "example_publish_complete tools=" + mesh.toolNames());
        mesh.registerAll();
        LOGGER.info("example_register_complete");
        LOGGER.info("example_serve_start");
        mesh.serve();
    }
}
