# Sprints

Hermes Sprints is a Hermes plugin for durable agentic workflow execution.

Sprints writes a repo-owned `WORKFLOW.md`, dispatches actors through configured
runtimes, stores state, and exposes operator commands. Policy belongs in
`WORKFLOW.md`; Python owns mechanics.

## Quick Start

```bash
sudo apt install python3-yaml python3-jsonschema
hermes plugins install attmous/sprints --enable

cd /path/to/repo
hermes sprints bootstrap
$EDITOR WORKFLOW.md
hermes sprints codex-app-server up
hermes sprints validate
hermes sprints doctor
hermes
```

Inside Hermes:

```text
/sprints status
/sprints doctor
/sprints watch
/workflow agentic status
/workflow agentic validate
/workflow agentic tick
```

## What Sprints Owns

| Area | Meaning |
| --- | --- |
| Workflow contract | `WORKFLOW.md` front matter plus orchestrator/actor policy sections. |
| Runtime dispatch | Actor turns through Codex app-server, Hermes Agent, Claude, ACPX, or command-backed runtime profiles. |
| Durable state | SQLite runs, events, leases, retries, runtime sessions, and status projections. |
| Operator surface | `/sprints`, `/workflow agentic`, watch output, and runtime diagnostics. |
| Trackers | GitHub and Linear client boundaries. |

## Workflow Model

The public workflow implementation is `agentic`.

Each contract defines:

- orchestrator actor
- runtime profiles
- actors
- stages
- gates
- actions
- storage paths

Bundled policy templates live under `sprints/workflows/templates/`:

- `issue-runner.md`
- `change-delivery.md`
- `release.md`
- `triage.md`

They are templates for `workflow: agentic`, not separate Python workflow
packages.

## Package Layout

```text
sprints/
|-- cli/          # command surface
|-- engine/       # SQLite-backed state
|-- observe/      # read-only operator views
|-- runtimes/     # runtime adapters and turn dispatch
|-- trackers/     # GitHub and Linear trackers
`-- workflows/    # WORKFLOW.md loader and agentic runner
```

## Docs

| Doc | Purpose |
| --- | --- |
| [Installation](docs/operator/installation.md) | Install, bootstrap, validate, run. |
| [Architecture](docs/architecture.md) | Current package boundaries. |
| [Workflow Contract](docs/workflows/workflow-contract.md) | `WORKFLOW.md` structure. |
| [Runtimes](docs/concepts/runtimes.md) | Actor/runtime execution path. |
| [Engine](docs/concepts/engine.md) | Durable state model. |
| [Slash Commands](docs/operator/slash-commands.md) | Command reference. |
| [Security](docs/security.md) | Trust model and execution risk. |

## License

MIT. See [LICENSE](LICENSE).
