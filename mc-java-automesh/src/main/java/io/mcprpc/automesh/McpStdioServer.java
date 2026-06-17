package io.mcprpc.automesh;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

final class McpStdioServer {
    private static final ObjectMapper MAPPER = SchemaUtils.MAPPER;
    private final AutoMesh autoMesh;
    private final InputStream input;
    private final OutputStream output;

    McpStdioServer(AutoMesh autoMesh, InputStream input, OutputStream output) {
        this.autoMesh = autoMesh;
        this.input = input;
        this.output = output;
    }

    void serve() throws IOException {
        while (true) {
            JsonNode message = readMessage();
            if (message == null) {
                return;
            }
            JsonNode response = handle(message);
            if (response != null) {
                writeMessage(response);
            }
        }
    }

    private JsonNode handle(JsonNode message) {
        String method = message.path("method").asText("");
        JsonNode id = message.get("id");
        try {
            return switch (method) {
                case "initialize" -> success(id, initializeResult());
                case "ping" -> success(id, MAPPER.createObjectNode());
                case "tools/list" -> success(id, toolsListResult());
                case "tools/call" -> success(id, callToolResult(message.path("params")));
                case "notifications/initialized" -> null;
                default -> id == null ? null : error(id, -32601, "Unknown method: " + method);
            };
        } catch (Exception exception) {
            return id == null ? null : error(id, -32000, exception.getMessage() == null ? exception.toString() : exception.getMessage());
        }
    }

    private ObjectNode initializeResult() {
        ObjectNode result = MAPPER.createObjectNode();
        result.put("protocolVersion", "2024-11-05");
        ObjectNode capabilities = result.putObject("capabilities");
        capabilities.putObject("tools").put("listChanged", false);
        ObjectNode serverInfo = result.putObject("serverInfo");
        serverInfo.put("name", autoMesh.serviceName());
        serverInfo.put("version", AutoMesh.VERSION);
        return result;
    }

    private ObjectNode toolsListResult() {
        ObjectNode result = MAPPER.createObjectNode();
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
        Object value = autoMesh.invoke(name, arguments.isMissingNode() ? MAPPER.createObjectNode() : arguments);
        ObjectNode result = MAPPER.createObjectNode();
        ArrayNode content = result.putArray("content");
        ObjectNode text = content.addObject();
        text.put("type", "text");
        text.put("text", autoMesh.stringifyResult(value));
        return result;
    }

    private ObjectNode success(JsonNode id, JsonNode result) {
        ObjectNode response = MAPPER.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", id);
        response.set("result", result);
        return response;
    }

    private ObjectNode error(JsonNode id, int code, String message) {
        ObjectNode response = MAPPER.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", id);
        ObjectNode error = response.putObject("error");
        error.put("code", code);
        error.put("message", message);
        return response;
    }

    private JsonNode readMessage() throws IOException {
        int contentLength = -1;
        String line;
        while (!(line = readHeaderLine()).isEmpty()) {
            String lower = line.toLowerCase(Locale.ROOT);
            if (lower.startsWith("content-length:")) {
                contentLength = Integer.parseInt(line.substring(line.indexOf(':') + 1).trim());
            }
        }
        if (contentLength < 0) {
            return null;
        }
        byte[] body = input.readNBytes(contentLength);
        if (body.length == 0) {
            return null;
        }
        return MAPPER.readTree(body);
    }

    private String readHeaderLine() throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        while (true) {
            int value = input.read();
            if (value == -1) {
                if (buffer.size() == 0) {
                    return "";
                }
                break;
            }
            if (value == '\r') {
                int next = input.read();
                if (next == '\n') {
                    break;
                }
                if (next != -1) {
                    buffer.write(next);
                }
            } else if (value == '\n') {
                break;
            } else {
                buffer.write(value);
            }
        }
        return buffer.toString(StandardCharsets.UTF_8);
    }

    private void writeMessage(JsonNode message) throws IOException {
        byte[] payload = MAPPER.writeValueAsBytes(message);
        String header = "Content-Length: " + payload.length + "\r\n\r\n";
        output.write(header.getBytes(StandardCharsets.UTF_8));
        output.write(payload);
        output.flush();
    }
}
