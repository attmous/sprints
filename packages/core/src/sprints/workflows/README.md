# Sprints Workflows

`sprints/workflows/` is the flat implementation shared by bundled workflow
templates.

Workflow intent lives in `WORKFLOW.md`. Python owns the mechanics: loading the
contract, typing front matter, dispatching actors, applying route or
orchestrator decisions, and writing state.

## Layout

```text
workflows/
|-- __init__.py              # public workflow exports
|-- __main__.py              # `python -m workflows --workflow-root <path> ...`
|-- entry_registry.py        # workflow object registry and CLI dispatch
|-- entry_runner.py          # CLI command router
|-- entry_inspection.py      # validate, show, status, and lanes commands
|-- entry_lanes.py           # lane facade used by workflow mechanics
|-- tick_orchestrator.py     # orchestrator-mode tick lifecycle
|-- tick_actor_driven.py     # actor-driven tick lifecycle
|-- tick_journal.py          # engine run/events for workflow.tick.*
|-- route_orchestrator.py    # orchestrator prompt + decision schema
|-- route_rules.py           # declarative actor-driven route selection
|-- route_effects.py         # execute selected actor-driven route
|-- lane_intake.py           # tracker intake, auto-activation, lane claiming
|-- lane_reconcile.py        # runtime, tracker, and pull request reconciliation
|-- lane_transitions.py      # lane decisions, transitions, release mechanics
|-- lane_teardown.py         # merge, tracker cleanup, and cleanup retry mechanics
|-- lane_completion.py       # actor-driven completion verification
|-- lane_state.py            # lane ledger state, config parsing, engine projections
|-- runtime_dispatch.py      # actor dispatch, background worker, heartbeats
|-- runtime_sessions.py      # actor dispatch journal, sessions, scheduler projections
|-- actor_runtime.py         # actor runtime construction
|-- actor_outputs.py         # actor output recording and contract handling
|-- action_handlers.py       # deterministic action execution
|-- state_io.py              # WorkflowState, state IO, audit, and state lock
|-- state_retries.py         # workflow adapter for engine-owned retry mechanics
|-- state_effects.py         # idempotency keys for external side effects
|-- state_projection.py      # engine-first lane projections
|-- state_status.py          # workflow and lane status payloads
|-- prompt_context.py        # compact state/facts for runtime prompts
|-- prompt_variables.py      # prompt variable builders
|-- surface_board.py         # board label mutation mechanics
|-- surface_board_state.py   # label-backed board state mapping
|-- surface_review_state.py  # review signal building
|-- surface_review_context.py # pull request review/comment collection
|-- surface_notifications.py # review feedback notifications
|-- surface_workpad.py       # compact Sprints workpad comment
|-- surface_operator.py      # operator retry, release, and complete commands
|-- surface_worktrees.py     # lane worktree helpers
|-- schema.yaml              # workflow config schema
`-- templates/               # bundled WORKFLOW.md policy templates
    |-- code.md
    |-- change-delivery.md
    |-- release.md
    `-- triage.md
```

## Contract Shape

`WORKFLOW.md` has:

- YAML front matter for runtime bindings, actors, stages, storage, and routing.
- `# Orchestrator Policy` for transition authority.
- `# Actor: <name>` sections for actor-specific policy and output shape.

In orchestrator mode, the orchestrator decides whether to run an actor, run an
action, advance, retry, complete, or raise operator attention.
`tick_orchestrator.py` validates and applies that decision.
`gates` and deterministic `actions` are legacy orchestrator-mode config only.

In actor-driven mode, route policy lives in the workflow front matter as
`routing.actor-driven.rules`. `route_rules.py` selects a route from that table,
and `route_effects.py` executes it.

The orchestrator does not receive raw workflow state. `prompt_context.py`
builds a compact prompt payload:

- active and decision-ready lanes keep the fields needed for validation and
  handoff
- terminal lanes are reduced to counts and recent summaries
- runtime sessions, dispatch journals, transition history, and side-effect
  details stay in lane state, audit logs, and engine history
- prompt size is measured before runtime dispatch and aggressively compacted
  before the Codex app-server input limit can be hit

## Tick Journal

Each runner tick is journaled in the engine:

```text
engine_runs(mode=tick)
  `-- engine_events(workflow.tick.*)
```

The journal starts before policy loading and ends after state save or failure
handling. It records the main mechanical checkpoints: policy loaded, state
loaded, reconciled, intake completed, readiness evaluated, orchestrator
started/completed or output override, decisions parsed, decisions applied, and
the terminal event. `/sprints status` exposes the latest tick run and recent
tick journal events.

## Retry Wakeups

`workflows/state_retries.py` is only the workflow adapter around engine retry
mechanics. It asks the engine to schedule or clear retry rows, then keeps
`lane.pending_retry` as actor/orchestrator context.

The daemon does not derive wake timing from `lane.pending_retry`. It reads
`EngineStore.retry_wakeup()`, which is built from `engine_retry_queue`, and
uses that to shorten the next sleep when a retry is due or nearly due.

## Actor Dispatch Journal

Actor dispatch is journaled before the runtime is launched:

```text
planned -> started -> running -> completed | failed | interrupted | blocked
```

`planned` is saved immediately after the runner decides to launch an actor.
`started` links the journal entry to the engine actor run and runtime session.
`running` records progress metadata such as thread, turn, heartbeat, and log
paths. Terminal states preserve the final runtime result.

The journal is lane-scoped and blocks duplicate dispatch for that lane. If a
tick dies after `planned` but before a runtime session starts, reconciliation
marks the dispatch `interrupted` after `recovery.running-stale-seconds` and
queues a retry to the same actor/stage when configured.
