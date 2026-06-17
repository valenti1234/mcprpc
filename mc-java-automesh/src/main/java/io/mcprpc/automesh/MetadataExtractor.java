package io.mcprpc.automesh;

import com.fasterxml.jackson.databind.JsonNode;
import io.mcprpc.automesh.annotations.Expose;
import io.mcprpc.automesh.annotations.InputMode;
import java.beans.Introspector;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class MetadataExtractor {
    private MetadataExtractor() {
    }

    static ToolMetadata extract(Method method) {
        Expose expose = method.getAnnotation(Expose.class);
        String namespace = Introspector.decapitalize(method.getDeclaringClass().getSimpleName());
        String name = expose != null && !expose.name().isBlank()
            ? expose.name()
            : namespace + "." + method.getName();
        String description = expose != null && !expose.description().isBlank()
            ? expose.description()
            : "Auto-published method " + name;
        JsonNode inputSchema = SchemaUtils.inputSchema(method);
        JsonNode outputSchema = SchemaUtils.outputSchema(method);
        Map<String, Object> acl = new LinkedHashMap<>();
        Map<String, Object> cost = new LinkedHashMap<>();
        List<String> tags = List.of(namespace);
        String version = "0.1.0";
        InputMode inputMode = InputMode.OBJECT;
        List<String> parameters = Arrays.stream(method.getParameters()).map(p -> p.getName()).toList();

        if (expose != null) {
            if (expose.roles().length > 0) {
                acl.put("roles", List.of(expose.roles()));
            }
            if (expose.costCpuWeight() >= 0) {
                cost.put("cpuWeight", expose.costCpuWeight());
            }
            if (expose.tags().length > 0) {
                tags = List.of(expose.tags());
            }
            if (!expose.version().isBlank()) {
                version = expose.version();
            }
            inputMode = expose.inputMode();
            if (expose.parameters().length > 0) {
                parameters = List.of(expose.parameters());
            }
        }

        return new ToolMetadata(name, description, inputSchema, outputSchema, acl, cost, tags, version, inputMode, parameters, method);
    }
}
