# Sprints Slash Command Catalog

Quick reference for the two Hermes slash commands registered by the plugin:
`/sprints` for the operator control surface and `/workflow` for the active
workflow CLI.

## `/sprints`

### Inspection

| Command | What it does |
|---|---|
| `/sprints status` | Show workflow state, workflow root, and important paths |
| `/sprints doctor` | Run health checks across config, state, and runtime dependencies |
| `/sprints validate` | Validate the repo-owned `WORKFLOW.md` contract |
| `/sprints runs` | Inspect durable engine run history |
| `/sprints events` | Inspect the durable engine event ledger |
| `/sprints events stats` | Show event counts and retention posture |
| `/sprints events prune` | Apply explicit or contract-defined event retention |
| `/sprints runtime-matrix` | Show role-to-runtime bindings |

### Workflow Setup

| Command | What it does |
|---|---|
| `/sprints bootstrap` | Infer repo root, create a workflow root, write the repo-owned contract, and persist the repo pointer |
| `/sprints scaffold-workflow` | Create a workflow root and repo-owned contract from explicit paths |
| `/sprints configure-runtime` | Bind an actor role to a runtime preset |

### Codex App-Server

| Command | What it does |
|---|---|
| `/sprints codex-app-server install` | Write the shared Codex app-server user unit |
| `/sprints codex-app-server up` | Install, enable, and start the shared Codex app-server |
| `/sprints codex-app-server status` | Show unit status plus readiness |
| `/sprints codex-app-server doctor` | Diagnose managed/external listener health, auth posture, and Codex thread mappings |
| `/sprints codex-app-server restart` | Restart the Codex app-server unit |
| `/sprints codex-app-server logs` | Show recent Codex app-server journal entries |
| `/sprints codex-app-server down` | Stop and disable Codex app-server |

### Observability

| Command | What it does |
|---|---|
| `/sprints watch` | Live operator TUI |
| `/sprints watch --once` | Render one frame and exit |

## `/workflow`

| Command | What it does |
|---|---|
| `/workflow` | List installed workflows |
| `/workflow <name>` | Show that workflow's help |
| `/workflow <name> <cmd> [args]` | Route to that workflow's CLI |

### `agentic`

| Command | What it does |
|---|---|
| `/workflow agentic status` | Show workflow state |
| `/workflow agentic validate` | Validate the active `WORKFLOW.md` contract |
| `/workflow agentic tick` | Run one orchestrator tick |

## Day To Day

1. `/sprints watch`
2. `/sprints doctor`
3. `/sprints validate`
4. `/workflow agentic status`
5. `/workflow agentic tick`

Most commands accept `--workflow-root <path>`. Inspection commands commonly
accept `--format json` or `--json`.
