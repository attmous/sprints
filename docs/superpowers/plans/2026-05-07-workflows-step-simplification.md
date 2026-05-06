# Workflows Step Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bloated workflows implementation with a `code` workflow step runner built around `intake -> code -> review -> merge -> done`.

**Architecture:** Keep engine, runtime, tracker, worktree, retry, and status durability. Add a new step runner path for `workflow=code`, then remove orchestrator-mode and actor-driven `change-delivery` paths after the new path is active. The public workflow contract uses `step`; old `stage`, `mode`, `gates`, `actions`, and `routing` are removed from the `code` path.

**Tech Stack:** Python, Markdown `WORKFLOW.md` contracts, YAML front matter, GitHub tracker via `gh`, git worktrees, Codex app-server runtime.

---

## File Structure

Create:

- `packages/core/src/sprints/workflows/step_labels.py`: canonical step labels and label mutation plans.
- `packages/core/src/sprints/workflows/step_routes.py`: deterministic route selection for the `code` workflow.
- `packages/core/src/sprints/workflows/step_runner.py`: tick lifecycle for step workflows.

Modify:

- `packages/core/src/sprints/workflows/templates/code.md`: rewrite to the step contract.
- `packages/core/src/sprints/workflows/prompt_variables.py`: expose `step` and keep compatibility shims temporarily.
- `packages/core/src/sprints/workflows/runtime_dispatch.py`: record `step` in dispatch metadata and prompt inputs.
- `packages/core/src/sprints/workflows/actor_outputs.py`: validate coder output by `step`.
- `packages/core/src/sprints/workflows/entry_runner.py`: route `tick` to `step_runner` for `workflow=code`.
- `packages/core/src/sprints/workflows/entry_registry.py`: make `code` the supported/default workflow once deletion happens.
- `packages/core/src/sprints/workflows/schema.yaml`: remove old required workflow concepts and accept the simplified `code` contract.
- `packages/core/src/sprints/workflows/README.md`: replace old mental model with step runner model.
- `packages/core/src/sprints/workflows/__init__.py`: remove exports tied to removed workflow modes after deletion.

Delete later:

- `packages/core/src/sprints/workflows/templates/change-delivery.md`
- `packages/core/src/sprints/workflows/templates/release.md`
- `packages/core/src/sprints/workflows/templates/triage.md`
- `packages/core/src/sprints/workflows/action_handlers.py`
- `packages/core/src/sprints/workflows/route_orchestrator.py`
- `packages/core/src/sprints/workflows/tick_orchestrator.py`
- `packages/core/src/sprints/workflows/tick_actor_driven.py`
- `packages/core/src/sprints/workflows/route_rules.py`
- `packages/core/src/sprints/workflows/route_effects.py`
- `packages/core/src/sprints/workflows/lane_completion.py`
- `packages/core/src/sprints/workflows/lane_teardown.py`
- `packages/core/src/sprints/workflows/surface_board.py`
- `packages/core/src/sprints/workflows/surface_board_state.py`
- `packages/core/src/sprints/workflows/surface_notifications.py`
- `packages/core/src/sprints/workflows/surface_review_context.py`
- `packages/core/src/sprints/workflows/surface_review_state.py`

---

### Task 1: Rewrite `code.md` To The Step Contract

**Files:**
- Modify: `packages/core/src/sprints/workflows/templates/code.md`

- [ ] **Step 1: Replace the intake claim label**

Change:

```yaml
  claim:
    remove_labels: [todo]
    add_labels: [in-progress]
    branch: codex/issue-{number}-{slug}
```

to:

```yaml
  claim:
    remove_labels: [todo]
    add_labels: [code]
    branch: codex/issue-{number}-{slug}
```

- [ ] **Step 2: Keep the worktree base path**

Ensure this remains:

```yaml
workspace:
  root: .sprints/workspace/worktrees/{{ workflow }}
```

Do not include `{{ lane_id }}` in `workspace.root`.

- [ ] **Step 3: Replace the workflow policy with step language**

Replace the current `# Workflow Policy` body with:

```md
# Workflow Policy

Sprints owns lane mechanics: tracker intake, claims, leases, worktree creation,
runtime dispatch, retries, step transitions, status, audit, and release.

The coder owns work inside one lane. Do not claim other issues, touch unrelated
paths, or ask for interactive escalation.

## Steps

This workflow uses GitHub labels as step state. Use exactly one active step
label at a time:

- `todo`: ready for intake.
- `code`: implementation or feedback-fix loop.
- `review`: PR is ready; wait for human, bot, checks, or project-board signal.
- `merge`: merge authority exists; run the land flow.
- `done`: terminal; release the lane.
- `blocked`: cannot continue without external unblock.

Flow:

```text
todo -> code -> review -> merge -> done
          ^        |
          |--------|
