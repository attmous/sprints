# Codex App-Server

Use this when actors run through `kind: codex-app-server`.

## Managed Listener

```bash
hermes sprints codex-app-server up
hermes sprints codex-app-server status
hermes sprints codex-app-server doctor
```

Default endpoint:

```text
ws://127.0.0.1:4500
```

Logs:

```bash
hermes sprints codex-app-server logs --lines 100
```

Stop:

```bash
hermes sprints codex-app-server down
```

## Workflow Config

```yaml
runtimes:
  codex:
    kind: codex-app-server
    mode: external
    endpoint: ws://127.0.0.1:4500
    ephemeral: false
    keep_alive: true
```

`mode: external` means Sprints connects to an existing listener. `keep_alive:
true` keeps the WebSocket connection open for reuse.

## Auth

Loopback listeners usually do not need WebSocket auth. Non-loopback listeners
should use a token:

```bash
hermes sprints codex-app-server up \
  --ws-token-file /absolute/path/to/codex-app-server.token
```

Then reference the token in the runtime profile:

```yaml
runtimes:
  codex:
    kind: codex-app-server
    mode: external
    endpoint: ws://127.0.0.1:4500
    ws_token_file: /absolute/path/to/codex-app-server.token
```
