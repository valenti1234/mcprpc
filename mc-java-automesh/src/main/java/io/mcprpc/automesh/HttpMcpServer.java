package io.mcprpc.automesh;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

final class HttpMcpServer {
    private static final int KEEPALIVE_SECONDS = 15;

    private final AutoMesh autoMesh;
    private final String bindHost;
    private final URI endpointUri;
    private final String transportName;
    private final HttpServer server;
    private final String endpointPath;
    private final String messagesBasePath;
    private final Map<String, Session> sessions = new ConcurrentHashMap<>();

    HttpMcpServer(AutoMesh autoMesh, String bindHost, String endpointUrl, String transportName) throws IOException {
        this.autoMesh = autoMesh;
        this.bindHost = bindHost;
        this.endpointUri = URI.create(endpointUrl);
        this.transportName = transportName;
        int port = endpointUri.getPort() > 0 ? endpointUri.getPort() : 7002;
        this.endpointPath = normalizedPath(endpointUri.getPath(), "sse".equals(transportName) ? "/sse" : "/mcp");
        this.messagesBasePath = "sse".equals(transportName)
            ? "/messages"
            : normalizedPath(this.endpointPath + "/messages", this.endpointPath + "/messages");
        this.server = HttpServer.create(new InetSocketAddress(bindHost, port), 0);
        this.server.createContext("/", new RootHandler());
        this.server.setExecutor(
            Executors.newCachedThreadPool(r -> {
                Thread t = new Thread(r, "mc-java-automesh-http");
                t.setDaemon(true);
                return t;
            })
        );
    }

    void serve() {
        System.err.println(
            "event=http_server_start service_name="
                + autoMesh.serviceName()
                + " transport="
                + transportName
                + " bind="
                + bindHost
                + ":"
                + server.getAddress().getPort()
                + " endpoint="
                + endpointUri
        );
        server.start();
    }

    void stop() {
        server.stop(0);
        for (Session session : new ArrayList<>(sessions.values())) {
            session.close();
        }
        sessions.clear();
    }

    private String endpointEventData(HttpExchange exchange, String sessionId) {
        String host = exchange.getRequestHeaders().getFirst("Host");
        if (host == null || host.isBlank()) {
            host = bindHost + ":" + server.getAddress().getPort();
        }
        String scheme = "http";
        return scheme + "://" + host + messagesBasePath + "?sessionId=" + sessionId;
    }

    private static String normalizedPath(String raw, String fallback) {
        String path = (raw == null || raw.isBlank()) ? fallback : raw;
        if (!path.startsWith("/")) {
            path = "/" + path;
        }
        while (path.length() > 1 && path.endsWith("/")) {
            path = path.substring(0, path.length() - 1);
        }
        return path;
    }

    private final class RootHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            try {
                String path = normalizedPath(exchange.getRequestURI().getPath(), "/");
                String method = exchange.getRequestMethod().toUpperCase();
                if (endpointPath.equals(path) || messagesBasePath.equals(path) || "/health".equals(path)) {
                    System.err.println(
                        "event=http_request service_name="
                            + autoMesh.serviceName()
                            + " transport="
                            + transportName
                            + " method="
                            + method
                            + " path="
                            + exchange.getRequestURI().getPath()
                            + " query="
                            + (exchange.getRequestURI().getRawQuery() == null ? "" : exchange.getRequestURI().getRawQuery())
                            + " remote="
                            + exchange.getRemoteAddress()
                    );
                }

                if ("GET".equals(method) && "/health".equals(path)) {
                    writeJson(exchange, 200, healthPayload());
                    return;
                }

                if ("sse".equals(transportName)) {
                    if ("GET".equals(method) && endpointPath.equals(path)) {
                        handleSseConnect(exchange);
                        return;
                    }
                    if ("POST".equals(method) && messagesBasePath.equals(path)) {
                        handleSseMessage(exchange);
                        return;
                    }
                } else {
                    if ("GET".equals(method) && endpointPath.equals(path)) {
                        handleSseConnect(exchange);
                        return;
                    }
                    if ("POST".equals(method) && path.equals(messagesBasePath)) {
                        handleSseMessage(exchange);
                        return;
                    }
                    if ("POST".equals(method) && endpointPath.equals(path)) {
                        handleStreamablePost(exchange);
                        return;
                    }
                }

