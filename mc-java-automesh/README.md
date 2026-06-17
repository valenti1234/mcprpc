# mc-java-automesh

`mc-java-automesh` is a Java 21 AutoMesh implementation for the `mcprpc` monorepo. It discovers Java methods, exposes them as MCP tools over stdio or HTTP transports, and publishes metadata to the `mr-registry` service.

## Features

- Java 21 library with Maven build
- Reflection-based discovery for instance or static methods
- `@Expose` and `@Ignore` annotations for metadata control
- JSON Schema generation from Java method signatures
- Registry `/register` and `/heartbeat` support via `HttpClient`
- Minimal MCP stdio server with `initialize`, `ping`, `tools/list`, and `tools/call`
- HTTP-compatible MCP serving for `sse` and `streamable-http`
- Built-in `system.health` and `system.heartbeat` tools

## Quickstart

```java
import io.mcprpc.automesh.AutoMesh;
import io.mcprpc.automesh.annotations.Expose;

public final class BillingService {
    @Expose(description = "Calculate VAT", tags = {"billing"})
    public double calculateVat(double amount, double rate) {
        return amount * rate;
    }
}

public final class Main {
    public static void main(String[] args) throws Exception {
        AutoMesh mesh = AutoMesh.builder()
            .serviceName("java-billing-worker")
            .registryUrl("http://127.0.0.1:7000")
            .mcpTransport("sse")
            .endpoint("http://127.0.0.1:7002/sse/")
            .build();

        mesh.publishInstance(new BillingService());
        mesh.registerAll();
        mesh.serve();
    }
}
```

## Discovery Rules

Included:

- Public methods declared on the published class
- Public static methods declared on the published class
- Public methods annotated with `@Expose`

Ignored automatically:

- Methods starting with `_`
- Synthetic and bridge methods
- Methods inherited from a superclass
- Methods annotated with `@Ignore`

Default tool names use `<lowerCamelClassName>.<methodName>`, for example `billingService.calculateVat`.

## Annotations

### `@Expose`

```java
@Expose(
    name = "billing.calculateVat",
    description = "Calculate VAT",
    tags = {"billing"},
    roles = {"billing", "admin"},
    inputMode = InputMode.POSITIONAL,
    parameters = {"amount", "rate"},
    costCpuWeight = 1
)
public double calculateVat(double amount, double rate) {
    return amount * rate;
}
```

### `@Ignore`

```java
@Ignore
public String internalHelper() {
    return "hidden";
}
```

## CLI

The Maven module ships with a simple CLI for classes that have a no-arg constructor.

```bash
cd mc-java-automesh
mvn -DskipTests compile exec:java -Dexec.args="run --service-name java-billing-worker --registry-url http://127.0.0.1:7000 --transport sse --endpoint http://127.0.0.1:7002/sse/ --class com.example.BillingService"
```

Supported commands:

- `run`: discover, register, then serve over `stdio`, `sse`, or `streamable-http`
- `publish-class`: discover and register without serving
- `publish-package`: scan a package, discover classes, and register them
- `list-tools`: print tool names and exit
- `heartbeat`: send a single heartbeat

## Example API

This module includes a small example API in [BillingApi.java](file:///home/valenti/mcprpc/mc-java-automesh/src/main/java/io/mcprpc/automesh/examples/BillingApi.java) with a runnable entrypoint in [BillingApiExampleMain.java](file:///home/valenti/mcprpc/mc-java-automesh/src/main/java/io/mcprpc/automesh/examples/BillingApiExampleMain.java).

Exposed example tools:

- `billing.createInvoice`
- `billing.calculateVat`
- `billing.listCurrencies`

Run the example directly:

```bash
cd mc-java-automesh
export MCP_TRANSPORT=sse
mvn -DskipTests compile exec:java -Dexec.mainClass=io.mcprpc.automesh.examples.BillingApiExampleMain
```

Or use the helper script:

```bash
cd mc-java-automesh
./run-example.sh
```

To publish to the registry, start `mr-registry` first and set:

```bash
export REGISTRY_URL=http://127.0.0.1:7000
```

The helper script defaults to:

- `MCP_TRANSPORT=sse`
- `AUTOMESH_ENDPOINT=http://127.0.0.1:7002/sse/`

If you want the alternate HTTP mode:

```bash
cd mc-java-automesh
MCP_TRANSPORT=streamable-http AUTOMESH_ENDPOINT=http://127.0.0.1:7002/mcp ./run-example.sh
```

Compatibility note:

- `sse` is the safest choice with the current `mr-router`
- `streamable-http` is exposed by the Java worker, but the current router still connects using an SSE-style client path for both HTTP transports

Run the same example through the CLI:

```bash
cd mc-java-automesh
mvn -DskipTests compile exec:java -Dexec.args="run --service-name java-billing-api --registry-url http://127.0.0.1:7000 --transport sse --endpoint http://127.0.0.1:7002/sse/ --class io.mcprpc.automesh.examples.BillingApi"
```

To see immediate output without starting the MCP stdio server, list the tools:

```bash
cd mc-java-automesh
mvn -DskipTests compile exec:java -Dexec.args="list-tools --service-name java-billing-api --class io.mcprpc.automesh.examples.BillingApi"
```

Once running, the worker will register the example tools with the registry and serve them over the selected MCP transport.

## End-to-End Demo (registry + router + mr-html)

The router currently invokes MCP tools over HTTP transports, so for a Java worker use `sse` (recommended) or `streamable-http`.

1. Start the registry:

```bash
cd ../mr-registry
./run.sh
```

2. Start the router:

```bash
cd ../mr-router
./run.sh
```

3. Start the Java worker (SSE):

```bash
cd ../mc-java-automesh
export REGISTRY_URL=http://127.0.0.1:7000
export MCP_TRANSPORT=sse
./run-example.sh
```

4. Start the pure frontend UI:

```bash
cd ../mr-html
./run.sh
```

Open `mr-html` at http://127.0.0.1:8386/ and set:

- Registry URL: `http://127.0.0.1:7000`
- Router URL: `http://127.0.0.1:7010`

## Troubleshooting

- If the registry logs `Invalid HTTP request received` with `Upgrade: h2c`, force HTTP/1.1 for clients. `mc-java-automesh` uses HTTP/1.1 for registry calls by default.
- If tool calls time out and you are using `sse`, confirm the Java worker is running and you see `event=http_request ... GET ... /sse/` and `event=http_request ... POST ... /messages` on stderr.

## Testing

```bash
cd mc-java-automesh
mvn test
```
