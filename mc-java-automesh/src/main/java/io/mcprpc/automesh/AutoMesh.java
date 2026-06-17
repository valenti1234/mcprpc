package io.mcprpc.automesh;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.mcprpc.automesh.annotations.Ignore;
import io.mcprpc.automesh.annotations.InputMode;
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.net.JarURLConnection;
import java.net.URL;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class AutoMesh {
    static final String VERSION = "0.1.0";
    private static final ObjectMapper MAPPER = SchemaUtils.MAPPER;

    private final String serviceName;
    private final String registryUrl;
    private final String runtime;
    private final String mcpTransport;
    private final String endpoint;
    private final String meshId;
    private final int heartbeatIntervalSeconds;
    private final Instant startedAt;
    private final RegistryClient registryClient;
    private final Map<String, ToolRegistration> tools = new LinkedHashMap<>();
    private ScheduledExecutorService heartbeatExecutor;
    private HttpMcpServer httpMcpServer;

    private AutoMesh(Builder builder) {
        this.serviceName = requireText(builder.serviceName, "serviceName");
        this.registryUrl = builder.registryUrl == null ? "" : builder.registryUrl;
        this.runtime = builder.runtime == null || builder.runtime.isBlank() ? "java" : builder.runtime;
        this.mcpTransport = builder.mcpTransport == null || builder.mcpTransport.isBlank() ? "stdio" : builder.mcpTransport;
        this.endpoint = resolveEndpoint(builder.endpoint, this.mcpTransport);
        this.meshId = builder.meshId == null || builder.meshId.isBlank()
            ? System.getenv().getOrDefault("MCPRPC_MESH_ID", UUID.randomUUID().toString().replace("-", ""))
            : builder.meshId;
        this.heartbeatIntervalSeconds = builder.heartbeatIntervalSeconds > 0
            ? builder.heartbeatIntervalSeconds
            : parseHeartbeatIntervalSeconds();
        this.startedAt = Instant.now();
        this.registryClient = new RegistryClient(this.registryUrl);
        registerBuiltinTools();
    }

    public static Builder builder() {
        return new Builder();
    }

    public String serviceName() {
        return serviceName;
    }

    public int toolCount() {
        return tools.size();
    }

    public List<String> toolNames() {
        return List.copyOf(tools.keySet());
    }

    Map<String, ToolRegistration> tools() {
        return tools;
    }

    public AutoMesh publishInstance(Object instance) {
        Objects.requireNonNull(instance, "instance");
        for (Method method : instance.getClass().getMethods()) {
            if (isDiscoverableMethod(method, instance.getClass(), false)) {
                registerMethod(method, instance);
            }
        }
        return this;
    }

    public AutoMesh publishClass(Class<?> clazz) {
        Objects.requireNonNull(clazz, "clazz");
        for (Method method : clazz.getMethods()) {
            if (isDiscoverableMethod(method, clazz, true)) {
                registerMethod(method, null);
            }
        }
        return this;
    }

    public AutoMesh publishPackage(String packageName) {
        for (Class<?> clazz : discoverClasses(packageName)) {
            if (hasDiscoverableMethods(clazz, true)) {
                publishClass(clazz);
            }
            if (hasNoArgsConstructor(clazz) && hasDiscoverableMethods(clazz, false)) {
                publishInstance(instantiate(clazz));
            }
        }
        return this;
    }

    public void registerAll() throws IOException, InterruptedException {
        if (registryUrl.isBlank()) {
            System.err.println("event=register_all skipped=true reason=registry_url_empty tools=" + tools.size());
            return;
        }
        for (ToolRegistration registration : tools.values()) {
            try {
                registryClient.publish(registrationPayload(registration));
            } catch (IOException | InterruptedException exception) {
                System.err.println("event=registry_publish ok=false name=" + registration.metadata().name() + " error=" + exception);
            }
        }
    }

    public void heartbeatOnce(String health) throws IOException, InterruptedException {
        registryClient.heartbeat(
            registryClient.buildHeartbeatPayload(
                serviceName,
                meshId,
                runtime,
                health,
                heartbeatIntervalSeconds,
                new ArrayList<>(tools.keySet()),
                tools.values().stream().map(this::registrationPayload).toList()
            )
        );
    }

    public void startHeartbeat() {
        if (registryUrl.isBlank() || heartbeatIntervalSeconds <= 0 || heartbeatExecutor != null) {
            return;
        }
        heartbeatExecutor = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread thread = new Thread(r, "mc-java-automesh-heartbeat");
            thread.setDaemon(true);
            return thread;
        });
        heartbeatExecutor.scheduleAtFixedRate(() -> {
            try {
                heartbeatOnce("healthy");
            } catch (Exception ignored) {
            }
        }, 0, heartbeatIntervalSeconds, TimeUnit.SECONDS);
    }

    public void stopHeartbeat() {
        if (heartbeatExecutor == null) {
            return;
        }
        heartbeatExecutor.shutdownNow();
        heartbeatExecutor = null;
    }

    public void serve() throws IOException {
        if ("stdio".equals(mcpTransport)) {
            System.err.println("event=serve_start service_name=" + serviceName + " transport=stdio registry_enabled=" + (!registryUrl.isBlank()) + " tools=" + tools.size());
            for (String tool : tools.keySet()) {
                System.err.println("tool=" + tool);
            }
            System.err.println("note=mcp_stdio_waiting detail=waiting_for_client_on_stdin_stdout");
            startHeartbeat();
            try {
                new McpStdioServer(this, System.in, System.out).serve();
            } finally {
                stopHeartbeat();
            }
            return;
        }

        if ("sse".equals(mcpTransport) || "streamable-http".equals(mcpTransport)) {
            String bindHost = System.getenv().getOrDefault("MCPRPC_BIND_HOST", "127.0.0.1");
            System.err.println("event=serve_start service_name=" + serviceName + " transport=" + mcpTransport + " registry_enabled=" + (!registryUrl.isBlank()) + " tools=" + tools.size());
            for (String tool : tools.keySet()) {
                System.err.println("tool=" + tool);
            }
            startHeartbeat();
            httpMcpServer = new HttpMcpServer(this, bindHost, endpoint, mcpTransport);
            httpMcpServer.serve();
            Runtime.getRuntime().addShutdownHook(new Thread(this::stopHttpServer));
            try {
                synchronized (this) {
                    while (true) {
                        try {
                            this.wait();
                        } catch (InterruptedException exception) {
                            Thread.currentThread().interrupt();
                            break;
                        }
                    }
                }
            } finally {
                stopHttpServer();
                stopHeartbeat();
            }
            return;
        }

        throw new IllegalStateException("Unsupported transport: " + mcpTransport);
    }

    private void stopHttpServer() {
        if (httpMcpServer != null) {
            httpMcpServer.stop();
            httpMcpServer = null;
        }
    }

    public Object invoke(String toolName, JsonNode arguments) throws Exception {
        ToolRegistration registration = tools.get(toolName);
        if (registration == null) {
            throw new IllegalArgumentException("Unknown tool: " + toolName);
        }
        ToolMetadata metadata = registration.metadata();
        Method method = metadata.method();
        Object[] args = toArguments(method, metadata, arguments == null || arguments.isNull() ? MAPPER.createObjectNode() : arguments);
        try {
            Object result = method.invoke(registration.target(), args);
            if (result instanceof CompletionStage<?> stage) {
                return stage.toCompletableFuture().get(30, TimeUnit.SECONDS);
            }
            return result;
        } catch (InvocationTargetException exception) {
            Throwable cause = exception.getCause();
            if (cause instanceof Exception e) {
                throw e;
            }
            throw exception;
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("Failed to invoke tool " + toolName, exception);
        } catch (java.util.concurrent.TimeoutException exception) {
            throw new IllegalStateException("Timed out waiting for tool result", exception);
        }
    }

    public String stringifyResult(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof CharSequence || value instanceof Number || value instanceof Boolean) {
            return value.toString();
        }
        try {
            return MAPPER.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            return value.toString();
        }
    }

    private void registerBuiltinTools() {
        registerSynthetic("system.health", "Service health status", builtInMethod("systemHealth"), this, List.of("system", "health"));
        registerSynthetic("system.heartbeat", "Send heartbeat to registry", builtInMethod("systemHeartbeat", String.class), this, List.of("system", "heartbeat"));
    }

    public Map<String, Object> systemHealth() {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("status", "ok");
        payload.put("service", serviceName);
        payload.put("runtime", runtime);
        payload.put("version", VERSION);
        payload.put("uptime_ms", Duration.between(startedAt, Instant.now()).toMillis());
        payload.put("tools", tools.size());
        return payload;
    }

    public Map<String, Object> systemHeartbeat(String health) throws IOException, InterruptedException {
        heartbeatOnce(health == null || health.isBlank() ? "healthy" : health);
        return Map.of("ok", true);
    }

    private void registerSynthetic(String name, String description, Method method, Object target, List<String> tags) {
        ToolMetadata metadata = new ToolMetadata(
            name,
            description,
            SchemaUtils.inputSchema(method),
            SchemaUtils.outputSchema(method),
            Map.of(),
            Map.of(),
            tags,
            VERSION,
            InputMode.OBJECT,
            Arrays.stream(method.getParameters()).map(p -> p.getName()).toList(),
            method
        );
        tools.put(name, new ToolRegistration(metadata, target));
    }

    private Method builtInMethod(String name, Class<?>... parameterTypes) {
        try {
            return AutoMesh.class.getMethod(name, parameterTypes);
        } catch (NoSuchMethodException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private void registerMethod(Method method, Object target) {
        ToolMetadata metadata = MetadataExtractor.extract(method);
        tools.putIfAbsent(metadata.name(), new ToolRegistration(metadata, target));
    }

    private Map<String, Object> registrationPayload(ToolRegistration registration) {
        return registryClient.buildPublishPayload(serviceName, meshId, runtime, mcpTransport, endpoint, registration.metadata());
    }

    private Object[] toArguments(Method method, ToolMetadata metadata, JsonNode arguments) {
        JsonNode safeArguments = arguments.isObject() ? arguments : MAPPER.createObjectNode();
        List<String> parameterOrder = metadata.inputMode() == InputMode.POSITIONAL && !metadata.parameters().isEmpty()
            ? metadata.parameters()
            : Arrays.stream(method.getParameters()).map(p -> p.getName()).toList();
        if (parameterOrder.size() < method.getParameterCount()) {
            throw new IllegalStateException("Parameter metadata does not cover all arguments for " + metadata.name());
        }
        Object[] values = new Object[method.getParameterCount()];
        for (int index = 0; index < method.getParameterCount(); index++) {
            String argumentName = parameterOrder.get(index);
            JsonNode node = safeArguments.get(argumentName);
            values[index] = node == null || node.isNull()
                ? nullValue(method.getParameterTypes()[index])
                : MAPPER.convertValue(node, MAPPER.constructType(method.getGenericParameterTypes()[index]));
        }
        return values;
    }

    private Object nullValue(Class<?> type) {
        if (!type.isPrimitive()) {
            return null;
        }
        if (boolean.class.equals(type)) {
            return false;
        }
        if (char.class.equals(type)) {
            return (char) 0;
        }
        return 0;
    }

    private static boolean isDiscoverableMethod(Method method, Class<?> owner, boolean staticOnly) {
        if (!Modifier.isPublic(method.getModifiers())) {
            return false;
        }
        if (method.isSynthetic() || method.isBridge()) {
            return false;
        }
        if (method.getDeclaringClass() != owner || method.getDeclaringClass() == Object.class) {
            return false;
        }
        if (method.getName().startsWith("_")) {
            return false;
        }
        if (method.isAnnotationPresent(Ignore.class)) {
            return false;
        }
        return !staticOnly || Modifier.isStatic(method.getModifiers());
    }

    private static boolean hasDiscoverableMethods(Class<?> clazz, boolean staticOnly) {
        return Arrays.stream(clazz.getMethods()).anyMatch(method -> isDiscoverableMethod(method, clazz, staticOnly));
    }

    private static boolean hasNoArgsConstructor(Class<?> clazz) {
        try {
            Constructor<?> constructor = clazz.getDeclaredConstructor();
            return Modifier.isPublic(constructor.getModifiers());
        } catch (NoSuchMethodException exception) {
            return false;
        }
    }

    private static Object instantiate(Class<?> clazz) {
        try {
            return clazz.getDeclaredConstructor().newInstance();
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("Failed to instantiate " + clazz.getName(), exception);
        }
    }

    private static List<Class<?>> discoverClasses(String packageName) {
        try {
            String path = packageName.replace('.', '/');
            ClassLoader classLoader = Thread.currentThread().getContextClassLoader();
            Enumeration<URL> resources = classLoader.getResources(path);
            List<Class<?>> classes = new ArrayList<>();
            while (resources.hasMoreElements()) {
                URL resource = resources.nextElement();
                if ("file".equals(resource.getProtocol())) {
                    Path directory = Path.of(URLDecoder.decode(resource.getPath(), StandardCharsets.UTF_8));
                    if (Files.exists(directory)) {
                        try (var stream = Files.walk(directory)) {
                            stream.filter(file -> file.toString().endsWith(".class"))
                                .filter(file -> !file.getFileName().toString().contains("$"))
                                .forEach(file -> classes.add(loadClass(packageName, directory, file)));
                        }
                    }
                } else if ("jar".equals(resource.getProtocol())) {
                    classes.addAll(discoverJarClasses(resource, packageName, path));
                }
            }
            return classes;
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to scan package " + packageName, exception);
        }
    }

    private static Class<?> loadClass(String packageName, Path root, Path file) {
        String relative = root.relativize(file).toString().replace('/', '.').replace('\\', '.');
        String className = packageName + "." + relative.substring(0, relative.length() - ".class".length());
        try {
            return Class.forName(className);
        } catch (ClassNotFoundException exception) {
            throw new IllegalStateException("Failed to load class " + className, exception);
        }
    }

    private static List<Class<?>> discoverJarClasses(URL resource, String packageName, String path) {
        List<Class<?>> classes = new ArrayList<>();
        try {
            JarURLConnection connection = (JarURLConnection) resource.openConnection();
            try (JarFile jar = connection.getJarFile()) {
                Enumeration<JarEntry> entries = jar.entries();
                while (entries.hasMoreElements()) {
                    JarEntry entry = entries.nextElement();
                    String name = entry.getName();
                    if (!name.startsWith(path) || !name.endsWith(".class") || name.contains("$")) {
                        continue;
                    }
                    String className = name.substring(0, name.length() - ".class".length()).replace('/', '.');
                    classes.add(Class.forName(className));
                }
            }
        } catch (Exception exception) {
            throw new IllegalStateException("Failed to scan jar for package " + packageName, exception);
        }
        return classes;
    }

    private static int parseHeartbeatIntervalSeconds() {
        String raw = System.getenv("MCPRPC_HEARTBEAT_INTERVAL_S");
        if (raw == null || raw.isBlank()) {
            return 3;
        }
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException exception) {
            return 3;
        }
    }

    private static String resolveEndpoint(String configuredEndpoint, String transport) {
        if (configuredEndpoint != null && !configuredEndpoint.isBlank()) {
            return configuredEndpoint;
        }
        if ("sse".equals(transport)) {
            return System.getenv().getOrDefault("MCPRPC_SSE_URL", "http://localhost:7002/sse/");
        }
        if ("streamable-http".equals(transport)) {
            return System.getenv().getOrDefault("MCPRPC_STREAMABLE_HTTP_URL", "http://localhost:7002/mcp");
        }
        String command = System.getProperty("sun.java.command", "").trim();
        return command.isBlank() ? "java" : "java " + command;
    }

    private static String requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + " must not be blank");
        }
        return value;
    }

    public static final class Builder {
        private String serviceName;
        private String registryUrl = "";
        private String runtime = "java";
        private String mcpTransport = "stdio";
        private String endpoint;
        private String meshId;
        private int heartbeatIntervalSeconds;

        public Builder serviceName(String serviceName) {
            this.serviceName = serviceName;
            return this;
        }

        public Builder registryUrl(String registryUrl) {
            this.registryUrl = registryUrl;
            return this;
        }

        public Builder runtime(String runtime) {
            this.runtime = runtime;
            return this;
        }

        public Builder mcpTransport(String mcpTransport) {
            this.mcpTransport = mcpTransport;
            return this;
        }

        public Builder endpoint(String endpoint) {
            this.endpoint = endpoint;
            return this;
        }

        public Builder meshId(String meshId) {
            this.meshId = meshId;
            return this;
        }

        public Builder heartbeatIntervalSeconds(int heartbeatIntervalSeconds) {
            this.heartbeatIntervalSeconds = heartbeatIntervalSeconds;
            return this;
        }

        public AutoMesh build() {
            return new AutoMesh(this);
        }
    }
}