```

If review feedback requires changes, Sprints moves the lane from `review` back
to `code`. The coder then starts or continues from the same lane, sweeps PR
feedback, fixes required items, validates, pushes, and returns the lane to
`review`.
```

- [ ] **Step 4: Replace actor input fields**

Use this `## Input` section:

```md
## Input

Issue:
{{ issue }}

Lane:
{{ lane }}

Step:
{{ step }}

Workspace:
{{ workspace }}

Repository:
{{ repository }}

Pull request:
{{ pull_request }}

Review feedback:
{{ review_feedback }}

Attempt:
{{ attempt }}

Retry:
{{ retry }}
```

- [ ] **Step 5: Add step policy sections**

Replace the actor policy body after `## Input` with step sections:

```md
## Policy

Work on exactly one lane and follow the section for the provided `Step`.

Never claim another issue, switch lanes, modify workflow ownership, change
concurrency, or touch unrelated paths.

Never request interactive escalation. Return `blocked` only for missing auth,
permissions, secrets, tools, unsafe scope, or unrecoverable workspace state.

## Step: code

Start or continue implementation for this issue.

Before editing:

1. Read the issue, comments, current labels, branch, and PR state.
2. Find or create one persistent `## Sprints Workpad` issue comment.
3. If a PR already exists, run the PR feedback sweep before new code.
4. Sync from `origin/main`.
5. Reproduce or confirm the issue signal when possible.

Execution loop:

1. Implement the smallest scoped change.
2. Run focused validation.
3. Commit only lane-scoped changes.
4. Push the branch.
5. Create or update the PR.
6. Sweep PR feedback:
   - top-level PR comments
   - inline review comments
   - review summaries
   - failed checks
7. Address actionable feedback or reply with justified pushback.
8. Update the workpad with plan, acceptance criteria, validation, and notes.

Return `done` only when the PR exists, validation evidence exists, no known
actionable PR feedback remains, and the workpad is current.

## Step: review

Do not edit code. The runner normally idles in this step.

If dispatched manually in this step, inspect current PR state and return
`waiting` unless there is a true blocker.

## Step: merge

Open and follow `.codex/skills/land/SKILL.md`.

Do not call merge mechanics outside the land skill. If the PR cannot merge yet,
return `waiting` or `blocked` with the exact reason. If new required feedback
appears, return enough evidence for Sprints to move the lane back to `code`.

After a successful merge, return merge and cleanup evidence.

## Step: done

Terminal. Do not perform actor work.

## Step: blocked

Do not code unless the blocker has clearly been resolved. Return `blocked` with
the remaining unblock requirement, or `waiting` if the lane should remain held.
```

- [ ] **Step 6: Replace output contract**

Use this output contract:

```md
## Output

Return JSON only:

{
  "status": "done|waiting|blocked|failed",
  "step": "code|review|merge|done|blocked",
  "summary": "what happened",
  "branch": "codex/issue-20-short-name",
  "pull_request": {
    "url": "https://github.com/owner/repo/pull/123",
    "number": 123,
    "state": "open|merged|closed",
    "merged": false
  },
  "commits": [],
  "files_changed": [],
  "verification": [],
  "review_feedback": [],
  "workpad": {
    "url": "issue workpad comment URL if available",
    "updated": true
  },
  "cleanup": {
    "removed_labels": [],
    "added_labels": []
  },
  "blockers": [],
  "artifacts": {}
}
```

- [ ] **Step 7: Validate the template**

Run:

```powershell
@'
from pathlib import Path
import jsonschema, yaml
from sprints.core.contracts import load_workflow_contract_file
schema = yaml.safe_load(Path('packages/core/src/sprints/workflows/schema.yaml').read_text())
contract = load_workflow_contract_file(Path('packages/core/src/sprints/workflows/templates/code.md'))
jsonschema.validate(contract.config, schema)
print('ok code.md')
'@ | uv run python -
```

Expected output:

```text
ok code.md
```

---

### Task 2: Add Step Label Helpers

**Files:**
- Create: `packages/core/src/sprints/workflows/step_labels.py`

- [ ] **Step 1: Create canonical step helpers**

Create `step_labels.py` with:

```python
"""Canonical step labels for the code workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.workflows.lane_state import issue_labels

TODO = "todo"
CODE = "code"
REVIEW = "review"
MERGE = "merge"
DONE = "done"
BLOCKED = "blocked"

ACTIVE_STEPS = (CODE, REVIEW, MERGE, BLOCKED)
ALL_STEP_LABELS = (TODO, CODE, REVIEW, MERGE, DONE, BLOCKED)


@dataclass(frozen=True)
class StepLabelPlan:
    remove_labels: tuple[str, ...]
    add_labels: tuple[str, ...]


def lane_step(*, config: WorkflowConfig, lane: dict[str, Any]) -> str:
    del config
    tracker = lane.get("tracker") if isinstance(lane.get("tracker"), dict) else {}
    step = str(tracker.get("step") or lane.get("step") or "").strip().lower()
    if step:
        return step
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    return step_from_labels(issue.get("labels") or [])


def step_from_labels(labels: Any) -> str:
    normalized = issue_labels({"labels": labels})
    for step in ALL_STEP_LABELS:
        if step in normalized:
            return step
    return ""


def active_step_labels(labels: Any) -> set[str]:
    normalized = issue_labels({"labels": labels})
    return {label for label in ALL_STEP_LABELS if label in normalized}


def label_plan_for_step(*, current_labels: Any, target_step: str) -> StepLabelPlan:
    target = str(target_step or "").strip().lower()
    if target not in ALL_STEP_LABELS:
        raise ValueError(f"unknown code workflow step: {target_step!r}")
    existing = active_step_labels(current_labels)
    remove = tuple(label for label in ALL_STEP_LABELS if label in existing and label != target)
    add = () if target in existing else (target,)
    return StepLabelPlan(remove_labels=remove, add_labels=add)
```

- [ ] **Step 2: Compile the new module**

Run:

```powershell
uv run python -m compileall packages/core/src/sprints/workflows/step_labels.py
```

Expected: command exits `0`.

---

### Task 3: Expose `step` To Actor Prompts

**Files:**
- Modify: `packages/core/src/sprints/workflows/prompt_variables.py`
- Modify: `packages/core/src/sprints/workflows/runtime_dispatch.py`

- [ ] **Step 1: Import step helper**

In `prompt_variables.py`, add:

```python
from sprints.workflows.step_labels import lane_step
```

- [ ] **Step 2: Add `step` to actor variables**

In `actor_variables()`, add `"step": step_context` where `step_context` is computed once:

```python
step_context = actor_step(lane=lane, inputs=inputs, config=config)
```

The returned dict should include:

```python
"step": step_context,
```

Keep `"mode"` temporarily for compatibility, but have it mirror `step_context` for `workflow=code`.

- [ ] **Step 3: Add helper function**

Add this function near `actor_mode()`:

```python
def actor_step(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    inputs: dict[str, Any],
) -> str:
    for value in (inputs.get("step"), inputs.get("mode"), lane.get("step")):
        text = str(value or "").strip().lower()
        if text:
            return text
    return lane_step(config=config, lane=lane)
```

- [ ] **Step 4: Include `step` in dispatch inputs**

In `actor_dispatch_inputs()`, add:

```python
"step": inputs.get("step") or inputs.get("mode") or lane.get("step"),
```

The temporary result may still contain `mode`; the new `code.md` uses only
`step`.

- [ ] **Step 5: Record step in dispatch metadata**

In `runtime_dispatch.py`, compute:

```python
actor_step = str(inputs.get("step") or inputs.get("mode") or "").strip()
```

and include it in `_dispatch_plan_meta(... extra={...})` as:

```python
"step": actor_step,
```

Keep old `"actor_mode"` for now to avoid breaking runtime session readers.

- [ ] **Step 6: Compile changed modules**

Run:

```powershell
uv run python -m compileall packages/core/src/sprints/workflows/prompt_variables.py packages/core/src/sprints/workflows/runtime_dispatch.py
```

Expected: command exits `0`.

---

### Task 4: Add Step Route Selection

**Files:**
- Create: `packages/core/src/sprints/workflows/step_routes.py`

- [ ] **Step 1: Create route dataclass and selector**

Create `step_routes.py` with:

```python
"""Deterministic step routes for the code workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.workflows.step_labels import BLOCKED, CODE, DONE, MERGE, REVIEW, lane_step
from sprints.workflows.surface_pull_request import pull_request_url
from sprints.workflows.surface_review_state import review_has_required_changes
from sprints.workflows.lane_completion import done_release_verified
from sprints.workflows.lane_state import lane_is_terminal
from sprints.workflows.runtime_sessions import active_actor_dispatch
from sprints.workflows.state_retries import lane_retry_is_due


@dataclass(frozen=True)
class StepRoute:
    action: str
    step: str
    target_step: str | None = None
    actor: str | None = None
    reason: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value not in (None, {}, [])}


