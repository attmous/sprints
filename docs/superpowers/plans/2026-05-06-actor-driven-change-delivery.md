# Actor-Driven Change Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the bundled `change-delivery` workflow from orchestrator-agent routing to actor-driven delivery where Python owns durable lane mechanics and actors own implementation, review, rework, landing, and final label cleanup.

**Architecture:** Keep the generic orchestrator-driven engine available for other workflows. Add an explicit `orchestration.mode: actor-driven` path for `change-delivery` that routes lanes from GitHub label-backed board state, dispatches implementer/reviewer actor modes, verifies outputs, and persists all transitions without normal orchestrator LLM calls.

**Tech Stack:** Python 3.12, uv, SQLite engine state, GitHub CLI-backed tracker/code-host integration, Codex app server runtime, Hermes Agent CLI runtime, Markdown `WORKFLOW.md` contracts, YAML/JSON schema validation.

---

## Locked Mental Model

This plan is now locked to the Symphony-inspired split:

- Python is the coded orchestrator. It owns ticks, intake, reconciliation,
  lane claims, leases, retries, runtime sessions, prompt assembly, compaction,
  dispatch, observe/status, audit, and final verification.
- The implementer is a prompted delivery worker for exactly one lane. It owns
  `implement`, `rework`, and `land` modes inside that lane only.
- The reviewer is a prompted fresh-context review worker for exactly one PR/lane.
  It must not resume implementer context.
- `WORKFLOW.md` is config plus policy. It does not create an orchestrator actor
  for actor-driven `change-delivery`.
- The engine is durable memory. GitHub labels/project automation are the external
  operator surface.

The boundary rule is:

```text
Python decides which lane, actor, and mode should run.
Actors decide how to complete their scoped lane work.
```

PR #110 currently contains the foundation slice: actor-driven config support,
label-backed board state helpers, durable workpads, explicit actor modes, and
deterministic tick routing. The remaining work is the hard cutoff from the old
default template and runner-owned completion behavior.

## Operator Constraints

- Do not create new test files. The operator has explicitly rejected tests for this repo.
- Use command-based verification instead: ruff, import/compile checks, schema validation, and manual smoke commands.
- Preserve generic orchestrator workflow support for existing templates.
- Do not make the runner call `gh pr merge` for actor-driven `change-delivery`.
- Do not make Python perform final post-merge label cleanup for actor-driven `change-delivery`; implementer land mode owns that and Python verifies it.
- Keep labels plain: `backlog`, `todo`, `in-progress`, `review`, `rework`, `merging`, `done`.

## Existing Code Boundaries

The implementation should keep these mental model boundaries:

- `packages/core/src/sprints/core/`: load and validate workflow contracts.
- `packages/core/src/sprints/engine/`: durable leases, retries, sessions, work records, journals.
- `packages/core/src/sprints/workflows/`: lane routing, actor dispatch, transitions, state compaction, workflow-state persistence.
- `packages/core/src/sprints/trackers/`: GitHub issue/PR/comment/check mechanics behind tracker and code-host clients.
- `packages/core/src/sprints/runtimes/`: runtime-specific turn execution.
- `packages/core/src/sprints/skills/`: reusable actor instructions.

## New Runtime Shape

Actor-driven `change-delivery` should run this state machine:

```text
todo
  -> in-progress
      -> implementer(mode=implement)
      -> review
          -> reviewer(mode=review), optional once per attempt
          -> wait for human/bot/reviewer result
          -> rework if required changes exist
          -> merging if merge authority exists and reviewer is finished
      -> rework
          -> implementer(mode=rework)
          -> review
      -> merging
          -> implementer(mode=land)
          -> done after Python verifies merged PR and labels
```

Conflict priority in Review:

```text
required changes > reviewer still running > merge signal > approval
```

## Task 1: Make Actor-Driven Config A First-Class Contract

Files:

- `packages/core/src/sprints/core/config.py`
- `packages/core/src/sprints/core/contracts.py`
- `packages/core/src/sprints/core/validation.py`
- `packages/core/src/sprints/workflows/schema.yaml`
- `packages/core/src/sprints/workflows/inspection.py`
- `packages/core/src/sprints/workflows/templates/change-delivery.md`

Steps:

