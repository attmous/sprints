# Workflows Simplification Spec

Date: 2026-05-07

## Problem

`sprints/workflows/` is carrying several designs at the same time:

- legacy orchestrator-mode stages, gates, actions, and LLM decisions;
- actor-driven `change-delivery` routing with reviewer/implementer actors;
- new `code` workflow direction with one coder and step-based state;
- compatibility helpers for modes, board state, rework, reviewer signals, and
  runner-owned completion.

That makes the package large and hard to reason about. The new target is
simpler:

```text
tracker issue -> lane -> step -> coder dispatch or hold -> step transition
```

The user-facing workflow primitive should be `step`, not actor/stage/gate/mode.

## Decision

Do not keep both old designs and the new step model.

The recommended path is **not a full repository restart**. The engine, runtime
adapters, trackers, Codex app-server integration, leases, retries, worktrees,
status projection, and daemon are useful and should stay.

The recommended path is a **workflow package hard cut**:

- keep the durable mechanics that are already proven;
- remove orchestrator-mode and actor-driven `change-delivery` mechanics from
  `workflows/`;
- make `code` the default and primary workflow;
- implement one step runner for `code`;
- keep `release` and `triage` templates only if they can run on the same simple
  single-actor step contract, otherwise remove them from bundled workflows.

## Target Mental Model

```text
Workflow contract
  declares tracker, intake, workspace, runtime, storage, and actor policy

Runner tick
  reconciles tracker/PR/runtime state
  claims eligible todo issues
  derives current step from labels
  dispatches coder only for runnable steps
  applies deterministic step transitions
  persists lane state and engine projections

Coder actor
  receives one lane and one step
  performs code or merge work in one git worktree
  returns JSON
```

## Keep

Keep these concepts:

- `WORKFLOW.md` front matter + Markdown actor policy.
- `WorkflowConfig`, but simplify it around runtime, storage, tracker, intake,
  workspace, and inferred single actor.
- `WorkflowState` lane ledger.
- engine-backed state projection, audit, retry, lease, and runtime session
  storage.
- lane intake from tracker.
- GitHub tracker/code-host integration.
- git worktree creation/reuse.
- runtime dispatch through Codex app-server and other runtime adapters.
- status, lanes, retry, release, complete operator commands.
- prompt compaction for lane/workflow context.
- bundled skills appended to actor prompts.

## Remove

Remove these from the `code` workflow path:

- orchestrator actor;
- orchestrator prompt;
- orchestrator decisions;
- `stages` as user-facing workflow config;
- `gates`;
- deterministic `actions`;
- actor-driven routing table;
- `mode`;
- `board_state`;
- reviewer actor;
- implementer actor;
- `rework` as a durable step/label;
- runner-owned pull request merge;
- runner-owned workpad for `code`.

## Files To Delete Or Retire

Delete once no imports remain:

```text
workflows/action_handlers.py
workflows/route_orchestrator.py
workflows/tick_orchestrator.py
```

Delete or replace after step runner lands:

```text
workflows/tick_actor_driven.py
workflows/route_rules.py
workflows/route_effects.py
workflows/lane_completion.py
workflows/lane_teardown.py
workflows/surface_board.py
workflows/surface_board_state.py
workflows/surface_notifications.py
workflows/surface_review_context.py
workflows/surface_review_state.py
```

Remove templates unless they are rewritten to the new contract:

```text
workflows/templates/change-delivery.md
workflows/templates/release.md
workflows/templates/triage.md
```

`change-delivery.md` should be removed first. Its concepts are replaced by
`code.md` plus later `review.md`.

## Files To Keep But Slim

```text
workflows/entry_registry.py
workflows/entry_runner.py
workflows/entry_inspection.py
workflows/lane_intake.py
workflows/lane_reconcile.py
workflows/lane_state.py
workflows/lane_transitions.py
workflows/runtime_dispatch.py
workflows/runtime_sessions.py
workflows/actor_runtime.py
workflows/actor_outputs.py
workflows/prompt_context.py
workflows/prompt_variables.py
workflows/state_io.py
workflows/state_retries.py
workflows/state_effects.py
workflows/state_projection.py
workflows/state_status.py
workflows/surface_operator.py
workflows/surface_pull_request.py
workflows/surface_workpad.py
workflows/surface_worktrees.py
workflows/tick_journal.py
```

Expected slimming:

- `entry_registry.py`: supported workflows should start with `("code",)`.
- `entry_runner.py`: `tick` should call the new step runner, not orchestrator
  or actor-driven dispatch.
