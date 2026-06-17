package io.mcprpc.automesh;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.beans.Introspector;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

final class SchemaUtils {
    static final ObjectMapper MAPPER = new ObjectMapper();
    private static final Set<Class<?>> INTEGER_TYPES = Set.of(
        byte.class, short.class, int.class, long.class,
        Byte.class, Short.class, Integer.class, Long.class,
        BigInteger.class
    );
    private static final Set<Class<?>> NUMBER_TYPES = Set.of(
        float.class, double.class, Float.class, Double.class, BigDecimal.class
    );

    private SchemaUtils() {
    }

    static ObjectNode inputSchema(Method method) {
        ObjectNode schema = MAPPER.createObjectNode();
        schema.put("type", "object");
        ObjectNode properties = schema.putObject("properties");
        ArrayNode required = MAPPER.createArrayNode();

        for (Parameter parameter : method.getParameters()) {
            properties.set(parameter.getName(), schemaForType(parameter.getParameterizedType(), new LinkedHashSet<>()));
            if (isRequired(parameter)) {
                required.add(parameter.getName());
            }
        }

        if (!required.isEmpty()) {
            schema.set("required", required);
        }
        schema.put("additionalProperties", false);
        return schema;
    }

    static JsonNode outputSchema(Method method) {
        return schemaForType(method.getGenericReturnType(), new LinkedHashSet<>());
    }

    private static boolean isRequired(Parameter parameter) {
        Class<?> type = parameter.getType();
        return !Optional.class.equals(type);
    }

    static JsonNode schemaForType(Type type, Set<String> seen) {
        if (type instanceof ParameterizedType parameterizedType) {
            Type raw = parameterizedType.getRawType();
            if (raw instanceof Class<?> rawClass && Optional.class.isAssignableFrom(rawClass)) {
                return schemaForType(parameterizedType.getActualTypeArguments()[0], seen);
            }
            if (raw instanceof Class<?> rawClass && Collection.class.isAssignableFrom(rawClass)) {
                ObjectNode schema = MAPPER.createObjectNode();
                schema.put("type", "array");
                Type itemType = parameterizedType.getActualTypeArguments().length > 0
                    ? parameterizedType.getActualTypeArguments()[0]
                    : Object.class;
                schema.set("items", schemaForType(itemType, seen));
                return schema;
            }
            if (raw instanceof Class<?> rawClass && Map.class.isAssignableFrom(rawClass)) {
                ObjectNode schema = MAPPER.createObjectNode();
                schema.put("type", "object");
                Type valueType = parameterizedType.getActualTypeArguments().length > 1
                    ? parameterizedType.getActualTypeArguments()[1]
                    : Object.class;
                schema.set("additionalProperties", schemaForType(valueType, seen));
                return schema;
            }
        }

        if (!(type instanceof Class<?> clazz)) {
            return fallbackSchema();
        }

        if (void.class.equals(clazz) || Void.class.equals(clazz)) {
            return MAPPER.createObjectNode().put("type", "null");
        }
        if (INTEGER_TYPES.contains(clazz)) {
            return MAPPER.createObjectNode().put("type", "integer");
        }
        if (NUMBER_TYPES.contains(clazz)) {
            return MAPPER.createObjectNode().put("type", "number");
        }
        if (boolean.class.equals(clazz) || Boolean.class.equals(clazz)) {
            return MAPPER.createObjectNode().put("type", "boolean");
        }
        if (String.class.equals(clazz) || Character.class.equals(clazz) || char.class.equals(clazz)
            || Instant.class.equals(clazz) || LocalDate.class.equals(clazz) || LocalDateTime.class.equals(clazz)) {
            return MAPPER.createObjectNode().put("type", "string");
        }
        if (clazz.isEnum()) {
            ObjectNode schema = MAPPER.createObjectNode().put("type", "string");
            ArrayNode values = schema.putArray("enum");
            Object[] constants = clazz.getEnumConstants();
            if (constants != null) {
                for (Object constant : constants) {
                    values.add(constant.toString());
                }
            }
            return schema;
        }
        if (clazz.isArray()) {
            ObjectNode schema = MAPPER.createObjectNode().put("type", "array");
            schema.set("items", schemaForType(clazz.getComponentType(), seen));
            return schema;
        }
        if (Collection.class.isAssignableFrom(clazz)) {
            ObjectNode schema = MAPPER.createObjectNode().put("type", "array");
            schema.set("items", fallbackSchema());
            return schema;
        }
        if (Map.class.isAssignableFrom(clazz)) {
            ObjectNode schema = MAPPER.createObjectNode().put("type", "object");
            schema.set("additionalProperties", fallbackSchema());
            return schema;
        }
        if (clazz.getName().startsWith("java.")) {
            return fallbackSchema();
        }

        return objectSchemaForClass(clazz, seen);
    }

    private static JsonNode objectSchemaForClass(Class<?> clazz, Set<String> seen) {
        String name = clazz.getName();
        if (!seen.add(name)) {
            return fallbackSchema();
        }

        ObjectNode schema = MAPPER.createObjectNode();
        schema.put("type", "object");
        ObjectNode properties = schema.putObject("properties");
        List<String> requiredNames = new ArrayList<>();

        if (clazz.isRecord()) {
            for (RecordComponent component : clazz.getRecordComponents()) {
                properties.set(component.getName(), schemaForType(component.getGenericType(), seen));
                requiredNames.add(component.getName());
            }
        } else {
            for (Method method : clazz.getMethods()) {
                if (method.getParameterCount() != 0 || method.getDeclaringClass() == Object.class) {
                    continue;
                }
                String propertyName = beanPropertyName(method);
                if (propertyName == null || properties.has(propertyName)) {
                    continue;
                }
                properties.set(propertyName, schemaForType(method.getGenericReturnType(), seen));
            }
        }

        if (!requiredNames.isEmpty()) {
            ArrayNode required = schema.putArray("required");
            requiredNames.forEach(required::add);
        }
        schema.put("additionalProperties", false);
        seen.remove(name);
        return schema;
    }

    private static String beanPropertyName(Method method) {
        String name = method.getName();
        if (name.startsWith("get") && name.length() > 3) {
            return Introspector.decapitalize(name.substring(3));
        }
        if (name.startsWith("is") && name.length() > 2
            && (boolean.class.equals(method.getReturnType()) || Boolean.class.equals(method.getReturnType()))) {
            return Introspector.decapitalize(name.substring(2));
        }
        return null;
    }

    static ObjectNode fallbackSchema() {
        ObjectNode schema = MAPPER.createObjectNode();
        schema.put("type", "object");
        schema.put("additionalProperties", true);
        return schema;
    }
}