- [ ] Add a typed orchestration config shape with at least:

  ```python
  @dataclass(frozen=True)
  class OrchestrationConfig:
      mode: Literal["orchestrator", "actor-driven"] = "orchestrator"
      actor: str | None = None
  ```

- [ ] Keep `WorkflowConfig.orchestrator_actor` available for orchestrator-driven workflows, but make it optional or derived from `orchestration.actor` only when `mode == "orchestrator"`.
- [ ] Update config loading so old contracts with:

  ```yaml
  orchestrator:
    actor: orchestrator
  ```

  still normalize to `orchestration.mode == "orchestrator"`.

- [ ] Add config helper properties:

  ```python
  def is_actor_driven(self) -> bool: ...
  def requires_orchestrator_actor(self) -> bool: ...
  ```

- [ ] Update `validate_references()` so `orchestrator_actor` is required only for orchestrator-driven `False`.
- [ ] Update `schema.yaml` so `orchestrator` is no longer globally required when `orchestration.mode: actor-driven`.
- [ ] Update policy parsing so actor-driven workflows may use:

  ```text
  # Workflow Policy
  # Actor: implementer
  # Actor: reviewer
  ```

  without requiring `# Orchestrator Policy`.

- [ ] Keep `# Orchestrator Policy` parsing for existing templates.
- [ ] Store workflow policy text separately from orchestrator policy text. A small shape is enough:

  ```python
  @dataclass(frozen=True)
  class WorkflowPolicy:
      workflow: str | None
      orchestrator: str | None
      actors: dict[str, ActorPolicy]
  ```

- [ ] Update inspection/status code so it describes actor-driven workflow contracts without showing a missing orchestrator as an error.
- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/core packages/core/src/sprints/workflows
  uv run ruff check packages/core/src/sprints/core packages/core/src/sprints/workflows
  ```

Commit target:

```text
workflow: support actor-driven contract mode
```

## Task 2: Add Label-Backed Board State Mechanics

Files:

- `packages/core/src/sprints/workflows/board_state.py` (new)
- `packages/core/src/sprints/workflows/lane_state.py`
- `packages/core/src/sprints/workflows/intake.py`
- `packages/core/src/sprints/trackers/__init__.py`
- `packages/core/src/sprints/trackers/github.py`

Steps:

- [ ] Create `board_state.py` for label-backed workflow state. It should own:

  ```python
  class BoardState(str, Enum):
      BACKLOG = "backlog"
      TODO = "todo"
      IN_PROGRESS = "in-progress"
      REVIEW = "review"
      REWORK = "rework"
      MERGING = "merging"
      DONE = "done"
  ```

- [ ] Add helpers:

  ```python
  def state_labels(config: WorkflowConfig) -> dict[str, str]: ...
  def state_from_labels(labels: Iterable[str], config: WorkflowConfig) -> str | None: ...
  def non_state_labels(labels: Iterable[str], config: WorkflowConfig) -> list[str]: ...
  def desired_state_mutation(current_labels, target_state, config) -> LabelMutation: ...
  ```

- [ ] Enforce exclusive state labels when Python routes state. For example, moving to Review removes `todo`, `in-progress`, `rework`, `merging`, `done` and adds `review`.
- [ ] Add tracker protocol support for replacing state labels atomically from the workflow perspective:

  ```python
  def set_issue_state_label(issue_id: str, *, add: str, remove: Sequence[str]) -> TrackerResult: ...
  ```

  It can use existing `add_labels()` and `remove_labels()` internally for GitHub.

- [ ] Keep transient label failures retryable through existing retry/effect machinery. Do not immediately create `operator_attention` for one failed label mutation.
- [ ] Update lane metadata with refreshed board state:

  ```json
  {
    "board_state": "review",
    "board_state_source": "labels",
    "state_labels": ["review"]
  }
  ```

- [ ] Update intake so eligible lanes come from configured `todo` state, not the old `active` label model.
- [ ] Keep the old intake keys tolerated only for non-actor-driven workflows if still needed by older templates.
- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/workflows packages/core/src/sprints/trackers
  uv run ruff check packages/core/src/sprints/workflows packages/core/src/sprints/trackers
  ```

Commit target:

