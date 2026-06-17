package io.mcprpc.automesh;

import java.util.HashMap;
import java.util.Map;

public final class AutoMeshCli {
    private AutoMeshCli() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            printUsage();
            return;
        }

        String command = args[0];
        Map<String, String> options = parseOptions(args);
        AutoMesh mesh = AutoMesh.builder()
            .serviceName(required(options, "--service-name"))
            .registryUrl(options.getOrDefault("--registry-url", ""))
            .mcpTransport(options.getOrDefault("--transport", "stdio"))
            .endpoint(options.get("--endpoint"))
            .build();

        switch (command) {
            case "run" -> {
                publish(mesh, options);
                mesh.registerAll();
                mesh.serve();
            }
            case "publish-class" -> {
                publish(mesh, options);
                mesh.registerAll();
            }
            case "publish-package" -> {
                mesh.publishPackage(required(options, "--package"));
                mesh.registerAll();
            }
            case "list-tools" -> {
                if (options.containsKey("--package")) {
                    mesh.publishPackage(required(options, "--package"));
                } else {
                    publish(mesh, options);
                }
                for (String name : mesh.toolNames()) {
                    System.out.println(name);
                }
            }
            case "heartbeat" -> mesh.heartbeatOnce(options.getOrDefault("--health", "healthy"));
            default -> printUsage();
        }
    }

    private static void publish(AutoMesh mesh, Map<String, String> options) throws ReflectiveOperationException {
        String className = required(options, "--class");
        Class<?> clazz = Class.forName(className);
        if (hasPublicStaticMethods(clazz)) {
            mesh.publishClass(clazz);
        }
        if (!hasPublicStaticMethods(clazz)) {
            mesh.publishInstance(clazz.getDeclaredConstructor().newInstance());
            return;
        }
        if (hasPublicInstanceMethods(clazz)) {
            mesh.publishInstance(clazz.getDeclaredConstructor().newInstance());
        }
    }

    private static boolean hasPublicStaticMethods(Class<?> clazz) {
        return java.util.Arrays.stream(clazz.getMethods())
            .anyMatch(method -> method.getDeclaringClass() == clazz
                && java.lang.reflect.Modifier.isPublic(method.getModifiers())
                && java.lang.reflect.Modifier.isStatic(method.getModifiers()));
    }

    private static boolean hasPublicInstanceMethods(Class<?> clazz) {
        return java.util.Arrays.stream(clazz.getMethods())
            .anyMatch(method -> method.getDeclaringClass() == clazz
                && java.lang.reflect.Modifier.isPublic(method.getModifiers())
                && !java.lang.reflect.Modifier.isStatic(method.getModifiers()));
    }

    private static Map<String, String> parseOptions(String[] args) {
        Map<String, String> options = new HashMap<>();
        for (int index = 1; index < args.length; index++) {
            String key = args[index];
            if (!key.startsWith("--")) {
                continue;
            }
            String value = index + 1 < args.length ? args[index + 1] : "";
            if (value.startsWith("--")) {
                options.put(key, "true");
                continue;
            }
            options.put(key, value);
            index++;
        }
        return options;
    }

    private static String required(Map<String, String> options, String key) {
        String value = options.get(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing required option " + key);
        }
        return value;
    }

    private static void printUsage() {
        System.err.println("Usage:");
        System.err.println("  run --service-name <name> --class <fqcn> [--registry-url <url>] [--transport stdio|sse|streamable-http] [--endpoint <url>]");
        System.err.println("  publish-class --service-name <name> --class <fqcn> [--registry-url <url>] [--transport stdio|sse|streamable-http] [--endpoint <url>]");
        System.err.println("  publish-package --service-name <name> --package <pkg> [--registry-url <url>] [--transport stdio|sse|streamable-http] [--endpoint <url>]");
        System.err.println("  list-tools --service-name <name> (--class <fqcn> | --package <pkg>)");
        System.err.println("  heartbeat --service-name <name> [--registry-url <url>] [--health healthy]");
    }
}