                writePlain(exchange, 404, "Not Found");
            } catch (Exception exception) {
                writePlain(exchange, 500, exception.getMessage() == null ? exception.toString() : exception.getMessage());
            } finally {
                if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                    exchange.close();
                }
            }
        }
    }

    private void handleSseConnect(HttpExchange exchange) throws IOException {
        String sessionId = UUID.randomUUID().toString().replace("-", "");
        Session session = new Session(sessionId, exchange);
        sessions.put(sessionId, session);
        session.start(endpointEventData(exchange, sessionId));
    }

    private void handleSseMessage(HttpExchange exchange) throws IOException {
        String sessionId = queryParam(exchange.getRequestURI(), "sessionId");
        if (sessionId == null || sessionId.isBlank()) {
            writePlain(exchange, 400, "Missing sessionId");
            return;
        }
        Session session = sessions.get(sessionId);
        if (session == null || !session.isOpen()) {
            writePlain(exchange, 404, "Unknown sessionId");
            return;
        }
        JsonNode request = readJson(exchange);
        JsonNode response = session.handleRequest(request);
        if (response != null) {
            session.enqueueMessage(response.toString());
        }
        writePlain(exchange, 202, "Accepted");
    }

    private void handleStreamablePost(HttpExchange exchange) throws IOException {
        JsonNode request = readJson(exchange);
        JsonNode response = handleJsonRpc(request);
        if (response == null) {
            exchange.sendResponseHeaders(202, -1);
            return;
        }
        if (wantsEventStream(exchange)) {
            exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
            exchange.getResponseHeaders().set("Cache-Control", "no-cache");
            exchange.getResponseHeaders().set("Connection", "keep-alive");
            exchange.sendResponseHeaders(200, 0);
            try (OutputStream out = exchange.getResponseBody()) {
                writeSseEvent(out, "message", response.toString());
                out.flush();
            }
            return;
        }
        writeJson(exchange, 200, response);
    }

    private ObjectNode healthPayload() {
        ObjectNode payload = SchemaUtils.MAPPER.createObjectNode();
        payload.put("status", "ok");
        payload.put("service", autoMesh.serviceName());
        payload.put("runtime", "java");
        payload.put("version", AutoMesh.VERSION);
        payload.put("tools", autoMesh.toolCount());
        payload.put("mcp_transport", transportName);
        return payload;
    }

    private boolean wantsEventStream(HttpExchange exchange) {
        List<String> acceptValues = exchange.getRequestHeaders().getOrDefault("Accept", List.of());
        for (String value : acceptValues) {
            if (value != null && value.contains("text/event-stream")) {
                return true;
            }
        }
        return false;
    }

    private JsonNode handleJsonRpc(JsonNode request) {
        String method = request.path("method").asText("");
        JsonNode id = request.get("id");
        try {
            return switch (method) {
                case "initialize" -> success(id, initializeResult());
                case "ping" -> success(id, SchemaUtils.MAPPER.createObjectNode());
                case "tools/list" -> success(id, toolsListResult());
                case "tools/call" -> success(id, callToolResult(request.path("params")));
                case "notifications/initialized" -> null;
                default -> id == null ? null : error(id, -32601, "Unknown method: " + method);
            };
        } catch (Exception exception) {
            return id == null ? null : error(id, -32000, exception.getMessage() == null ? exception.toString() : exception.getMessage());
        }
    }

    private ObjectNode initializeResult() {
        ObjectNode result = SchemaUtils.MAPPER.createObjectNode();
        result.put("protocolVersion", "2024-11-05");
        ObjectNode capabilities = result.putObject("capabilities");
        capabilities.putObject("tools");
        ObjectNode serverInfo = result.putObject("serverInfo");
        serverInfo.put("name", autoMesh.serviceName());
        serverInfo.put("version", AutoMesh.VERSION);
        return result;
    }

    private ObjectNode toolsListResult() {
        ObjectNode result = SchemaUtils.MAPPER.createObjectNode();
        ArrayNode tools = result.putArray("tools");
        for (ToolRegistration registration : autoMesh.tools().values()) {
            ToolMetadata metadata = registration.metadata();
            ObjectNode tool = tools.addObject();
            tool.put("name", metadata.name());
            tool.put("description", metadata.description());
            tool.set("inputSchema", metadata.inputSchema());
        }
        return result;
    }

    private ObjectNode callToolResult(JsonNode params) throws Exception {
        String name = params.path("name").asText();
        JsonNode arguments = params.path("arguments");
        Object value = autoMesh.invoke(name, arguments.isMissingNode() ? SchemaUtils.MAPPER.createObjectNode() : arguments);
        ObjectNode result = SchemaUtils.MAPPER.createObjectNode();
        ArrayNode content = result.putArray("content");
        ObjectNode text = content.addObject();
        text.put("type", "text");
        text.put("text", autoMesh.stringifyResult(value));
        return result;
    }

    private ObjectNode success(JsonNode id, JsonNode result) {
        ObjectNode response = SchemaUtils.MAPPER.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", id);
        response.set("result", result);
        return response;
    }

    private ObjectNode error(JsonNode id, int code, String message) {
        ObjectNode response = SchemaUtils.MAPPER.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", id);
        ObjectNode error = response.putObject("error");
        error.put("code", code);
        error.put("message", message);
        return response;
    }

    private JsonNode readJson(HttpExchange exchange) throws IOException {
        try (InputStream in = exchange.getRequestBody()) {
            byte[] body = in.readAllBytes();
            return SchemaUtils.MAPPER.readTree(body);
        }
    }

    private void writeJson(HttpExchange exchange, int status, JsonNode payload) throws IOException {
        byte[] body = SchemaUtils.MAPPER.writeValueAsBytes(payload);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    private void writePlain(HttpExchange exchange, int status, String text) throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    private static void writeSseEvent(OutputStream out, String event, String data) throws IOException {
        StringBuilder builder = new StringBuilder();
        builder.append("event: ").append(event).append("\n");
        for (String line : data.split("\n", -1)) {
            builder.append("data: ").append(line).append("\n");
        }
        builder.append("\n");
        out.write(builder.toString().getBytes(StandardCharsets.UTF_8));
    }

    private static String queryParam(URI uri, String name) {
        String query = uri.getRawQuery();
        if (query == null || query.isBlank()) {
            return null;
        }
        for (String pair : query.split("&")) {
            int idx = pair.indexOf('=');
            String k = idx >= 0 ? pair.substring(0, idx) : pair;
            if (!name.equals(URLDecoder.decode(k, StandardCharsets.UTF_8))) {
                continue;
            }
            String v = idx >= 0 ? pair.substring(idx + 1) : "";
            return URLDecoder.decode(v, StandardCharsets.UTF_8);
        }
        return null;
    }

    private final class Session {
        private final String sessionId;
        private final HttpExchange exchange;
        private final BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        private volatile boolean open = true;

        Session(String sessionId, HttpExchange exchange) {
            this.sessionId = sessionId;
            this.exchange = exchange;
        }

        boolean isOpen() {
            return open;
        }

        void start(String endpointData) throws IOException {
            exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
            exchange.getResponseHeaders().set("Cache-Control", "no-cache");
            exchange.getResponseHeaders().set("Connection", "keep-alive");
            exchange.sendResponseHeaders(200, 0);
            try (OutputStream out = exchange.getResponseBody()) {
                writeSseEvent(out, "endpoint", endpointData);
                out.flush();
                Instant lastKeepalive = Instant.now();
                while (open) {
                    String message = queue.poll(1, TimeUnit.SECONDS);
                    if (message != null) {
                        writeSseEvent(out, "message", message);
                        out.flush();
                        lastKeepalive = Instant.now();
                    } else if (Duration.between(lastKeepalive, Instant.now()).getSeconds() >= KEEPALIVE_SECONDS) {
                        out.write(": keepalive\n\n".getBytes(StandardCharsets.UTF_8));
                        out.flush();
                        lastKeepalive = Instant.now();
                    }
                }
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            } catch (IOException ignored) {
                // Client disconnected.
            } finally {
                close();
                exchange.close();
            }
        }

        JsonNode handleRequest(JsonNode request) {
            return handleJsonRpc(request);
        }

        void enqueueMessage(String message) {
            if (open) {
                queue.offer(message);
            }
        }

        void close() {
            open = false;
            sessions.remove(sessionId);
        }
    }
}