def route_code_lane(*, config: WorkflowConfig, lane: dict[str, Any]) -> StepRoute:
    step = lane_step(config=config, lane=lane)
    lane_id = str(lane.get("lane_id") or "")
    if lane_is_terminal(lane):
        return StepRoute(action="hold", step=step, reason=f"{lane_id} is terminal")
    if active_actor_dispatch(lane):
        return StepRoute(action="hold", step=step, reason="actor dispatch already active")
    status = str(lane.get("status") or "").strip().lower()
    if status == "running":
        return StepRoute(action="hold", step=step, reason="actor runtime is running")
    if status == "operator_attention":
        return StepRoute(action="hold", step=step, reason="operator attention required")
    if status == "workpad_failed":
        return StepRoute(action="hold", step=step, reason="workpad repair must succeed first")
    if status == "retry_queued" and not lane_retry_is_due(lane):
        return StepRoute(action="hold", step=step, reason="retry is not due yet")

    if step == CODE:
        return StepRoute(
            action="dispatch",
            step=CODE,
            actor="coder",
            reason="code step dispatch",
            inputs={"step": CODE},
        )
    if step == REVIEW:
        if review_has_required_changes(lane):
            return StepRoute(
                action="move_step",
                step=REVIEW,
                target_step=CODE,
                reason="review feedback requires code changes",
                inputs={"step": CODE},
            )
        if _merge_signal_present(lane):
            return StepRoute(
                action="move_step",
                step=REVIEW,
                target_step=MERGE,
                reason="merge signal present",
                inputs={"step": MERGE},
            )
        return StepRoute(action="hold", step=REVIEW, reason="waiting for review signal")
    if step == MERGE:
        return StepRoute(
            action="dispatch",
            step=MERGE,
            actor="coder",
            reason="merge step dispatch",
            inputs={"step": MERGE},
        )
    if step == DONE:
        if done_release_verified(lane):
            return StepRoute(action="release", step=DONE, reason="done verified")
        return StepRoute(action="hold", step=DONE, reason="done label present but completion is not verified")
    if step == BLOCKED:
        return StepRoute(action="hold", step=BLOCKED, reason="blocked step")
    if pull_request_url(lane):
        return StepRoute(action="move_step", step=step, target_step=REVIEW, reason="pull request exists")
    return StepRoute(action="hold", step=step, reason="lane has no code workflow step")


def next_step_after_actor_output(*, lane: dict[str, Any], output: dict[str, Any]) -> str | None:
    step = str(output.get("step") or "").strip().lower()
    status = str(output.get("status") or "").strip().lower()
    if step == CODE and status == "done":
        return REVIEW
    if step == MERGE and status == "done":
        return DONE
    return None


def _merge_signal_present(lane: dict[str, Any]) -> bool:
    signal = lane.get("merge_signal") if isinstance(lane.get("merge_signal"), dict) else {}
    if signal.get("approved") or signal.get("merge"):
        return True
    tracker = lane.get("tracker") if isinstance(lane.get("tracker"), dict) else {}
    return str(tracker.get("step") or "").strip().lower() == MERGE
```

- [ ] **Step 2: Compile the new module**

Run:

```powershell
uv run python -m compileall packages/core/src/sprints/workflows/step_routes.py
```

Expected: command exits `0`.

---

### Task 5: Add Step Runner Tick Path

**Files:**
- Create: `packages/core/src/sprints/workflows/step_runner.py`
- Modify: `packages/core/src/sprints/workflows/entry_runner.py`

- [ ] **Step 1: Create `step_runner.py`**

Create the module with:

```python
"""Step-based tick runner for the code workflow."""

from __future__ import annotations

import json
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.core.loader import load_workflow_policy
from sprints.workflows.lane_intake import claim_new_lanes
from sprints.workflows.lane_reconcile import reconcile_lanes
from sprints.workflows.lane_state import active_lanes, record_engine_lane, set_lane_status
from sprints.workflows.lane_transitions import release_lane, validate_actor_capacity
from sprints.workflows.runtime_dispatch import actor_dispatch_mode, dispatch_stage_actor_background, run_stage_actor
from sprints.workflows.state_io import (
    WorkflowState,
    load_state,
    persist_runtime_state,
    refresh_state_status,
    save_state_event,
    validate_state,
    with_state_lock,
)
from sprints.workflows.step_labels import label_plan_for_step, lane_step
from sprints.workflows.step_routes import StepRoute, route_code_lane
from sprints.workflows.surface_board import set_lane_board_state
from sprints.workflows.surface_board_state import BoardState
from sprints.workflows.tick_journal import finish_tick_journal, record_tick_journal, result_summaries, start_tick_journal


