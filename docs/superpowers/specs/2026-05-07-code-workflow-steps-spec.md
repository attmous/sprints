# Code Workflow Step Model

Date: 2026-05-07

## Problem

The current `code` workflow is moving in the right direction, but the boundary is
still blurry:

- the prompt talks about tracker labels directly instead of a normalized workflow
  position;
- the runtime still exposes old `mode` language from `change-delivery`;
- `workspace.root` previously looked like a lane checkout path even though the
  implementation uses git worktrees;
- review and rework are over-modeled compared to the desired single-coder flow.

The goal is a smaller and clearer workflow contract where the runner owns lane
mechanics and the coder owns work inside one lane.

## Target Model

`code` is a single-actor workflow.

The normalized primitive is `step`.

```text
step = durable lane position
step = actor prompt entrypoint
step = tracker label projection
```

The public flow is:

```text
intake -> code -> review -> merge -> done
             ^       |
             |-------|
```

There is no separate `rework` step. Review feedback moves the lane from
`review` back to `code`. When the coder is dispatched again, the prompt uses the
same start/continue pattern inspired by Symphony: inspect current issue state,
read the workpad, sweep PR feedback, then continue or fix.

## Responsibilities

Runner/Python owns:

- tracker discovery and lane claim;
- per-lane lease and duplicate dispatch protection;
- git worktree creation/reuse;
- runtime dispatch and session recording;
- durable retries, tick journals, audit, and status;
- step detection from tracker labels;
- step transitions forward and backward;
- release when the lane reaches `done`.

Coder owns:

- work inside exactly one lane worktree;
- issue understanding, workpad maintenance, implementation, validation, commit,
  push, PR creation/update;
- PR feedback sweep when a PR exists;
- landing only when dispatched for `step=merge`;
- structured JSON output.

The coder must not claim other issues, dispatch other actors, mutate concurrency,
or manage global workflow state.

## Steps

The `code` workflow uses canonical GitHub labels as step state:

| Step | Label | Runner behavior | Coder behavior |
| --- | --- | --- | --- |
| intake | `todo` | claim eligible issue and move to `code` | not dispatched |
| code | `code` | dispatch coder with `step=code` | start/continue implementation or fix PR feedback |
| review | `review` | idle and reconcile PR/check/review signals | not normally dispatched |
| merge | `merge` | dispatch coder with `step=merge` | open/follow land skill |
| done | `done` | release lane | not dispatched |
| blocked | `blocked` | hold or surface operator attention | not dispatched unless manually retried |

`intake` is not a long-lived lane step. It is the pre-claim label used to pick
new work.

## Step Transitions

Runner transitions are deterministic:

```text
todo issue claimed       -> code
code output done + PR    -> review
review needs changes     -> code
review merge signal      -> merge
merge output done/merged -> done
done verified            -> release
blocked                  -> hold
```

The runner may also hold instead of moving when required evidence is missing.
Examples:

- coder returns `done` without a PR;
- coder returns `done` without validation evidence;
- merge step returns `waiting`;
- tracker/GitHub state cannot be reconciled.

Repeated failures or unsafe ambiguity become `operator_attention`.

## Workflow Contract Shape

The front matter should contain only operator-tunable mechanics.

Example:

```yaml
---
workflow: code
schema-version: 1
template: code

tracker:
  kind: github
  github_slug: owner/repo

code-host:
  kind: github
  github_slug: owner/repo

polling:
  interval_ms: 5000

intake:
  entry:
    states: [open]
    include_labels: [todo]
    exclude_labels: [blocked, done]
  claim:
    remove_labels: [todo]
    add_labels: [code]
    branch: codex/issue-{number}-{slug}

workspace:
  root: .sprints/workspace/worktrees/{{ workflow }}

workpad:
  owner: actor

concurrency:
  max-lanes: 1
  per-lane-lock: true

runtime:
  kind: codex-app-server
  mode: external
  endpoint: ws://127.0.0.1:4500
  ephemeral: false
  keep_alive: true
  model: gpt-5.5
  effort: high
  approval_policy: never
  thread_sandbox: workspace-write
  turn_sandbox_policy:
    type: workspaceWrite

storage:
  state: .sprints/code-state.json
  audit-log: .sprints/code-audit.jsonl
---
```

Do not add `actors`, `stages`, `gates`, `actions`, `routing`, `modes`, or a
label alias table to the `code` workflow contract.

The config loader may still infer an internal actor and internal dispatch stage
because runtime code needs those objects. They are implementation details, not
operator-facing workflow concepts.

## Actor Prompt Shape

The actor input should expose `Step`, not `Mode` or `Board state`.

Example:

```md
Issue:
{{ issue }}

Lane:
{{ lane }}

Step:
{{ step }}

Workspace:
{{ workspace }}

Pull request:
{{ pull_request }}

Review feedback:
{{ review_feedback }}

Retry:
{{ retry }}
```

Prompt policy should define:

- `## Step: code`
- `## Step: review`
- `## Step: merge`
- `## Step: done`
- `## Step: blocked`

Only `code` and `merge` normally dispatch the coder.

## Output Contract

Coder returns JSON only.

For `step=code`:

```json
{
  "status": "done|waiting|blocked|failed",
  "step": "code",
  "summary": "what happened",
  "branch": "codex/issue-20-short-name",
  "pull_request": {
    "url": "https://github.com/owner/repo/pull/123",
    "number": 123,
    "state": "open",
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
  "blockers": [],
  "artifacts": {}
}
```

For `step=merge`:

```json
{
  "status": "done|waiting|blocked|failed",
  "step": "merge",
  "summary": "landing summary",
  "pull_request": {
    "url": "https://github.com/owner/repo/pull/123",
    "number": 123,
    "state": "merged",
    "merged": true,
    "merge_commit": "sha if known"
  },
  "cleanup": {
    "removed_labels": ["code", "review", "merge"],
    "added_labels": ["done"]
  },
  "blockers": [],
  "artifacts": {}
}
```

The runner validates output by step.

## Worktrees

The lane workspace is a git worktree.

`workspace.root` is a base directory. Sprints appends a safe lane segment.

Example:

```yaml
workspace:
  root: .sprints/workspace/worktrees/{{ workflow }}
```

For lane `github#20`, the actual worktree path becomes:

```text
<repo>/.sprints/workspace/worktrees/code/github20
```

The codex app-server runtime receives this worktree as `cwd` and, for
`workspace-write`, as the writable sandbox root.

## Prompt Variable Changes

Replace old actor-facing variables:

- `mode`
- `board_state`

with:

- `step`

Compatibility can exist internally during migration, but `code.md` should use
only `{{ step }}`.

The runner should derive `step` from the lane/tracker label projection and pass
it into actor dispatch inputs.

## Non-Goals

This spec does not implement the future `review` workflow.

This spec does not add a human/AI reviewer actor to `code`.

This spec does not support custom label aliases for `code`. The canonical labels
are part of the workflow policy for now.

This spec does not remove legacy orchestrator-mode support from older workflows.

## Acceptance Criteria

- `code.md` uses repo-local worktree base path.
- `code.md` describes steps, not modes or stages.
- `code.md` uses `todo`, `code`, `review`, `merge`, `done`, and `blocked`.
- actor prompt variables include `step`.
- runtime dispatch records step in prompt metadata.
- code route logic moves lanes forward/backward using canonical step labels.
- review feedback routes `review -> code`; there is no `rework` step.
- merge authority routes `review -> merge`.
- merged output routes `merge -> done`.
- schema validation passes for bundled templates.
- Python compile check passes for touched workflow modules.
