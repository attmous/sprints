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
  hooks:
    after_create: |
      git fetch origin
    before_remove: |
      git status --short

workpad:
  owner: actor

concurrency:
  max-lanes: 1
  per-lane-lock: true

limits:
  max_turns: 20

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

# Actor: coder

Bundled skills available to this actor: `pull`, `debug`, `commit`, `push`, `land`.

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

After a successful merge, explicitly close the source issue and verify it is
closed. Do not rely on GitHub auto-close from PR body text. Return `done` only
when the PR is merged, the source issue is closed, and cleanup evidence includes
`cleanup.issue_state: "closed"`.

## Step: done

Terminal. Do not perform actor work.

## Step: blocked

Do not code unless the blocker has clearly been resolved. Return `blocked` with
the remaining unblock requirement, or `waiting` if the lane should remain held.

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
    "added_labels": [],
    "issue_state": "closed"
  },
  "blockers": [],
  "artifacts": {}
}