def tick_step_locked(config: WorkflowConfig) -> int:
    journal = start_tick_journal(config=config, orchestrator_output="")
    state: WorkflowState | None = None
    intake: dict[str, Any] = {}
    reconcile: dict[str, Any] = {}
    routes: list[StepRoute] = []
    results: list[dict[str, Any]] = []
    try:
        policy = load_workflow_policy(config.workflow_root)
        state = load_state(config.storage.state_path, workflow=config.workflow_name, first_stage=config.first_stage)
        validate_state(config, state)
        reconcile = reconcile_lanes(config=config, state=state)
        record_tick_journal(config=config, journal=journal, state=state, event="step.reconciled", details={"reconcile": reconcile})
        intake = claim_new_lanes(config=config, state=state)
        record_tick_journal(config=config, journal=journal, state=state, event="step.intake_completed", details={"intake": intake})
        if not active_lanes(state):
            state.status = "idle"
            state.idle_reason = intake.get("reason") or "no active lanes"
            _save_step_tick(config=config, state=state, event="step_idle", extra={"intake": intake, "reconcile": reconcile})
            finish_tick_journal(config=config, journal=journal, state=state, status="completed", terminal_event="step.idle", selected_count=0, completed_count=0)
            return 0
        dispatch_counts: dict[str, int] = {}
        for lane in list(active_lanes(state)):
            route = route_code_lane(config=config, lane=lane)
            routes.append(route)
            result = _apply_step_route(config=config, policy=policy, state=state, lane=lane, route=route, dispatch_counts=dispatch_counts)
            results.append(result)
        refresh_state_status(state, idle_reason="no active lanes")
        _save_step_tick(
            config=config,
            state=state,
            event="step_tick",
            extra={
                "intake": intake,
                "reconcile": reconcile,
                "routes": [route.to_dict() for route in routes],
                "results": results,
            },
        )
        finish_tick_journal(
            config=config,
            journal=journal,
            state=state,
            status="completed",
            terminal_event="step.completed",
            selected_count=len(active_lanes(state)),
            completed_count=len(results),
            details={"results": result_summaries(results)},
        )
        return 0
    except Exception as exc:
        if state is not None:
            persist_runtime_state(config=config, state=state)
        finish_tick_journal(
            config=config,
            journal=journal,
            state=state,
            status="failed",
            terminal_event="step.failed",
            selected_count=len(active_lanes(state)) if state else 0,
            completed_count=len(results),
            error=exc,
        )
        raise


def tick_step(config: WorkflowConfig) -> int:
    return with_state_lock(
        config=config,
        owner_role="workflow-step-tick",
        callback=lambda: tick_step_locked(config),
    )


def _apply_step_route(
    *,
    config: WorkflowConfig,
    policy: Any,
    state: WorkflowState,
    lane: dict[str, Any],
    route: StepRoute,
    dispatch_counts: dict[str, int],
) -> dict[str, Any]:
    if route.action == "hold":
        return {"lane_id": lane.get("lane_id"), "status": "held", "route": route.to_dict()}
    if route.action == "release":
        release_lane(config=config, lane=lane, reason=route.reason or "released")
        record_engine_lane(config=config, lane=lane)
        persist_runtime_state(config=config, state=state)
        return {"lane_id": lane.get("lane_id"), "status": "released", "route": route.to_dict()}
    if route.action == "move_step":
        target = str(route.target_step or "")
        _set_lane_step(config=config, lane=lane, target_step=target, reason=route.reason)
        record_engine_lane(config=config, lane=lane)
        persist_runtime_state(config=config, state=state)
        return {"lane_id": lane.get("lane_id"), "status": "step_moved", "route": route.to_dict()}
    if route.action == "dispatch":
        actor = str(route.actor or "coder")
        stage = config.first_stage
        validate_actor_capacity(config=config, actor_name=actor, dispatch_counts=dispatch_counts)
        inputs = {"step": route.step, **dict(route.inputs or {})}
        if actor_dispatch_mode(config) == "background":
            dispatch = dispatch_stage_actor_background(config=config, policy=policy, state=state, lane=lane, actor_name=actor, inputs=inputs)
        else:
            dispatch = run_stage_actor(config=config, policy=policy, state=state, lane=lane, actor_name=actor, inputs=inputs)
        dispatch_counts[actor] = dispatch_counts.get(actor, 0) + 1
        return {"lane_id": lane.get("lane_id"), "status": "dispatched", "route": route.to_dict(), "dispatch": dispatch}
    return {"lane_id": lane.get("lane_id"), "status": "skipped", "route": route.to_dict()}


def _set_lane_step(*, config: WorkflowConfig, lane: dict[str, Any], target_step: str, reason: str) -> None:
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    plan = label_plan_for_step(current_labels=issue.get("labels") or [], target_step=target_step)
    # Temporary bridge: surface_board currently owns label mutation and accepts BoardState.
    transition = set_lane_board_state(config=config, lane=lane, target=BoardState(target_step))
    if transition.get("status") == "failed":
        raise RuntimeError(str(transition.get("error") or f"failed to move lane to {target_step}"))
    lane["step"] = target_step
    tracker = lane.setdefault("tracker", {})
    if isinstance(tracker, dict):
        tracker["step"] = target_step
    set_lane_status(config=config, lane=lane, status="claimed", actor=None, reason=reason or f"moved to {target_step}")
    del plan


