# Sprints Workflows

`sprints/workflows/` runs the bundled `code` workflow.

The workflow contract defines policy in `WORKFLOW.md`. Python owns mechanics:
intake, leases, lane state, worktrees, runtime dispatch, retries, review signal
collection, step transitions, status, and audit.

The active mental model is step-based:

```text
todo -> code -> review -> merge -> done
          ^        |
          |--------|
```

`review` is an idle polling step. If PR feedback requires changes, Python moves
the lane back to `code`. If merge authority appears, the label moves to `merge`
and the coder runs the land skill. `done` is terminal and releases the lane.

## Layout

```text
workflows/
|-- entry_registry.py      # supported workflow registry
|-- entry_runner.py        # validate/show/status/lanes/retry/release/tick commands
|-- entry_inspection.py    # read-only CLI commands
|-- entry_lanes.py         # facade for lane/runtime helpers
|-- step_runner.py         # one tick for the step workflow
|-- step_routes.py         # deterministic route for one lane step
|-- step_labels.py         # canonical labels and label mutation
|-- lane_intake.py         # tracker intake and lane claiming
|-- lane_reconcile.py      # runtime, tracker, PR, and review reconciliation
|-- lane_state.py          # lane ledger state and engine projections
|-- lane_transitions.py    # lane status, actor capacity, release mechanics
|-- review_signals.py      # compact PR reviews/comments/check signals
|-- runtime_dispatch.py    # actor dispatch, background worker, heartbeats
|-- runtime_sessions.py    # dispatch journal and runtime session projection
|-- actor_prompts.py       # actor prompt rendering
|-- actor_runtime.py       # runtime adapter construction
|-- actor_outputs.py       # actor output contract handling
|-- prompt_context.py      # compact lane/state facts
|-- prompt_variables.py    # actor prompt variables
|-- state_io.py            # WorkflowState, file IO, audit, lock
|-- state_retries.py       # workflow adapter for engine retries
|-- state_effects.py       # idempotency records for side effects
|-- state_projection.py    # engine-first lane projection
|-- state_status.py        # status payloads
|-- surface_operator.py    # operator retry, release, complete
|-- surface_pull_request.py # PR URL/number helpers
|-- surface_workpad.py     # optional runner-owned workpad mechanics
|-- surface_worktrees.py   # lane worktree helpers
|-- tick_journal.py        # engine run/events for ticks
|-- schema.yaml            # front matter schema
`-- templates/
    `-- code.md
```

## Boundaries

Python:

- claims eligible `todo` issues and applies the `code` step label
- enforces lane and actor concurrency
- creates/recovers worktrees
- dispatches the coder only for `code` and `merge`
- polls tracker, PR, runtime, and retry state
- moves labels forward/backward with idempotent side-effect records
- releases verified `done` lanes

Coder actor:

- works on exactly one lane
- in `code`, implements or handles review feedback, validates, commits, pushes,
  and opens/updates the PR
- in `merge`, opens and follows `.codex/skills/land/SKILL.md`
- returns structured JSON only
- reports `blocked` instead of asking for interactive escalation

## State

The hot lane ledger lives in the workflow state JSON. Engine tables hold durable
leases, work item projections, runtime sessions, retries, runs, events, and
side-effect history. Prompts get compact lane context; bulky journals and
terminal history stay out of actor input.
