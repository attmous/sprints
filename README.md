# Sprints

<p align="center">
  <img src="packages/web/src/sprints_web/assets/site-assets/sprints-readme-banner.png" alt="Hermes Sprints banner">
</p>

Sprints is a Hermes-Agent plugin for durable supervised workflow execution.

Sprints writes a repo-owned `WORKFLOW.md`, dispatches actors through configured
runtimes, stores state, and exposes operator commands. Policy belongs in
`WORKFLOW.md`; Python owns mechanics.

## Maintainer Note

Sprints started at the beginning of April 2026 as my attempt to learn, in public
and through working code, what harness engineering and agent orchestration
really mean.

My background is in Agile software delivery, where teams move work through
issues, implementation, review, feedback, and completion. With Sprints, I am
trying to recreate that delivery loop around AI agents and humans in the loop.

On April 27, 2026, OpenAI published
[**Symphony**](https://openai.com/index/open-source-codex-orchestration-symphony/),
an open-source spec for Codex orchestration. That playbook helped me cut through
parts of my own implementation, reduce code size, and close many design gaps.

## Quick Start

Prerequisites:

- Hermes-Agent installed
- Git and tracker credentials available to the runtime
- Linux with `systemd --user` for `hermes sprints daemon up`

```bash
hermes plugins install attmous/sprints --enable

cd /path/to/repo
hermes sprints init
hermes sprints codex-app-server up
hermes sprints validate
hermes sprints doctor
hermes sprints doctor --fix
hermes sprints daemon up
hermes
```

Inside Hermes:

```text
/sprints status
/sprints doctor
/sprints doctor --fix
/sprints watch
/sprints daemon status
/workflow code status
/workflow code validate
/workflow code tick
```

To run the first lane, add the `todo` label to one eligible issue. The daemon
will pick it up on the next tick.

## Mental Model

Sprints is a multi-lane workflow runner.

```text
tracker issue -> lane ledger -> step tick -> actor runtime turn -> next step
                                                    |                 |
                                                    `-> retry         `-> operator_attention
```

A lane is one issue, pull request, or task with durable state. Python observes
eligible lanes and moves them through fixed workflow steps. Actors work on one
lane at a time through a configured runtime.

The engine stores mechanics: SQLite state, leases, retries, runtime sessions,
events, and projections. The workflow owns policy: step labels, actor rules,
tracker criteria, and output contracts.

## Default Workflow

The default workflow template is `code`.

```text
todo -> code -> review -> merge -> done
          ^        |
          |--------|
```

By default, only open issues with label `todo` are eligible. Intake removes
`todo`, adds `code`, and claims the lane. The coder implements, validates,
pushes, and opens or updates the PR. `review` is idle polling. Required changes
move the lane back to `code`; merge authority moves it to `merge`; successful
land moves it to `done`.

Default concurrency is one active lane:

```yaml
execution:
  actor-dispatch: auto

concurrency:
  max-lanes: 1
  per-lane-lock: true
```

With `actor-dispatch: auto`, Sprints keeps the single-lane default inline. If
you raise `max-lanes`, actor turns are dispatched as background workers so the
daemon can keep ticking and supervise other lanes. Ticks that only see running
lanes, review lanes, blocked lanes, or retries that are not due yet return
without dispatching new actor work.

Lane states are internal orchestration state, not tracker status:

| State | Meaning |
| --- | --- |
| `claimed` | The lane is reserved and must not be duplicated. |
| `running` | An actor is working on the lane. |
| `waiting` | The lane is held until the next real-world signal or retry. |
| `retry_queued` | Retry is scheduled and not ready or not yet dispatched. |
| `operator_attention` | The operator must unblock the lane. |
| `complete` | The workflow finished successfully. |
| `released` | The claim was removed because the lane is terminal or no longer eligible. |

## Runtime And Daemon

Two services are involved:

| Service | Job |
| --- | --- |
| `codex-app-server` | Runtime listener that executes actor turns. |
| `sprints daemon` | Workflow loop that triggers ticks, reconciles lanes, and dispatches actors. |

If the daemon is not running, the workflow only advances when an operator runs a
manual tick.

## What Sprints Owns

| Area | Meaning |
| --- | --- |
| Workflow contract | `WORKFLOW.md` front matter plus actor policy sections. |
| Runtime dispatch | Actor turns through Codex app-server, Hermes Agent, Claude, ACPX, or command-backed runtime profiles. |
| Durable state | SQLite runs, events, leases, retries, runtime sessions, and status projections. |
| Operator surface | `/sprints`, `/workflow code`, daemon control, watch output, and runtime diagnostics. |
| Trackers | Issue discovery and issue status/label updates. |
| Code hosts | Branch and pull request mechanics. GitHub currently provides both tracker and code-host boundaries. |
| Skills | Reusable actor mechanics such as `pull`, `debug`, `commit`, and `push`. |

## Workflow Model

Each contract defines:

- tracker and code-host bindings
- intake labels
- workspace root
- runtime profile
- concurrency
- storage paths
- actor policy

Bundled policy templates live under `packages/core/src/sprints/workflows/templates/`:

- `code.md`

The `code` workflow uses one coder actor and fixed steps:
`todo -> code -> review -> merge -> done`.

## First-Run Setup

Use `init` for the guided path:

```bash
cd /path/to/repo
hermes sprints init
```

It asks for the target repo, tracker, runtime, optional model override, labels,
and concurrency. It writes a valid repo-owned `WORKFLOW.md`, creates the
workflow root, records the repo pointer, validates the contract, and prints the
next commands. `bootstrap` and `scaffold-workflow` remain available for scripts
and advanced operators that already know the contract shape.

## Package Layout

```text
packages/
|-- core/              # engine, workflows, runtimes, trackers, services, app API
|-- cli/               # standalone `sprints` command
|-- tui/               # terminal UI package
|-- web/               # web UI package and static site assets
|-- mob/               # mobile adapter package
`-- plugins/
    |-- hermes/        # Hermes plugin adapter
    `-- openclaw/      # OpenClaw plugin adapter
```

## Docs

| Doc | Purpose |
| --- | --- |
| [Installation](docs/operator/installation.md) | Install, bootstrap, validate, run. |
| [Architecture](docs/architecture.md) | Current package boundaries. |
| [Workflow Contract](docs/workflows/workflow-contract.md) | `WORKFLOW.md` structure. |
| [Workflow Daemon](docs/operator/workflow-daemon.md) | Tick loop and service control. |
| [Codex App Server](docs/operator/codex-app-server.md) | Default runtime listener. |
| [Runtimes](docs/concepts/runtimes.md) | Actor/runtime execution path. |
| [Engine](docs/concepts/engine.md) | Durable state model. |
| [Skills](packages/core/src/sprints/skills/README.md) | Actor skill packages. |
| [Slash Commands](docs/operator/slash-commands.md) | Command reference. |
| [Security](docs/security.md) | Trust model and execution risk. |

## Development

This repo is managed with `uv`:

```bash
uv sync --locked --dev
uv run python -m compileall packages __init__.py
uv run ruff check packages __init__.py
```

## License

MIT. See [LICENSE](LICENSE).