```text
workflow: route lanes from label board state
```

## Task 3: Add Sprints Workpad Comment Support

Files:

- `packages/core/src/sprints/workflows/workpad.py` (new)
- `packages/core/src/sprints/workflows/intake.py`
- `packages/core/src/sprints/workflows/reconcile.py`
- `packages/core/src/sprints/trackers/__init__.py`
- `packages/core/src/sprints/trackers/github.py`

Steps:

- [ ] Create `workpad.py` with one marker and small rendering helpers:

  ```python
  WORKPAD_MARKER = "<!-- sprints-workpad -->"

  def render_workpad(lane: Mapping[str, Any]) -> str: ...
  def find_workpad_comment(comments: Sequence[IssueComment]) -> IssueComment | None: ...
  def ensure_workpad(tracker, lane, state) -> WorkpadResult: ...
  ```

- [ ] Add tracker protocol methods for comments:

  ```python
  def list_issue_comments(issue_id: str) -> list[IssueComment]: ...
  def create_issue_comment(issue_id: str, body: str) -> IssueComment: ...
  def update_issue_comment(comment_id: str, body: str) -> IssueComment: ...
  ```

- [ ] Implement GitHub comments using `gh api`:

  ```text
  GET /repos/{owner}/{repo}/issues/{number}/comments --paginate
  POST /repos/{owner}/{repo}/issues/{number}/comments
  PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}
  ```

- [ ] Ensure workpad creation happens after lane claim and before implementer dispatch.
- [ ] Store workpad metadata on lane:

  ```json
  {
    "workpad": {
      "comment_id": "...",
      "url": "...",
      "last_updated_at": "..."
    }
  }
  ```

- [ ] Make workpad failures retryable. Do not dispatch implementer if the workpad cannot be created and the failure is transient.
- [ ] Keep workpad content compact: lane ID, attempt, board state, branch, PR, last actor result, next expected state, blocker/retry summary.
- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/workflows packages/core/src/sprints/trackers
  uv run ruff check packages/core/src/sprints/workflows packages/core/src/sprints/trackers
  ```

Commit target:

```text
workflow: add durable workpad comments
```

## Task 4: Add Actor Modes To Dispatch And Prompt Variables

Files:

- `packages/core/src/sprints/workflows/dispatch.py`
- `packages/core/src/sprints/workflows/variables.py`
- `packages/core/src/sprints/workflows/prompt_context.py`
- `packages/core/src/sprints/workflows/sessions.py`
- `packages/core/src/sprints/workflows/templates/change-delivery.md`

Steps:

- [ ] Add mode as an explicit dispatch input:

  ```python
  actor_inputs = {
      "mode": "implement" | "rework" | "land" | "review",
      "board_state": "...",
      "review_signals": {...},
      "workpad": {...},
      "merge_signal": {...}
  }
  ```

- [ ] Ensure runtime sessions remain lane + actor + stage scoped, and include mode in runtime metadata for diagnostics.
- [ ] Decide whether session resume should include mode:
  - Resume same actor on same lane/stage if it is a continuation.
  - Start a fresh session when switching implementer from `implement` to `rework` or `land` unless the runtime benefits from continuity and the prompt clearly scopes the mode.
  - Do not resume reviewer context into implementer or implementer context into reviewer.
- [ ] Update actor prompt variables to include compact lane state only:

  ```text
  workflow: compact workflow context
  lane: compact active lane
  mode: actor mode
  issue: issue facts
  pull_request: PR facts
  review_signals: human/bot/reviewer/check signals
  workpad: workpad metadata and compact content
  ```

- [ ] Keep full audit/session history out of actor prompts.
- [ ] Add land skill to implementer in the bundled `change-delivery` template:

  ```yaml
  skills: [pull, debug, commit, push, land]
  ```

- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/workflows
  uv run ruff check packages/core/src/sprints/workflows
  ```

Commit target:

```text
workflow: dispatch explicit actor modes
```

## Task 5: Add Actor-Driven Tick Routing

Files:

- `packages/core/src/sprints/workflows/actor_driven.py` (new)
- `packages/core/src/sprints/workflows/ticks.py`
- `packages/core/src/sprints/workflows/reconcile.py`
- `packages/core/src/sprints/workflows/intake.py`
- `packages/core/src/sprints/workflows/tick_journal.py`
- `packages/core/src/sprints/workflows/status.py`

