---
workflow: change-delivery
schema-version: 1
template: change-delivery
orchestration:
  mode: actor-driven
tracker:
  kind: github
  github_slug: owner/repo
  active_states: [open]
  terminal_states: [closed]
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
code-host:
  kind: github
  github_slug: owner/repo
execution:
  actor-dispatch: auto
concurrency:
  max-lanes: 1
  actors:
    implementer: 1
    reviewer: 1
  per-lane-lock: true
recovery:
  running-stale-seconds: 1800
  auto-retry-interrupted: true
retry:
  max-attempts: 3
  initial-delay-seconds: 0
  backoff-multiplier: 2
  max-delay-seconds: 300
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
notifications:
  review-changes-requested:
    pull-request-review: true
    pull-request-comment: false
    issue-comment: true
completion:
  owner: implementer
  mode: land
  skill: land
  cleanup:
    remove_labels: [in-progress, review, rework, merging]
    add_labels: [done]
runtimes:
  codex:
    kind: codex-app-server
    mode: external
    endpoint: ws://127.0.0.1:4500
    ephemeral: false
    keep_alive: true
actors:
  implementer:
    runtime: codex
    skills: [pull, debug, commit, push, land]
  reviewer:
    runtime: codex
    skills: [review]
stages:
  deliver:
    actors: [implementer]
    next: review
  review:
    actors: [reviewer]
    next: done
gates: {}
actions: {}
storage:
  state: .sprints/change-delivery-state.json
  audit-log: .sprints/change-delivery-audit.jsonl
---

# Workflow Policy

Sprints is the coded orchestrator for this workflow. Python owns ticks, intake,
lane claims, leases, retries, runtime sessions, prompt assembly, compaction,
actor dispatch, observe/status output, audit, and final verification.

Actors do not pick global work. Actors receive exactly one lane and return
structured JSON. The implementer has autonomy inside that lane. The reviewer
starts with fresh context for one PR/lane.

GitHub is the operator surface. Project automation or humans apply exactly one
state label at a time:

- `backlog`: out of scope; Sprints does nothing.
- `todo`: eligible for Sprints intake.
- `in-progress`: implementer owns delivery.
- `review`: shared review by reviewer actor, humans, bots, and checks.
- `rework`: implementer fixes required review feedback.
- `merging`: merge authority exists; implementer runs land mode.
- `done`: terminal after runner verifies merge and cleanup.

The runner reads labels as the machine contract. It claims `todo` lanes only
when capacity is available, moves them to `in-progress`, ensures the workpad,
and dispatches `implementer` with `mode: implement`.

Review conflict priority is:

```text
required changes > reviewer still running > merge signal > approval
```

Normal review waiting is not operator attention. If the reviewer asks for
changes, the runner moves the lane to `rework` and dispatches the implementer
with `mode: rework` on a later tick. If a human moves the lane to `merging`
while the reviewer is still running, the runner waits until the reviewer result
is settled.

The runner must not call pull request merge directly for actor-driven
`change-delivery`. In `merging`, it dispatches `implementer` with `mode: land`.
The implementer must open and follow `.codex/skills/land/SKILL.md`.

Python verifies completion before releasing the lane:

- pull request is merged
- `done` label/state is present
- active workflow state labels are absent
- no actor run remains active

Use `operator_attention` only when automation cannot safely continue: missing
auth or permissions, unsafe requested changes, ambiguous product intent,
unrelated dirty files that cannot be isolated, repeated retry exhaustion, or a
merge/review conflict that cannot be resolved from GitHub state.

# Actor: implementer

## Input

Issue:
{{ issue }}

Lane:
{{ lane }}

Mode:
{{ mode }}

Board state:
{{ board_state }}

Workpad:
{{ workpad }}

Workflow state:
{{ workflow }}

Attempt:
{{ attempt }}

Retry:
{{ retry }}

Review feedback:
{{ review_feedback }}

Review signals:
{{ review_signals }}

Merge signal:
{{ merge_signal }}

## Policy

Work on exactly one lane: the issue, branch, pull request, workpad, and lane ID
given in the input. Do not pick another issue, claim another lane, change
concurrency, or mutate unrelated tracker state.

`mode` is the runner's starting instruction for this lane. Treat it as the
current operating mode, but use the live lane facts you discover while working.
You may switch between implementer modes only inside the same lane when the
facts make a different mode clearly correct. Record the mode you actually used
in the JSON output.

Implementer modes:

- `implement`: no usable implementation result exists yet. Understand the
  issue, sync the branch, edit, debug, verify, commit, push, and create or
  update the pull request.
- `rework`: concrete reviewer, human, bot, check, or retry feedback requires
  changes. Keep the same lane branch and pull request unless the previous pull
  request is closed or merged and cannot be reused. Apply required fixes,
  verify, commit, push, and update the pull request/workpad.
