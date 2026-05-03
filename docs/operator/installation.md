# Installation

Supported path:

```bash
sudo apt install python3-yaml python3-jsonschema
hermes plugins install attmous/sprints --enable
```

## Bootstrap

Run from the target repo:

```bash
cd /path/to/repo
hermes sprints bootstrap
$EDITOR WORKFLOW.md
hermes sprints codex-app-server up
hermes sprints validate
hermes sprints doctor
hermes sprints daemon up
```

`bootstrap` creates a workflow root and writes a repo-owned `WORKFLOW.md`
contract.

Default workflow root:

```text
~/.hermes/workflows/<owner>-<repo>-change-delivery/
```

The repo pointer is written to:

```text
./.hermes/sprints/workflow-root
```

## Runtime

Bundled templates default actors to `codex-app-server`:

```yaml
runtimes:
  codex:
    kind: codex-app-server
    mode: external
    endpoint: ws://127.0.0.1:4500
```

Start the shared listener:

```bash
hermes sprints codex-app-server up
```

Or bind roles to another runtime:

```bash
hermes sprints configure-runtime --runtime hermes-final --role implementer
hermes sprints configure-runtime --runtime codex-app-server --role orchestrator
```

## Validate

```bash
hermes sprints validate
hermes sprints doctor
hermes sprints runtime-matrix
```

Use `runtime-matrix --execute` only when the configured runtimes are available.
It dispatches a minimal runtime turn.

## Daemon

Start the workflow daemon after the runtime listener and validation pass:

```bash
hermes sprints daemon up
hermes sprints daemon status
```

The daemon runs one workflow tick immediately, then keeps polling. Defaults:

```text
active lanes: 15s
idle workflow: 60s
retry wake cap: 30s
```

## Operate

Inside Hermes:

```text
/sprints status
/sprints doctor
/sprints watch
/sprints daemon status
/workflow change-delivery status
/workflow change-delivery validate
/workflow change-delivery tick
```

## Local Development Install

```bash
git clone https://github.com/attmous/sprints.git
cd sprints
./scripts/install.sh
hermes plugins enable sprints
```
