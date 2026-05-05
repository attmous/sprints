# Runner Split Spec

`sprints/workflows/runner.py` is now the main pressure point in the workflow
package. It owns CLI routing, state locking, tick lifecycle, actor dispatch,
background worker execution, operator commands, tick journaling, status writes,
and actor output parsing. That made sense while the model was changing quickly.
It is now too much surface in one file.

The split must preserve behavior. This is a mechanical cleanup, not a workflow
redesign.

Status: implemented.

## Goal

Make `runner.py` a thin command router.

After the split, a reader should be able to answer these questions by file
name:

| Question | File |
| --- | --- |
| What CLI command was called? | `runner.py` |
| What happens during one orchestrator tick? | `ticks.py` |
| Where is tick durability recorded? | `tick_journal.py` |
| How are actors launched? | `dispatch.py` |
| How do operator lane commands mutate state? | `operator.py` |
| How is workflow state loaded, saved, and locked? | `state_io.py` |

## Non-Goals

- No workflow policy changes.
- No `WORKFLOW.md` schema changes.
- No runtime adapter changes.
- No tracker or code-host changes.
- No test scaffolding wave.
- No compatibility shims for old module names unless an internal import needs a
  short-lived alias during the same refactor.

## Target Layout

```text
sprints/workflows/
|-- runner.py          # CLI parser and command routing only
|-- inspection.py      # validate, show, status, and lanes commands
|-- state_io.py        # WorkflowState, state file IO, audit JSONL, state lock
|-- ticks.py           # tick lifecycle and orchestrator invocation
|-- tick_journal.py    # engine run/events for workflow.tick.*
|-- dispatch.py        # actor dispatch, background worker, heartbeats
|-- operator.py        # operator retry/release/complete commands
|-- variables.py       # actor/action prompt variable builders
|-- transitions.py     # existing decision validation and lane transitions
|-- reconcile.py       # existing reconciliation
|-- intake.py          # existing lane intake
|-- retries.py         # existing workflow adapter for engine retry mechanics
`-- status.py          # existing engine-first status projection
```

`state_io.py` is the only extra file beyond the first sketch. It prevents import
cycles. Tick, dispatch, and operator code all need state IO and locking; keeping
that in `runner.py` would force the new modules to import the command router.

## Module Contracts

### `runner.py`

Owns:

- `main(workspace, argv)`
- argparse command definitions
- dispatch from command name to module function
- final stdout printing when the command is explicitly a display command

Does not own:

- tick mechanics
- actor dispatch
- background worker mechanics
- state lock implementation
- operator lane mutation logic

Expected imports:

```python
from workflows.operator import operator_complete, operator_release, operator_retry
from workflows.ticks import tick
from workflows.dispatch import run_actor_worker
from workflows.status import build_status
from workflows.state_io import WorkflowState, load_state, save_state
```

### `state_io.py`

Owns:

- `WorkflowState`
- `load_state()`
- `save_state()`
- `append_audit()`
- `persist_runtime_state()`
- `save_state_event()`
- `with_state_lock()`
- `update_state_locked()`
- state lock renewer

Rules:

- This module may use `EngineStore` for workflow-state locks.
- This module must not import `ticks.py`, `dispatch.py`, or `operator.py`.
- This module must stay policy-neutral.

### `inspection.py`

Owns:

- `validate_command()`
- `show_command()`
- `status_command()`
- `lanes_command()`

Rules:

- Read-only CLI commands live here.
- This module may render JSON for operator-facing command output.
- This module must not mutate lane state.

### `ticks.py`

Owns:

- `tick()`
- `tick_locked()`
- `refresh_state_status()`
- `save_tick()`
- `save_failed_tick()`
- `run_orchestrator()`
- `apply_decisions()`
- `plan_decisions()`
- `apply_decision()`

Rules:

- Tick lifecycle stays readable in one top-to-bottom function.
- Tick journal calls are explicit, but journal implementation lives in
  `tick_journal.py`.
- Actor execution is delegated to `dispatch.py`.
- Operator commands do not live here.

### `tick_journal.py`

Owns:

- `TickJournal`
- `start_tick_journal()`
- `record_tick_journal()`
- `finish_tick_journal()`
- tick decision/result summaries used only for journal payloads

Rules:

- This module writes only engine run/event records.
- It must not mutate lane state.
- It may read lane summaries for counts and journal payloads.

### `dispatch.py`

Owns:

- `parse_actor_output()`
- actor prompt variable rendering if it is only used by dispatch
- `run_stage_actor()`
- `dispatch_stage_actor_background()`
- `run_actor_worker()`
- actor heartbeat and dispatch file paths
- runtime metadata extraction
- `_ActorOutputError`

Rules:

- This module owns the runtime boundary.
- It records actor dispatch/session progress but does not decide the next lane
  stage.
- It may call transition helpers after actor output is parsed because applying
  actor output is part of closing the dispatch.

### `variables.py`

Owns:

- actor prompt variables
- action prompt variables
- review feedback projection used by both actors and actions

Rules:

- This module prepares prompt context only.
- It must not mutate lane state.

### `operator.py`

Owns:

- `operator_retry()`
- `operator_release()`
- `operator_complete()`

Rules:

- Operator commands acquire the shared workflow state lock.
- Operator commands refuse unsafe mutations, such as releasing a running lane.
- Operator commands use the same save/audit path as ticks.

## Migration Waves

### Wave 1: Extract State IO

Move `WorkflowState`, state load/save, audit append, state lock, lock renewer,
runtime state persistence, and locked update helpers into `state_io.py`.

Keep function names stable except removing leading underscores for functions
that are intentionally imported by sibling modules.

Verification:

- `uv run ruff check sprints/workflows/runner.py sprints/workflows/state_io.py`
- `python -m compileall -q sprints`

### Wave 2: Extract Tick Journal

Move tick journal dataclass and helper functions into `tick_journal.py`.

The only allowed engine writes in this module are:

- `EngineStore.start_run(mode="tick")`
- `EngineStore.append_event(event_type="workflow.tick.*")`
- `EngineStore.finish_run(...)`

Verification:

- Existing temp-root tick journal smoke still passes.
- `uv run ruff check sprints/workflows/tick_journal.py`

### Wave 3: Extract Dispatch

Move actor dispatch and background worker code into `dispatch.py`.

This is the highest-risk wave because it touches runtime sessions, dispatch
journal, background process files, heartbeat files, and actor output parsing.
Do not combine it with behavior cleanup.

Verification:

- Inline actor dispatch import path compiles.
- Background actor worker command still resolves.
- `python -m compileall -q sprints`

### Wave 4: Extract Operator Commands

Move manual retry/release/complete commands into `operator.py`.

Verification:

- `operator.py` imports no CLI parser code.
- `runner.py` only routes to operator functions.

### Wave 5: Move Tick Lifecycle

Move `_tick`, `_tick_locked`, orchestrator invocation, decision planning, and
decision application into `ticks.py`.

After this wave, `runner.py` should contain no lane mutation logic.

Verification:

- `uv run ruff check sprints`
- `python -m compileall -q sprints`
- one dry tick with explicit orchestrator output against a temp workflow root
if a small local fixture is available

### Wave 6: Extract Read-Side Helpers

Move validate/show/status/lanes command handlers to `inspection.py` and prompt
variable builders to `variables.py`.

Verification:

- `runner.py` imports only command handlers and execution entry points.
- observe code owns stall helpers under `observe/stalls.py`.

## Final Acceptance

`runner.py` is acceptable when it contains only:

- imports
- CLI argument definitions
- command dispatch
- simple JSON/text printing for command outputs

It is not acceptable if it still contains:

- `WorkflowState`
- state lock code
- actor dispatch code
- background worker mechanics
- tick journal code
- tick lifecycle logic
- operator lane mutation logic

## Import Rules

Allowed dependency direction:

```text
runner.py
  -> inspection.py
  -> ticks.py
  -> dispatch.py
  -> tick_journal.py
  -> state_io.py

runner.py
  -> operator.py
  -> state_io.py

dispatch.py
  -> variables.py
  -> state_io.py

ticks.py
  -> variables.py

tick_journal.py
  -> EngineStore
```

Forbidden:

- `state_io.py` importing `runner.py`, `ticks.py`, `dispatch.py`, or
  `operator.py`
- `tick_journal.py` mutating lane state
- `dispatch.py` calling CLI parser functions
- `operator.py` calling tick internals
- `variables.py` mutating lane state
- `runner.py` becoming a shared helper module again

## Rollback Strategy

Each wave should be a separate commit. If a wave breaks runtime behavior,
revert that wave only. Do not revert earlier durability work unless the break
is proven to come from that earlier change.

The safest sequence is state IO first, tick journal second, dispatch third.
Dispatch is the only wave that should be treated as high blast radius.
