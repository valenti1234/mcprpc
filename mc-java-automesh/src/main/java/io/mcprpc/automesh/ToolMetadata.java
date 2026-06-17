package io.mcprpc.automesh;

import com.fasterxml.jackson.databind.JsonNode;
import io.mcprpc.automesh.annotations.InputMode;
import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;

public record ToolMetadata(
    String name,
    String description,
    JsonNode inputSchema,
    JsonNode outputSchema,
    Map<String, Object> acl,
    Map<String, Object> cost,
    List<String> tags,
    String version,
    InputMode inputMode,
    List<String> parameters,
    Method method
) {
}
