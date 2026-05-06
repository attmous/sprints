# Architecture

Sprints is a Hermes-Agent plugin that runs supervised coding workflows from a
repo-owned `WORKFLOW.md`.

The current bundled workflow is `code`.

## Table Of Contents

- [Mental Model](#mental-model)
- [Workflow Steps](#workflow-steps)
- [System Parts](#system-parts)
- [Tick Loop](#tick-loop)
- [Filesystem Topology](#filesystem-topology)
- [Durability](#durability)
- [Runtime And Daemon](#runtime-and-daemon)

## Mental Model

```text
GitHub issue -> lane ledger -> step tick -> coder runtime turn -> tracker label
                                      |                |
                                      |                `-> JSON handoff
                                      `-> engine state, retries, audit
```

A lane is one issue/PR/task with durable state. Python owns lane mechanics and
step transitions. The coder actor owns the work inside one lane worktree.

## Workflow Steps

```text
todo -> code -> review -> merge -> done
          ^        |
          |--------|
```

| Step | Owner | Meaning |
| --- | --- | --- |
| `todo` | Operator/tracker | Eligible issue waiting for intake. |
| `code` | Coder actor | Implement, fix review feedback, validate, push, open/update PR. |
| `review` | Runner | Idle polling for PR comments, reviews, checks, and human merge signal. |
| `merge` | Coder actor | Open and follow `.codex/skills/land/SKILL.md`. |
| `done` | Runner | Verify merged PR evidence and release the lane. |
| `blocked` | Operator | External unblock required. |

Required review feedback moves `review -> code`. Merge authority moves
`review -> merge`. Successful land moves `merge -> done`.

## System Parts

| Part | Owns | Does Not Own |
| --- | --- | --- |
| `engine/` | SQLite schema, leases, retries, runs, events, runtime sessions, work item projections. | Workflow policy. |
| `workflows/` | `WORKFLOW.md` loading, lane ledger, intake, step evaluation, runtime dispatch, prompt variables, status. | Tracker implementation internals. |
| `runtimes/` | Backend adapters for actor turns. | Lane transitions. |
| `trackers/` | GitHub/Linear tracker and GitHub code-host mechanics. | Retry policy or actor prompts. |
| `skills/` | Reusable actor mechanics such as pull, debug, commit, push, land. | Lane claims or concurrency. |
| `services/` | Codex app-server and daemon management. | Actor policy. |

## Tick Loop

One daemon tick does this:

1. Load `WORKFLOW.md` and typed config.
2. Load the lane ledger.
3. Reconcile active lanes with runtime sessions, tracker issues, PRs, and review signals.
4. Claim new `todo` lanes if capacity allows.
5. Route each active lane by step.
6. Dispatch coder for `code` or `merge` when allowed.
7. Persist state, engine projections, audit, and tick journal.

Ticks dispatch no supervisor actor. If all lanes are running, in review,
blocked, terminal, or waiting for a retry due time, the tick exits cleanly.

## Filesystem Topology

```text
repo root
|-- WORKFLOW.md
|-- .hermes/
|   `-- sprints/
|       `-- workflow-root  -> ~/.hermes/workflows/<owner>-<repo>-code
`-- .sprints/
    `-- workspace/
        `-- worktrees/
            `-- code/
                `-- <lane-id>/
```

```text
~/.hermes/workflows/<owner>-<repo>-code
|-- .sprints/
|   |-- code-state.json
|   |-- code-audit.jsonl
|   `-- sprints.sqlite3
`-- WORKFLOW.md
```

The workflow root is the durable operator/runtime home. The repo root owns the
human-editable contract. Lane work happens in worktrees.

## Durability

Sprints keeps two layers of state:

| Layer | Purpose |
| --- | --- |
| Lane ledger JSON | Hot workflow state and compact actor context. |
| Engine SQLite | Leases, retries, runs, events, runtime sessions, work item projection, side-effect history. |

Side effects such as label moves use idempotency keys. Actor dispatch is
journaled before runtime execution so interrupted turns can be detected and
retried or escalated.

## Runtime And Daemon

The daemon triggers ticks. The runtime executes actor turns.

For Codex app-server:

```text
sprints daemon -> workflow tick -> coder prompt -> codex-app-server
```

Other runtimes can execute through their CLI/runtime adapter and do not require
the Codex app-server.
