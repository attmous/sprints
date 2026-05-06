# Actor-Driven Change Delivery Spec

Date: 2026-05-06

## Goal

Change `change-delivery` from an orchestrator-agent-driven workflow into an
actor-driven delivery loop supervised by Python mechanics.

The main product direction is:

```text
Python owns durability, routing, locking, retries, and verification.
Actors own the software delivery work.
```

The workflow should use GitHub-native project movement and labels as the human
control surface. Humans move work through board states. Sprints reads the
machine-readable state signal, dispatches the right actor mode, and persists
every transition.

## Why Change

The current orchestrator actor often acts as a smart JSON router:

```text
implementer done -> advance to review
reviewer approved -> complete
reviewer changes_requested -> retry implementer
```

For `change-delivery`, most of those choices are deterministic once actor
outputs and GitHub state are known. The extra orchestrator LLM call adds prompt
size, latency, failure modes, and another context boundary without giving the
implementer more autonomy.

The new model gives the LLM autonomy where it matters:

- understand the issue
- decide implementation approach
- debug failures
- create and update the pull request
- rework from feedback
- land the pull request using the land skill
- clean up labels/state after landing

Python remains the durable supervisor and verifier.

## Scope

This spec targets the bundled `change-delivery` workflow first.

Other workflow templates may keep the existing orchestrator-agent model until
they are redesigned. The workflow engine should support actor-driven execution
without forcing every workflow to migrate at once.

## Non-Goals

- Do not remove generic orchestrator support from the whole engine in this
  change.
- Do not build direct GitHub Projects API support as the first state source.
- Do not let actors claim lanes, release lanes, change concurrency, or mutate
  durable engine state directly.
- Do not keep actors alive for long human wait periods.
- Do not let the runner call `gh pr merge` or perform final label cleanup in
  the actor-driven `change-delivery` flow.

## Core Model

`change-delivery` has two work stages:

```text
deliver -> review
```

The completion path adds actor modes, not additional workflow stages:

```text
implement mode -> review state -> rework mode -> land mode -> done
```

The implementer actor owns multiple modes:

- `implement`: understand, implement, verify, commit, push, create/update PR
- `rework`: apply required fixes from human, bot, or reviewer feedback
- `land`: follow the land skill, merge when authorized, clean up labels/state

The reviewer actor is one participant in the shared Review state.

The runner dispatches actors by lane state and validates the results.

## Board States

The GitHub Project board should expose the human workflow:

```text
Backlog
Todo
In Progress
Review
Rework
Merging
Done
```

Sprints should not require direct board API integration in the first version.
Instead, board automation applies labels, and Sprints reads labels as the
machine contract.

Recommended machine labels:

```text
backlog
todo
in-progress
review
rework
merging
done
```

The board is the human UI. Labels are the runtime signal.

The state label set is exclusive: one issue should have only one Sprints state
label at a time. Runner-owned state routing may move labels between Todo,
In Progress, Review, Rework, and Merging. Final post-merge cleanup from
Merging to Done is implementer-owned in land mode and runner-verified before
release.

## State Routing

### Backlog

Sprints does nothing.

Backlog work is not eligible for intake. The operator or project workflow must
move it to Todo before Sprints starts.

### Todo

Sprints may claim the lane.

Startup sequence:

1. Claim the lane with engine lease.
2. Move or ensure the issue is in `In Progress`.
3. Ensure the Sprints workpad comment exists.
4. Dispatch implementer in `deliver` mode.

The state update happens before actor work starts so humans can see that the
lane is owned.

### In Progress

The implementer owns delivery.

If a lane is in progress and no actor is running, Python dispatches or resumes
the implementer in `deliver` mode. If a PR already exists for the branch, the
implementer starts by inspecting open PR comments and existing feedback.

When the implementer returns a valid PR and verification evidence, the runner
routes the lane to Review.

### Review

Review is a shared review state, not a human-only wait.

On entry:

1. Dispatch reviewer actor once per review attempt if AI review is enabled.
2. Post AI review output to the PR/issue when enabled.
3. Poll human and bot PR comments, PR review state, checks, and board labels
   through the runner.
4. Route to Rework if required changes exist.
5. Route to Merging only when merge authority appears and the reviewer actor is
   no longer running.

The guardrail is strict:

```text
Human merge signal is not actionable while the reviewer actor is running.
```

If a human moves the ticket to Merging while the reviewer actor is still
running, the lane waits in Review with metadata similar to:

```json
{
  "phase": "review_waiting_for_reviewer",
  "merge_signal_seen": true,
  "reviewer_status": "running"
}
```