def _save_step_tick(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    event: str,
    extra: dict[str, Any] | None = None,
) -> None:
    save_state_event(config=config, state=state, event=event, extra=extra)
    print(json.dumps(state.to_dict(), indent=2, sort_keys=True))
```

- [ ] **Step 2: Route `code` tick through step runner**

In `entry_runner.py`, replace:

```python
from sprints.workflows.tick_orchestrator import tick
```

with:

```python
from sprints.workflows.step_runner import tick_step
from sprints.workflows.tick_orchestrator import tick
```

Then change the tick command block:

```python
if args.command == "tick":
    return tick(workspace, orchestrator_output=args.orchestrator_output)
```

to:

```python
if args.command == "tick":
    if workspace.workflow_name == "code":
        if str(args.orchestrator_output or "").strip():
            raise RuntimeError("code workflow does not accept orchestrator output")
        return tick_step(workspace)
    return tick(workspace, orchestrator_output=args.orchestrator_output)
```

- [ ] **Step 3: Compile step runner path**

Run:

```powershell
uv run python -m compileall packages/core/src/sprints/workflows/step_runner.py packages/core/src/sprints/workflows/entry_runner.py
```

Expected: command exits `0`.

---

### Task 6: Validate Coder Output By Step

**Files:**
- Modify: `packages/core/src/sprints/workflows/actor_outputs.py`

- [ ] **Step 1: Add generic coder branch**

In `apply_actor_output_status()`, before actor-specific `implementer` logic, add handling for `actor_name == "coder"`:

```python
    if actor_name == "coder":
        _apply_coder_output_status(
            config=config,
            lane=lane,
            actor_name=actor_name,
            output=output,
            status=status,
            blockers=blockers,
        )
        return
```

- [ ] **Step 2: Add `_apply_coder_output_status()`**

Add:

```python
def _apply_coder_output_status(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    actor_name: str,
    output: dict[str, Any],
    status: str,
    blockers: list[Any],
) -> None:
    step = str(output.get("step") or lane.get("step") or "").strip().lower()
    if status not in {"done", "waiting", "blocked", "failed"}:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_output_contract_failed",
            message=f"coder returned unsupported status {status!r}",
            artifacts={"actor": actor_name, "output": output},
        )
        return
    if status in {"blocked", "failed"} or blockers:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason=blocker_reason(output) or status or "actor_blocked",
            message=str(output.get("summary") or f"{actor_name} returned {status}"),
            artifacts={
                "actor": actor_name,
                "blockers": blockers,
                "branch": lane.get("branch"),
                "pull_request": lane.get("pull_request"),
                "artifacts": output.get("artifacts") if isinstance(output.get("artifacts"), dict) else {},
            },
        )
        return
    if step == "code" and status == "done":
        if not pull_request_url(lane):
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message="code step requires pull_request.url before review",
                artifacts=contract_artifacts(lane),
            )
            return
        verification = output.get("verification")
        if not isinstance(verification, list) or not verification:
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message="code step requires non-empty verification evidence",
                artifacts=contract_artifacts(lane),
            )
            return
    if step == "merge" and status == "done":
        pull_request = output.get("pull_request")
        if not isinstance(pull_request, dict) or not pull_request.get("merged"):
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message="merge step requires merged pull request evidence",
                artifacts=contract_artifacts(lane),
            )
            return
    set_lane_status(
        config=config,
        lane=lane,
        status="waiting",
        actor=None,
        reason=f"{actor_name} returned {status} for step {step}",
    )
```

- [ ] **Step 3: Update runtime status helper**

In `runtime_dispatch.py`, update `_actor_output_runtime_status()`:

```python
    if actor_name == "coder" and status in {"done", "waiting"}:
        return "completed"