- `lane_state.py`: rename/clarify step-facing fields; avoid public `stage`,
  `mode`, and `board_state` language.
- `lane_transitions.py`: keep status/retry/release primitives; remove
  orchestrator decision helpers.
- `runtime_dispatch.py`: dispatch by `step`; remove `mode` metadata from the
  code path.
- `actor_outputs.py`: validate output by `step`, not actor name/mode.
- `prompt_variables.py`: expose `step`; stop exposing `mode` and `board_state`
  to `code.md`.
- `prompt_context.py`: remove orchestrator-specific payload builders when
  orchestrator mode is deleted.
- `schema.yaml`: remove actor-driven routing, gates, actions, stages as required
  concepts for new workflows.

## New Files

Add:

```text
workflows/step_runner.py
workflows/step_routes.py
workflows/step_labels.py
```

### `step_labels.py`

Owns canonical labels for `code`:

```text
todo
code
review
merge
done
blocked
```

Responsibilities:

- derive current step from issue labels;
- identify active step labels;
- build label mutation plans.

### `step_routes.py`

Owns deterministic code workflow transitions:

```text
todo claim             -> code
code done with PR      -> review
review feedback        -> code
review merge signal    -> merge
merge merged           -> done
done verified          -> release
blocked                -> hold
```

It returns a small route object:

```json
{
  "action": "dispatch|move_step|hold|release|operator_attention",
  "step": "code",
  "target_step": "review",
  "actor": "coder",
  "reason": "..."
}
```

### `step_runner.py`

Owns one tick for step workflows:

1. load policy;
2. load state;
3. reconcile lanes;
4. claim new lanes;
5. derive lane step;
6. select step route;
7. apply label transition or dispatch coder;
8. persist state/audit/tick journal.

## Code Workflow Contract

The only bundled workflow after the cut should be `code.md`.

It should not contain:

- `orchestration`;
- `actors`;
- `stages`;
- `gates`;
- `actions`;
- `routing`;
- `lifecycle`;
- `modes`.

It should contain:

- `tracker`;
- `code-host`;
- `polling`;
- `intake`;
- `workspace`;
- `workpad`;
- `concurrency`;
- `runtime`;
- `storage`;
- `# Workflow Policy`;
- `# Actor: coder`.

## Migration Strategy

Do this in waves.

### Wave 1: Step Contract

- update `code.md` to the step model;
- change intake claim label from `in-progress` to `code`;
- add `Step: {{ step }}` to actor input;
- update output contract to `status` + `step`.

### Wave 2: Step Variables

- add step derivation helpers;
- make `prompt_variables.py` expose `step`;
- keep `mode` internally only long enough to avoid breaking old code during the
  transition.

### Wave 3: Step Runner

- add `step_runner.py`, `step_routes.py`, and `step_labels.py`;
- route `workflow=code` ticks through `step_runner`;
- keep old runner files present but unused.

### Wave 4: Delete Old Paths

- remove `change-delivery.md`;
- remove orchestrator-mode files;
- remove actor-driven route files;
- shrink schema and README;
- update supported workflows to `code` only unless `release` and `triage` are
  rewritten.

### Wave 5: Polish

- remove remaining `mode`, `board_state`, `implementer`, `reviewer`, `rework`
  names from active code path;
- update docs and status output vocabulary;
- run schema validation and compile checks.

## Start From Scratch?

Starting from scratch inside `workflows/` would feel cleaner for one day, but it
would recreate hard problems already solved elsewhere:

- state locks;
- engine projections;
- retry history;
- runtime sessions;
- background dispatch;
- prompt compaction;
- tracker reconciliation;
- GitHub PR parsing;
- worktree setup;
- status/watch output.

Therefore, do not start from scratch at repo level.

The best compromise is a **new step runner path inside the existing package**,
then delete the old paths once the new path is active.

## Acceptance Criteria

- `workflow=code` no longer uses orchestrator-mode or actor-driven routing.
- `WORKFLOW.md` for `code` contains no actors/stages/gates/actions/routing.
- actor prompt receives `step`, not `mode`.
- canonical labels are `todo`, `code`, `review`, `merge`, `done`, `blocked`.
- no `rework` durable step exists.
- review feedback routes back to `code`.
- merge authority routes to `merge`.
- merged output routes to `done`.
- Sprints uses git worktrees as lane workspaces.
- schema validation passes for remaining bundled templates.
- Python compile check passes.
- package docs describe the new step runner mental model.
