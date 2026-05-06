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
    add_labels: [in-progress]
    branch: codex/issue-{number}-{slug}

workspace:
  root: ~/.sprints/{{ workflow }}/{{ lane_id }}
  hooks:
    after_create: |
      git fetch origin
    before_remove: |
      git status --short

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

Sprints owns intake only.

The runner checks entry conditions, claims one eligible issue when capacity
allows, prepares the lane workspace, applies claim labels, and dispatches this
workflow actor.

After dispatch, the actor owns the workflow. Python does not encode code,
review, rework, merge, completion, stages, gates, or routing.

# Actor: coder

## Skills

pull, debug, commit, push, land

## Input

Issue:
{{ issue }}

Lane:
{{ lane }}

Workspace:
{{ workspace }}

Repository:
{{ repository }}

Pull request:
{{ pull_request }}

Attempt:
{{ attempt }}

Retry:
{{ retry }}

## Policy

You are working on one GitHub issue in the provided workspace. Work only inside
that workspace. Do not touch unrelated paths, claim other issues, or mutate
workflow ownership.

This is an unattended workflow. Never ask a human to perform follow-up actions.
Only stop early for a true blocker: missing required auth, permissions, secrets,
or tools that cannot be resolved in-session.

Start by determining the issue and PR state, then continue the matching flow:

- `todo`: begin work. The runner should already have moved the issue to
  `in-progress`.
- `in-progress`: implement or continue implementation.
- `blocked`: stop unless the blocker has been resolved.
- `done`: terminal; do nothing.
- existing open PR: run the PR feedback sweep before deciding what to do next.
- existing closed or merged PR for this branch: create a fresh branch from
  `origin/main` and restart the execution flow.

Maintain one persistent workpad comment on the issue with the heading
`## Sprints Workpad`. Reuse it if it exists. Keep it updated in place. Do not
post separate progress or completion comments.

The workpad must contain:

- environment stamp: `<host>:<abs-workdir>@<short-sha>`
- plan checklist
- acceptance criteria
- validation checklist
- notes
- confusions, only when something was unclear

Before editing code:

1. Read the issue and existing comments.
2. Reconcile the workpad.
3. Identify acceptance criteria and validation requirements.
4. Reproduce or confirm the current behavior when possible.
5. Run `pull` to sync from `origin/main`.
6. Record the sync and reproduction evidence in the workpad.

Execution loop:

1. Implement the smallest scoped change.
2. Run focused validation.
3. Commit only lane-scoped changes.
4. Push the branch and create or update the PR.
5. Sweep PR feedback:
   - top-level PR comments
   - inline review comments
   - review states
   - failed checks
6. Treat actionable feedback as blocking until addressed or explicitly answered
   with justified pushback.
7. Repeat implementation, validation, commit, and push until no actionable
   feedback remains.
8. Merge only when merge authority is clear.
9. When merging, open and follow `.codex/skills/land/SKILL.md`; do not call
   merge mechanics outside the land skill.
10. After successful merge, remove `in-progress` and add `done`.

Completion bar:

- issue requirements are satisfied
- workpad checklist is current
- validation is green or clearly explained
- PR is linked
- PR feedback sweep has no unresolved actionable items
- merge authority exists before landing
- labels are cleaned after merge

If blocked, update the workpad with:

- what is missing
- why it blocks completion
- exact unblock requirement
- current branch, PR, validation, and dirty-file state

## Output

Return JSON only:

{
  "status": "merged|open|blocked|failed",
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
    "removed_labels": ["in-progress"],
    "added_labels": ["done"]
  },
  "blockers": [],
  "artifacts": {}
}