Steps:

- [ ] Create `actor_driven.py` as the deterministic router for actor-driven workflows. This module should own the routing mental model, not low-level GitHub or runtime mechanics.
- [ ] Add a branch in `tick_locked()`:

  ```python
  if config.is_actor_driven():
      return tick_actor_driven(...)
  return tick_orchestrator_driven(...)
  ```

- [ ] Keep old orchestrator tick logic intact, but rename helper boundaries if needed so the split is obvious.
- [ ] Actor-driven tick must:
  - [ ] Load config, policy, lane state.
  - [ ] Refresh issues, labels, PRs, reviews, checks, comments, runtime sessions.
  - [ ] Reconcile stale/interrupted actor sessions.
  - [ ] Claim Todo lanes if capacity allows.
  - [ ] Ensure `In Progress` state and workpad before implementer dispatch.
  - [ ] Route each active lane by board state.
  - [ ] Dispatch at most one actor per lane.
  - [ ] Respect actor concurrency limits.
  - [ ] Schedule retries for transient mechanics failures.
  - [ ] Verify Done lanes and release engine leases.
  - [ ] Persist lane state and tick journal even when a later step fails.
- [ ] Add routing table behavior:

  ```text
  backlog -> no-op or release if already claimed and non-active
  todo -> claim, set in-progress, ensure workpad, dispatch implementer implement
  in-progress -> dispatch implementer implement if lane is idle
  review -> run shared review routing
  rework -> dispatch implementer rework if lane is idle
  merging -> dispatch implementer land if lane is idle
  done -> verify completion and release
  ```

- [ ] Make normal Review waiting a first-class lane status, not `operator_attention`.
- [ ] Record routing decisions in the tick journal with compact, human-readable reasons.
- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/workflows
  uv run ruff check packages/core/src/sprints/workflows
  ```

Commit target:

```text
workflow: route actor-driven change delivery ticks
```

## Task 6: Update Actor Output Contracts And Transitions

Files:

- `packages/core/src/sprints/workflows/transitions.py`
- `packages/core/src/sprints/workflows/actor_contracts.py` (new, optional if transitions gets too large)
- `packages/core/src/sprints/workflows/notifications.py`
- `packages/core/src/sprints/workflows/retries.py`
- `packages/core/src/sprints/workflows/templates/change-delivery.md`

Steps:

- [ ] Split actor output validation by actor and mode:

  ```python
  validate_implementer_output(mode="implement" | "rework", output)
  validate_reviewer_output(output)
  validate_land_output(output)
  ```

- [ ] For implement/rework `status: done`, require:
  - [ ] branch
  - [ ] PR URL
  - [ ] PR number
  - [ ] non-empty verification evidence
- [ ] On valid implement/rework completion:
  - [ ] Store actor output compactly on lane.
  - [ ] Move board state to `review`.
  - [ ] Mark lane waiting for shared review.
  - [ ] Increment or stamp review attempt metadata.
- [ ] For reviewer `changes_requested`, require non-empty `required_fixes`.
- [ ] On reviewer `changes_requested`:
  - [ ] Post or store review findings as configured.
  - [ ] Move board state to `rework`.
  - [ ] Dispatch implementer in rework mode on a later tick.
- [ ] On reviewer `approved`:
  - [ ] Store approval.
  - [ ] Keep lane in Review unless merge authority is already present and reviewer is finished.
- [ ] For land output:
  - [ ] Accept `merged`, `waiting`, `blocked`, `failed`.
  - [ ] `waiting` means stay in Merging and schedule retry/poll, not operator attention.
  - [ ] `merged` requires runner refresh and verification before lane release.
- [ ] Keep `blocked` and `failed` paths engine-retry-first when recoverable, operator-attention only after policy exhaustion or clear non-recoverable blocker.
- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/workflows
  uv run ruff check packages/core/src/sprints/workflows
  ```

Commit target:

```text
workflow: validate actor-driven mode outputs
```

## Task 7: Add Shared Review Reconciliation

Files:

- `packages/core/src/sprints/workflows/review_state.py` (new)
- `packages/core/src/sprints/workflows/reconcile.py`
- `packages/core/src/sprints/workflows/actor_driven.py`
- `packages/core/src/sprints/trackers/__init__.py`
- `packages/core/src/sprints/trackers/github.py`

Steps:

- [ ] Create a compact `ReviewSignals` model:

  ```python
  @dataclass(frozen=True)
  class ReviewSignals:
      required_changes: list[ReviewFinding]
      approvals: list[ReviewApproval]
      checks: list[CheckStatus]
      comments: list[ReviewComment]
      merge_signal_seen: bool
      reviewer_actor_running: bool
      reviewer_actor_result: Mapping[str, Any] | None
  ```

- [ ] Pull review facts from the code host where available:
  - [ ] PR review decision
  - [ ] PR review states
  - [ ] check status
  - [ ] review comments
  - [ ] issue comments
  - [ ] unresolved review threads if available through `gh api`
- [ ] Keep first automatic classification conservative:
  - [ ] GitHub review state `CHANGES_REQUESTED` means required changes.
  - [ ] Reviewer actor `changes_requested` means required changes.
  - [ ] Explicit `rework` label means required changes.
  - [ ] Free-form comments are passed to actor context but are not blindly classified as required changes unless the GitHub review state says so.
- [ ] Implement Review conflict priority:

  ```text
  required changes > reviewer still running > merge signal > approval
  ```

- [ ] If merge signal appears while reviewer is running:
  - [ ] Do not dispatch implementer land mode.
  - [ ] Store lane phase `review_waiting_for_reviewer`.
  - [ ] Keep status visible in status/watch output.
- [ ] If required changes exist:
  - [ ] Move state to `rework`.
  - [ ] Store compact required fixes for implementer rework prompt.
- [ ] If merge signal exists and reviewer is finished:
  - [ ] Move or accept state `merging`.
  - [ ] Dispatch implementer land mode on the next route pass.
- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/workflows packages/core/src/sprints/trackers
  uv run ruff check packages/core/src/sprints/workflows packages/core/src/sprints/trackers
  ```

Commit target:

```text
workflow: reconcile shared review state
```

## Task 8: Move Actor-Driven Landing To Implementer And Make Python Verify-Only

Files:

- `packages/core/src/sprints/workflows/teardown.py`
- `packages/core/src/sprints/workflows/actor_driven.py`
- `packages/core/src/sprints/workflows/transitions.py`
- `packages/core/src/sprints/skills/land/SKILL.md`
- `packages/core/src/sprints/workflows/templates/change-delivery.md`

Steps:

- [ ] Add a clear helper:

  ```python
  def verify_actor_driven_completion(config, lane, refreshed_issue, refreshed_pr) -> CompletionVerification: ...
  ```

- [ ] For actor-driven `change-delivery`, do not call existing runner-owned auto-merge code.
- [ ] For actor-driven `change-delivery`, do not call runner-owned final label cleanup code.
- [ ] Keep old `teardown.py` behavior available for orchestrator-driven workflows that explicitly configure runner-owned automerge/cleanup.
- [ ] Update land skill to instruct actor to:
  - [ ] Confirm merge authority from workflow input.
  - [ ] Check PR readiness.
  - [ ] Use the land procedure, including merge.
  - [ ] Remove `in-progress`, `review`, `rework`, `merging`.
  - [ ] Add `done`.
  - [ ] Update workpad.
  - [ ] Return structured land JSON.
- [ ] Python verification must refresh GitHub after land output and require:
  - [ ] PR merged.
  - [ ] `done` label present.
  - [ ] active workflow labels absent.
  - [ ] no active actor run for the lane.
- [ ] If PR merged but labels are not clean:
  - [ ] Retry implementer land mode with cleanup-only context if retry budget allows.
  - [ ] Only use operator attention after retry exhaustion or permission failure.
- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/workflows
  uv run ruff check packages/core/src/sprints/workflows packages/core/src/sprints/skills
  ```

Commit target:

```text
workflow: make actor-driven landing implementer-owned
```

## Task 9: Rewrite The Bundled Change Delivery Template

Files:

- `packages/core/src/sprints/workflows/templates/change-delivery.md`
- `packages/core/src/sprints/core/bootstrap.py`
- `packages/core/src/sprints/core/init_wizard.py`
- `README.md`
- `docs/architecture.md`
- `docs/workflows/workflow-contract.md` if present

Steps:

- [x] Update template front matter:

  ```yaml
  workflow: change-delivery
  schema-version: 1

  orchestration:
    mode: actor-driven

  tracker:
    kind: github
    github_slug: owner/repo
    state-source:
      kind: labels
      labels:
        backlog: backlog
        todo: todo
        in-progress: in-progress
        review: review
        rework: rework
        merging: merging
        done: done

  review:
    mode: shared
    actor:
      enabled: true
      name: reviewer
      run-on-entry: true
      rerun-on-new-attempt: true
    merge-signal:
      state: merging
      require-reviewer-finished: true

  completion:
    owner: implementer
    mode: land
    skill: land
    cleanup:
      remove_labels:
        - in-progress
        - review
        - rework
        - merging
      add_labels:
        - done

  actors:
    implementer:
      runtime: codex
      skills: [pull, debug, commit, push, land]
    reviewer:
      runtime: codex
      skills: [review]
  ```

- [x] Replace `# Orchestrator Policy` with `# Workflow Policy`.
- [x] Implementer policy must include:
  - [x] implement mode responsibilities
  - [x] rework mode responsibilities
  - [x] land mode responsibilities
  - [x] required JSON output for each mode
  - [x] no interactive escalation
  - [x] blocked output shape for auth/permissions/tooling failures
- [x] Reviewer policy must include:
  - [x] review scope
  - [x] approval vs changes requested
  - [x] concrete required fixes
  - [x] no merge or label cleanup authority
- [x] Workflow policy must document:
  - [x] board states
  - [x] conflict priority
  - [x] merge authority
  - [x] runner verification
  - [x] operator attention rules
- [x] Update bootstrap/init wizard so default bootstrapped `WORKFLOW.md` is actor-driven `change-delivery`.
- [ ] Verification:

  ```powershell
  uv run sprints bootstrap --help
  uv run python -m compileall packages/core/src/sprints
  uv run ruff check packages/core/src/sprints
  ```

Commit target:

```text
workflow: ship actor-driven change delivery template
```

## Task 10: Update Status, Watch, And Operator Visibility

Files:

- `packages/core/src/sprints/workflows/status.py`
- `packages/core/src/sprints/observe/sources.py`
- `packages/core/src/sprints/observe/watch.py`
- `packages/core/src/sprints/app/commands.py`
- `packages/core/src/sprints/engine/reports.py`
- `docs/architecture.md`
- `README.md`

Steps:

- [ ] Status output should show actor-driven facts:
  - [ ] lane ID
  - [ ] board state
  - [ ] actor mode
  - [ ] running actor
  - [ ] PR URL/number
  - [ ] merge signal seen
  - [ ] reviewer actor running/done
  - [ ] required changes summary
  - [ ] retry due time and reason
  - [ ] operator attention only when truly needed
- [ ] Watch output should read engine-first lane projections where possible, not stale or missing tables.
- [ ] Add explicit Review wait phases:

  ```text
  waiting_for_review
  review_waiting_for_reviewer
  waiting_for_merge_signal
  waiting_for_land_retry
  ```