Conflict priority:

```text
required changes > reviewer still running > merge signal > approval
```

### Rework

Sprints dispatches the implementer in `rework` mode.

The implementer receives reviewer output, human PR comments, bot/check
feedback, verification gaps, and the existing PR. It must update the same lane
branch and PR unless the prior PR is closed or merged and non-reusable.

After successful rework, the runner routes the lane back to Review.

### Merging

Sprints dispatches the implementer in `land` mode.

The implementer must open and follow `.codex/skills/land/SKILL.md`.

Rule:

```text
Do not call gh pr merge directly from runner/Python.
Only the implementer land mode performs landing actions through the land skill.
```

The implementer owns:

- checking merge authority
- checking PR reviews/checks/conflicts
- bounded polling for merge readiness
- merging according to land skill rules
- removing in-progress/review/rework/merging labels
- adding the done label
- updating the workpad

Python verifies the final state before releasing the lane.

### Done

Python verifies:

- PR is merged
- expected cleanup labels are absent
- `done` label/state is present
- no active actor run remains

Then Python releases the engine lease and marks the lane terminal.

## Responsibilities

### Python / Runner

Python is the durable lane supervisor.

It owns:

- discover eligible tickets
- read board/label state
- claim and release lanes
- enforce lane concurrency
- enforce actor concurrency
- create and load lane ledger
- write engine work records
- dispatch actors by state
- prevent duplicate actor runs
- track runtime sessions and heartbeats
- detect stale or interrupted runs
- schedule retries and backoff
- enforce max attempts
- compact actor prompts
- validate actor JSON contracts
- reconcile PR state, labels, checks, comments, and reviews
- route lanes between board states
- verify merge and cleanup before release
- persist audit, events, status, and tick journals

Python does not:

- write product code
- decide implementation approach
- perform pull request merge in actor-driven `change-delivery`
- perform final post-merge label cleanup in actor-driven `change-delivery`
- treat actor claims as truth without refreshing GitHub state

### Implementer Actor

The implementer is the main delivery agent.

The implementer always works on exactly one lane: the issue, branch, pull
request, workpad, and lane ID provided by the runner. Python chooses the lane
and gives the implementer a starting mode. The implementer may switch between
its own modes only inside that same lane when fresh lane facts make another mode
clearly correct. That is autonomy inside delivery, not authority over the
harness.

Mode switching examples:

- `implement -> rework` when concrete required fixes or failed checks already
  exist.
- `rework -> implement` only when the feedback was already resolved and the
  lane needs normal PR delivery work.
- `implement|rework -> land` only when merge authority is present through the
  lane input, such as the `merging` state or merge signal.

The implementer must record the mode it actually used and explain any mode
transition in structured output. It must never switch to another lane, reviewer
work, orchestrator work, or global scheduling.

It owns:

```text
implement mode:
  - understand issue
  - inspect repo
  - sync branch
  - implement smallest scoped change
  - debug failures
  - run focused verification
  - commit
  - push
  - create or update PR
  - update workpad
  - return structured JSON

rework mode:
  - read reviewer, human, bot, and check feedback
  - apply required fixes
  - push back only when explicitly justified
  - rerun verification
  - commit and push updates
  - update PR/workpad
  - return structured JSON

land mode:
  - open and follow the land skill
  - verify merge authority exists
  - check PR reviews/checks/conflicts
  - poll only within bounded limits
  - merge using skill instructions
  - cleanup labels/state
  - update workpad
  - return structured JSON
```

The implementer does not:

- claim other lanes
- pick unrelated issues
- change concurrency
- release durable lane ownership
- mark the lane complete without runner verification

### Reviewer Actor

The reviewer actor is one reviewer participant in the shared Review state.

It owns:

- inspect one PR/lane
- review correctness, regressions, scope, and verification
- return `approved`, `changes_requested`, `blocked`, or `failed`
- provide concrete `required_fixes` when changes are requested
- identify verification gaps

The reviewer does not:

- merge
- cleanup labels
- override human merge signals
- mutate unrelated lane state

### Human Operator

Humans use the board and GitHub review surfaces.

Humans own:

- moving tickets from Backlog to Todo
- reviewing PRs/comments/checks
- moving tickets to Rework when more work is wanted
- moving tickets to Merging when merge is authorized
- resolving true operator attention cases

## Merge Authority

The preferred merge authority signal is the board/label state `Merging`.

Humans move the GitHub Project card to Merging. GitHub automation applies the
machine label, for example:

```text
merging
```

Sprints reacts to the label, not the board API.