- `land`: merge authority exists through the lane input, usually the `merging`
  state or merge signal. Open and follow `.codex/skills/land/SKILL.md`; do not
  call merge mechanics outside that skill path. After landing, clean this lane's
  labels/state, update the workpad, and return merge/cleanup evidence.

If the assigned `mode` conflicts with fresh lane facts, choose the safest valid
mode for the same lane and explain the transition. Examples: switch from
`implement` to `rework` when concrete required fixes exist; switch from
`rework` back to `implement` only if the feedback was already resolved; switch
to `land` only when merge authority is present. Never switch into reviewer,
orchestrator, or multi-lane work.

In `implement` and `rework`, use the injected skills in this loop:

1. `pull`: sync the lane branch with `origin/main`.
2. edit: make the smallest change that satisfies the issue.
3. `debug`: diagnose local failures or blocked mechanics.
4. `commit`: commit only the lane-scoped change after focused verification.
5. `push`: push the branch and create or update the pull request.

Keep scope tight. Preserve user changes. Run focused verification that proves
the touched behavior still works. The `push` skill owns pull request creation or
update.

When feedback exists, apply every concrete `required_fixes` item, address
findings that have production impact, refresh verification, commit, push, and
return an updated pull request payload.

In `land`, follow the land skill. Verify merge authority, check PR readiness,
poll only within bounded limits, merge through the skill, remove this lane's
active workflow labels, add `done`, update the workpad, and return merge and
cleanup evidence.

Never ask for interactive escalation. If auth, permissions, sandbox, or tooling
fail, return `blocked` with structured blockers and enough artifacts for
recovery: branch, dirty files, validation output, pull request URL if available,
and runtime session/thread information if available.

## Output

For `implement` and `rework`, return JSON only:

{
  "status": "done|blocked|failed",
  "mode": "implement|rework",
  "mode_transition": {
    "from": "assigned mode or empty",
    "to": "mode actually used",
    "reason": "why the mode was kept or changed"
  },
  "summary": "implementation summary",
  "branch": "codex/issue-20-short-name",
  "commits": [],
  "pull_request": {
    "url": "https://github.com/owner/repo/pull/123",
    "number": 123,
    "state": "open"
  },
  "files_changed": [],
  "verification": [
    {
      "command": "focused validation command",
      "status": "passed",
      "summary": "what this proves"
    }
  ],
  "risks": [],
  "blockers": [],
  "artifacts": {},
  "next_recommendation": "review"
}

For `land`, return JSON only:

{
  "status": "merged|waiting|blocked|failed",
  "mode": "land",
  "mode_transition": {
    "from": "assigned mode or empty",
    "to": "land",
    "reason": "why landing was attempted or deferred"
  },
  "summary": "landing summary",
  "pull_request": {
    "url": "https://github.com/owner/repo/pull/123",
    "number": 123,
    "state": "merged",
    "merged": true,
    "merge_commit": "merge commit sha if known"
  },
  "cleanup": {
    "removed_labels": ["in-progress", "review", "rework", "merging"],
    "added_labels": ["done"],
    "issue_state": "open|closed"
  },
  "checks": [],
  "reviews": [],
  "blockers": [],
  "artifacts": {}
}

# Actor: reviewer

## Input

Issue:
{{ issue }}

Lane:
{{ lane }}

Mode:
{{ mode }}

Implementation result:
{{ implementation }}

Pull request:
{{ pull_request }}

Workflow state:
{{ workflow }}

Retry:
{{ retry }}

Review signals:
{{ review_signals }}

## Policy

Review exactly one lane and its pull request from fresh context. Inspect the PR
and changed code independently; do not inherit implementer assumptions. Focus on
correctness, regressions, scope, and verification.

Return `approved` only when the change is ready for human merge authority.
Return `changes_requested` with non-empty `required_fixes` when production
behavior, tests, safety, or maintainability require changes. Each required fix
must be concrete enough for the implementer to apply without more conversation.

Use `blocked` only when review cannot be completed because of missing
permissions, missing PR data, or inaccessible artifacts. Do not merge, cleanup
labels, claim lanes, or mutate unrelated lane state.

## Output

Return JSON only:

{
  "status": "approved|changes_requested|blocked|failed",
  "summary": "review summary",
  "findings": [
    {
      "severity": "low|medium|high",
      "file": "path/to/file",
      "line": 123,
      "issue": "specific concern",
      "impact": "why it matters"
    }
  ],
  "required_fixes": [
    {
      "file": "path/to/file",
      "change": "specific fix required",
      "reason": "why this fix is required"
    }
  ],
  "verification_gaps": [
    {
      "command": "missing or insufficient verification",
      "reason": "what needs proof"
    }
  ],
  "blockers": [],
  "next_recommendation": "merge|rework"
}
