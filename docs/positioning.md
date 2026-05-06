# Positioning

Sprints is not an agent model and not a tracker.

It is the orchestration layer that connects repo policy, runtimes, state, and
operator controls.

## Boundaries

| Product | Owns |
| --- | --- |
| Hermes-Agent | Interactive agent runtime and model/tool execution. |
| Sprints | Durable workflow execution around repo-owned `WORKFLOW.md`. |
| Trackers | Work item source and status surface. |
| Code hosts | Branches, PRs, checks, reviews, and merge. |

Sprints keeps lane mechanics in Python and lane work instructions in
`WORKFLOW.md`. Python owns claims, retries, step labels, leases, dispatch, and
status. The workflow policy tells the coder how to execute the current step.

## Why Sprints Exists

Supervised workflow execution needs state that survives one chat turn:

- which work item is active
- which actor ran
- which runtime/session was used
- what the actor returned
- which step the lane is in
- what needs retry or operator attention

Sprints owns that loop.

## What Not To Put Here

- Kanban board semantics
- product roadmap decisions
- model prompting policy that belongs in `WORKFLOW.md`
- code-host rules that belong in tracker/code-host config
- one-off migration history
