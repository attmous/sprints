# Engine

`engine/` owns durable workflow state.

It does not decide workflow policy. `WORKFLOW.md` and the orchestrator decide what
should happen. The engine stores state, leases, runs, events, retries, runtime
sessions, and exposes a workflow-scoped API for that state.

## Layout

| File | Owns |
| --- | --- |
| `db.py` | SQLite connection, schema, table checks |
| `store.py` | `EngineStore`, the workflow-scoped public API |
| `state.py` | SQL reads and writes for scheduler state, runs, and events |
| `scheduler.py` | In-memory scheduler snapshot shape |
| `lifecycle.py` | Pure transitions for running and retry entries |
| `leases.py` | SQLite-backed leases |
| `retention.py` | Event retention config normalization |
| `reports.py` | CLI report builders for runs and events |
| `work.py` | Work/result dataclasses and tracker adapters |

## State

SQLite is the source of truth.

Default DB path comes from `workflows.paths.runtime_paths()`:

```text
<workflow_root>/runtime/state/sprints/sprints.db
```

## Rules

Workflow code should use `EngineStore`.

Only `state.py` should contain raw SQL for engine state operations. Only `db.py`
should create schema.

Durable events live in `engine_events`. Run timelines come from `engine_events`,
not JSONL audit files.

The engine stores neutral work IDs. Trackers may call them issues, tickets, PRs,
or tasks, but the engine should stay tracker-neutral.