```

- [ ] **Step 4: Compile changed modules**

Run:

```powershell
uv run python -m compileall packages/core/src/sprints/workflows/actor_outputs.py packages/core/src/sprints/workflows/runtime_dispatch.py
```

Expected: command exits `0`.

---

### Task 7: Apply Step Transition After Actor Completion

**Files:**
- Modify: `packages/core/src/sprints/workflows/step_runner.py`
- Modify: `packages/core/src/sprints/workflows/runtime_dispatch.py`

- [ ] **Step 1: Add transition helper**

In `step_runner.py`, add:

```python
def apply_step_after_actor_output(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    lane: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    from sprints.workflows.step_routes import next_step_after_actor_output

    target = next_step_after_actor_output(lane=lane, output=output)
    if not target:
        return {"status": "held", "reason": "actor output did not request step transition"}
    _set_lane_step(
        config=config,
        lane=lane,
        target_step=target,
        reason=f"actor completed step {output.get('step')}",
    )
    record_engine_lane(config=config, lane=lane)
    persist_runtime_state(config=config, state=state)
    return {"status": "step_moved", "target_step": target}
```

- [ ] **Step 2: Call it for inline actor dispatch**

In `runtime_dispatch.py`, after `apply_actor_output_status(...)` in `run_stage_actor()`, add:

```python
    if config.workflow_name == "code" and actor_name == "coder":
        from sprints.workflows.step_runner import apply_step_after_actor_output

        apply_step_after_actor_output(
            config=config,
            state=state,
            lane=lane,
            output=parsed,
        )
```

- [ ] **Step 3: Call it for background actor completion**

In `_finalize_background_actor_success()`, after `apply_actor_output_status(...)`, add the same guarded import/call.

- [ ] **Step 4: Compile changed modules**

Run:

```powershell
uv run python -m compileall packages/core/src/sprints/workflows/step_runner.py packages/core/src/sprints/workflows/runtime_dispatch.py
```

Expected: command exits `0`.

---

### Task 8: Shrink Supported Workflows And Schema

**Files:**
- Modify: `packages/core/src/sprints/workflows/entry_registry.py`
- Modify: `packages/core/src/sprints/workflows/schema.yaml`
- Modify: `packages/core/src/sprints/core/bootstrap.py`
- Modify: `packages/core/src/sprints/core/init_wizard.py`
- Delete: old template files only after imports/CLI choices are updated

- [ ] **Step 1: Change supported workflow names**

In `entry_registry.py`, change:

```python
SUPPORTED_WORKFLOW_NAMES = ("code", "change-delivery", "release", "triage")
```

to:

```python
SUPPORTED_WORKFLOW_NAMES = ("code",)
```

- [ ] **Step 2: Restrict schema workflow enum**

In `schema.yaml`, change:

```yaml
workflow:
  enum: [code, change-delivery, release, triage]
```

to:

```yaml
workflow:
  enum: [code]
```

- [ ] **Step 3: Remove routing/gates/actions expectations from schema**

Delete the `routing`, `gates`, and `actions` schema blocks. Keep `runtime`,
`tracker`, `intake`, `workspace`, `workpad`, `concurrency`, and `storage`.

- [ ] **Step 4: Delete old templates**

Delete:

```text
packages/core/src/sprints/workflows/templates/change-delivery.md
packages/core/src/sprints/workflows/templates/release.md
packages/core/src/sprints/workflows/templates/triage.md
```

- [ ] **Step 5: Validate remaining template**

Run:

```powershell
@'
from pathlib import Path
import jsonschema, yaml
from sprints.core.contracts import load_workflow_contract_file
schema = yaml.safe_load(Path('packages/core/src/sprints/workflows/schema.yaml').read_text())
for path in sorted(Path('packages/core/src/sprints/workflows/templates').glob('*.md')):
    contract = load_workflow_contract_file(path)
    jsonschema.validate(contract.config, schema)
    print(f'ok {path.name}')
'@ | uv run python -
```

Expected output:

```text
ok code.md
```

---

### Task 9: Remove Old Runner Paths

**Files:**
- Delete old workflow modules listed below.
- Modify imports in remaining files until `rg` finds no references.

- [ ] **Step 1: Search references**

Run:

```powershell
rg -n "tick_orchestrator|tick_actor_driven|route_rules|route_effects|route_orchestrator|action_handlers|lane_completion|lane_teardown|surface_board|surface_board_state|surface_notifications|surface_review_context|surface_review_state" packages/core/src/sprints packages/cli/src
```

Expected: references exist before deletion.

- [ ] **Step 2: Delete unused modules**

Delete:

```text
packages/core/src/sprints/workflows/action_handlers.py
packages/core/src/sprints/workflows/route_orchestrator.py
packages/core/src/sprints/workflows/tick_orchestrator.py
packages/core/src/sprints/workflows/tick_actor_driven.py
packages/core/src/sprints/workflows/route_rules.py
packages/core/src/sprints/workflows/route_effects.py
packages/core/src/sprints/workflows/lane_completion.py
packages/core/src/sprints/workflows/lane_teardown.py
packages/core/src/sprints/workflows/surface_notifications.py
packages/core/src/sprints/workflows/surface_review_context.py
packages/core/src/sprints/workflows/surface_review_state.py
```

Do not delete `surface_board.py` and `surface_board_state.py` until
`step_runner.py` no longer imports them. In this plan, `_set_lane_step()` still
bridges through them temporarily.

- [ ] **Step 3: Remove imports and references**

Use `rg` from Step 1 and remove remaining imports from:

```text
packages/core/src/sprints/workflows/README.md
packages/core/src/sprints/workflows/__init__.py
packages/core/src/sprints/workflows/entry_runner.py
packages/core/src/sprints/workflows/lane_transitions.py
packages/core/src/sprints/workflows/prompt_context.py
packages/core/src/sprints/workflows/prompt_variables.py
packages/core/src/sprints/workflows/runtime_dispatch.py
```

- [ ] **Step 4: Compile workflows package**

Run:

```powershell
uv run python -m compileall packages/core/src/sprints/workflows
```

Expected: command exits `0`.

---

### Task 10: Update Workflows README

**Files:**
- Modify: `packages/core/src/sprints/workflows/README.md`

- [ ] **Step 1: Replace the layout section**

Describe the new package shape:

```text
workflows/
|-- entry_registry.py
|-- entry_runner.py
|-- step_runner.py
|-- step_routes.py
|-- step_labels.py
|-- lane_intake.py
|-- lane_reconcile.py
|-- lane_state.py
|-- runtime_dispatch.py
|-- runtime_sessions.py
|-- actor_runtime.py
|-- actor_outputs.py
|-- prompt_variables.py
|-- prompt_context.py
|-- state_io.py
|-- state_retries.py
|-- state_effects.py
|-- state_projection.py
|-- state_status.py
|-- surface_operator.py
|-- surface_pull_request.py
|-- surface_workpad.py
|-- surface_worktrees.py
|-- tick_journal.py
|-- schema.yaml
`-- templates/
    `-- code.md
```

- [ ] **Step 2: Replace contract shape section**

Use:

```md
`WORKFLOW.md` has YAML front matter for tracker, intake, workspace, runtime,
storage, and actor policy.

`code` uses steps:

```text
todo -> code -> review -> merge -> done
          ^        |
          |--------|
```

Python owns step transitions. The coder owns work inside one lane worktree.
```

- [ ] **Step 3: Remove old sections**

Remove text about:

- orchestrator prompt;
- orchestrator decisions;
- actor-driven routing table;
- gates/actions;
- reviewer/implementer split.

- [ ] **Step 4: Verify docs mention no deleted files**

Run:

```powershell
rg -n "orchestrator|actor-driven|routing|gates|actions|change-delivery|reviewer|implementer" packages/core/src/sprints/workflows/README.md
```

Expected: no output, except if mentioning removed history intentionally. Prefer no output.

---

### Task 11: Final Verification

**Files:**
- No edits unless verification finds a problem.

- [ ] **Step 1: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: only intended workflow simplification files are changed/deleted/added.

- [ ] **Step 2: Validate templates**

Run:

```powershell
@'
from pathlib import Path
import jsonschema, yaml
from sprints.core.contracts import load_workflow_contract_file
schema = yaml.safe_load(Path('packages/core/src/sprints/workflows/schema.yaml').read_text())
for path in sorted(Path('packages/core/src/sprints/workflows/templates').glob('*.md')):
    contract = load_workflow_contract_file(path)
    jsonschema.validate(contract.config, schema)
    print(f'ok {path.name}')
'@ | uv run python -
```

Expected:

```text
ok code.md
```

- [ ] **Step 3: Compile packages**

Run:

```powershell
uv run python -m compileall packages/core/src/sprints packages/cli/src/sprints_cli packages/plugins/hermes/src
```

Expected: command exits `0`.

- [ ] **Step 4: Run focused ruff**

Run:

```powershell
uv run ruff check packages/core/src/sprints/workflows packages/core/src/sprints/core packages/cli/src/sprints_cli packages/plugins/hermes/src
```

Expected: command exits `0`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add docs/superpowers/specs/2026-05-07-code-workflow-steps-spec.md docs/superpowers/specs/2026-05-07-workflows-simplification-spec.md docs/superpowers/plans/2026-05-07-workflows-step-simplification.md packages/core/src/sprints
git commit -m "workflow: simplify code step runner"
```

Expected: commit succeeds.

---

## Self-Review

Spec coverage:

- worktree base path: Task 1.
- `step` replaces `mode`: Tasks 1, 3, 6, 7.
- deterministic forward/back transitions: Tasks 4, 5, 7.
- no `rework` durable step: Tasks 1, 4, 8.
- delete old paths: Tasks 8, 9.
- docs update: Task 10.

Known sequencing note:

- `surface_board.py` and `surface_board_state.py` are kept temporarily because
  the first `step_runner.py` implementation bridges through existing label
  mutation. Delete them in a follow-up once `step_labels.py` directly applies
  tracker labels.
