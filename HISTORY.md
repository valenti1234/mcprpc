# History

## 2026-06-16

- Added `mc-java-automesh`: Java AutoMesh implementation that discovers Java methods, generates JSON Schema, registers tools in `mr-registry`, and serves MCP tools.
- Implemented MCP serving over `stdio`, `sse`, and `streamable-http` in `mc-java-automesh`.
- Added `BillingApi` example + runner and improved example logging to make tool invocations visible.
- Fixed registry publishing noise by forcing Java `HttpClient` to use HTTP/1.1 (avoids `h2c` upgrade warnings with Uvicorn).
- Improved local dev defaults and docs to use `127.0.0.1` consistently (avoids `localhost` vs `127.0.0.1` mismatches in browser fetch + CORS).
- Updated `mr-router` default bind host and added default CORS origins for `mr-html`.