The merge signal is only actionable after the shared Review state is settled.
If the reviewer actor is still running, Sprints waits. If required changes are
present, Rework wins over Merging.

## Workpad Comment

Each claimed issue should have a persistent Sprints workpad comment.

The workpad is shared continuity for humans and agents. It should include:

- lane ID
- attempt
- current board state
- branch
- pull request
- last actor
- last result
- next expected state
- compact blocker/retry summary when relevant

Sprints should create the workpad before implementation starts. Actors may
update it during implement, rework, and land modes. Python verifies its existence
and may repair missing workpad metadata.

## Actor Output Contracts

### Implementer Implement/Rework Output

```json
{
  "status": "done|blocked|failed",
  "mode": "implement|rework",
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
```

Required for successful implement/rework:

- `status: done`
- branch
- pull request URL and number
- non-empty verification evidence

### Reviewer Output

```json
{
  "status": "approved|changes_requested|blocked|failed",
  "summary": "review summary",
  "findings": [],
  "required_fixes": [],
  "verification_gaps": [],
  "blockers": [],
  "next_recommendation": "merge|rework"
}
```

Required for `changes_requested`:

- non-empty `required_fixes`

### Implementer Land Output

```json
{
  "status": "merged|waiting|blocked|failed",
  "mode": "land",
  "summary": "landing summary",
  "pull_request": {
    "url": "https://github.com/owner/repo/pull/123",
    "number": 123,
    "state": "merged",
    "merged": true,
    "merge_commit": "..."
  },
  "cleanup": {
    "removed_labels": ["in-progress", "review", "merging"],
    "added_labels": ["done"],
    "issue_state": "open|closed"
  },
  "checks": [],
  "reviews": [],
  "blockers": [],
  "artifacts": {}
}
```

Required for successful landing:

- PR is merged
- cleanup evidence is present
- done label/state is present after runner refresh

## Retry And Attention

Retries remain engine-owned.

Python schedules retries for recoverable failures:

- invalid actor output that can be repaired
- actor runtime interruption
- transient GitHub/API/network failures
- land mode waiting within configured policy
- review/rework handoff retries

Python moves a lane to `operator_attention` only when automation cannot safely
continue:

- missing credentials or permissions
- ambiguous product intent
- unsafe/destructive requested change
- unrelated dirty files that actor cannot safely isolate
- repeated retry exhaustion
- merge authority conflict that cannot be resolved from board/review state
- actor output remains invalid after retry policy is exhausted

`operator_attention` is not used for normal human review waiting. Review waits
are ordinary workflow state.

## Configuration Shape

Proposed front matter direction:

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

The existing `orchestrator` front matter and `# Orchestrator Policy` section are
not required for actor-driven `change-delivery`.

Replace them with:

```text
# Workflow Policy
# Actor: implementer
# Actor: reviewer
```

`# Workflow Policy` defines routing and contracts. Python applies it
deterministically.

## Expected Tick Behavior

Each daemon tick:

1. Load workflow config and state.
2. Refresh lane issue/PR/review/check/label state.
3. Reconcile runtime sessions and stale actors.
4. Claim Todo lanes if capacity allows.
5. Route each active lane by board/label state.
6. Dispatch at most one actor per lane if no actor is already running.
7. Validate completed actor output.
8. Schedule retry, route state, or mark operator attention.
9. Verify Done lanes and release engine leases.
10. Persist lane state, engine projections, and tick journal.

No normal tick should call an orchestrator LLM for `change-delivery`.

## Migration Path

1. Add actor-driven mode behind config.
2. Keep existing orchestrator-driven templates working.
3. Create a new actor-driven `change-delivery` template.
4. Add state-label router for GitHub issues.
5. Add shared Review reconciliation.
6. Add implementer modes: implement, rework, land.
7. Move merge and cleanup instructions into land skill and implementer policy.
8. Change runner teardown for actor-driven mode to verify merge/cleanup only.
9. Update docs and operator commands around board states.

## Success Criteria

- `change-delivery` can run without an orchestrator actor.
- Todo issues are claimed and moved to In Progress before actor work starts.
- Implementer creates or updates PRs.
- Review is shared between reviewer actor, humans, bots, and checks.
- Merge signal in Merging is ignored while reviewer actor is running.
- Rework wins over merge signal when required changes exist.
- Implementer land mode merges and cleans labels by following the land skill.
- Runner verifies merged PR and cleanup before releasing the lane.
- Normal human review waiting does not become `operator_attention`.
- The engine remains durable across interrupted actor sessions and daemon restarts.