- [ ] Update docs so users understand GitHub Project board automation applies labels and Sprints reads labels.
- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/observe packages/core/src/sprints/app packages/core/src/sprints/workflows
  uv run ruff check packages/core/src/sprints/observe packages/core/src/sprints/app packages/core/src/sprints/workflows
  ```

Commit target:

```text
workflow: expose actor-driven lane status
```

## Task 11: Add Recovery And Idempotency Guardrails For The New Flow

Files:

- `packages/core/src/sprints/workflows/effects.py`
- `packages/core/src/sprints/workflows/tick_journal.py`
- `packages/core/src/sprints/workflows/retries.py`
- `packages/core/src/sprints/workflows/sessions.py`
- `packages/core/src/sprints/workflows/actor_driven.py`
- `packages/core/src/sprints/engine/retries.py`

Steps:

- [ ] Every side effect should have a stable idempotency key:
  - [ ] set board state
  - [ ] create/update workpad
  - [ ] dispatch actor
  - [ ] post reviewer output
  - [ ] retry land cleanup
  - [ ] release lane
- [ ] Persist the lane ledger immediately after claim and after each successful mechanical side effect.
- [ ] Preserve recovery journal entries before runtime dispatch:

  ```json
  {
    "lane_id": "github#20",
    "actor": "implementer",
    "mode": "rework",
    "dispatch_id": "...",
    "idempotency_key": "...",
    "status": "dispatching"
  }
  ```

- [ ] On daemon restart, reconcile dispatch journal and runtime sessions before deciding a lane is idle.
- [ ] Make retry wakeup ownership clear:
  - [ ] engine owns due time/backoff/max attempts
  - [ ] workflow owns classification/reason and next desired route
  - [ ] status shows both
- [ ] Verification:

  ```powershell
  uv run python -m compileall packages/core/src/sprints/workflows packages/core/src/sprints/engine
  uv run ruff check packages/core/src/sprints/workflows packages/core/src/sprints/engine
  ```

Commit target:

```text
workflow: harden actor-driven recovery
```

## Task 12: Final Manual Smoke Checklist

Files:

- no new product files expected unless smoke reveals a fix

Steps:

- [ ] Run full static verification:

  ```powershell
  uv run ruff check packages
  uv run python -m compileall packages
  ```

- [ ] Bootstrap a scratch repo workflow and inspect generated `WORKFLOW.md`:

  ```powershell
  uv run sprints bootstrap --help
  ```

- [ ] In a real GitHub smoke repo:
  - [ ] Create 2 open issues.
  - [ ] Label one `todo`.
  - [ ] Run daemon/tick with concurrency 1.
  - [ ] Confirm only one lane is claimed.
  - [ ] Confirm issue moves to `in-progress`.
  - [ ] Confirm workpad comment is created.
  - [ ] Confirm implementer receives mode `implement`.
  - [ ] Confirm valid implementer output moves state to `review`.
  - [ ] Confirm reviewer runs once if enabled.
  - [ ] Move issue/card to `rework`; confirm implementer receives mode `rework`.
  - [ ] Move issue/card to `merging` while reviewer is running; confirm land waits.
  - [ ] Move issue/card to `merging` after reviewer is done; confirm implementer receives mode `land`.
  - [ ] Confirm runner does not call merge directly.
  - [ ] Confirm runner verifies merged PR and labels before release.
  - [ ] Confirm second issue is picked only after capacity is free.
- [ ] Verify status/watch output during:
  - [ ] In Progress
  - [ ] Review waiting
  - [ ] Rework
  - [ ] Merging waiting
  - [ ] Done
  - [ ] Retry due
  - [ ] Operator attention
- [ ] Final commit if smoke fixes were needed.

Commit target:

```text
workflow: verify actor-driven delivery smoke
```

## Implementation Order

Use this order to avoid breaking the repo midway:

1. Config and contract support.
2. Label-backed board state.
3. Workpad mechanics.
4. Actor modes and prompt variables.
5. Actor-driven tick routing.
6. Actor output contracts and transitions.
7. Shared Review reconciliation.
8. Implementer-owned landing and runner verification.
9. Template rewrite.
10. Status/watch/docs.
11. Recovery and idempotency hardening.
12. Manual smoke.

## Design Review Before Coding

Before implementing, verify these decisions still hold:

- Actor-driven mode is specific to `change-delivery` first.
- Other workflows can keep orchestrator-agent routing.
- GitHub Project board is not read directly in first version; labels are the machine contract.
- Human review waiting is normal state, not `operator_attention`.
- Implementer owns land mode and cleanup.
- Python verifies completion and releases the lane.
- Runner never calls `gh pr merge` in actor-driven `change-delivery`.

## Expected End State

After implementation:

- A fresh bootstrap creates actor-driven `change-delivery` by default.
- The default workflow has no orchestrator actor.
- A `todo` issue can be claimed, moved to `in-progress`, implemented, reviewed, reworked, merged, cleaned, and released.
- The implementer has enough policy and skills to complete the delivery loop.
- The reviewer participates in Review without owning merge authority.
- Humans control merge authority through the `merging` state label.
- Engine durability stays Python-owned and visible through status/watch.
