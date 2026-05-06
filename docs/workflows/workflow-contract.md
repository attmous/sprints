# WORKFLOW.md Contract

`WORKFLOW.md` is the repo-owned contract for Sprints.

It has two parts:

1. YAML front matter for mechanics.
2. Markdown policy for the coder actor.

## Front Matter

Minimal shape:

```yaml
---
workflow: code
schema-version: 1

tracker:
  kind: github
  github_slug: owner/repo

code-host:
  kind: github
  github_slug: owner/repo

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

storage:
  state: .sprints/code-state.json
  audit-log: .sprints/code-audit.jsonl
---
```

## Step Labels

The `code` workflow uses labels as step state:

```text
todo -> code -> review -> merge -> done
          ^        |
          |--------|
```

| Label | Meaning |
| --- | --- |
| `todo` | Eligible for intake. |
| `code` | Coder should implement or address review feedback. |
| `review` | PR is ready; Sprints waits and polls reviews/checks/comments. |
| `merge` | Merge authority exists; coder runs the land skill. |
| `done` | Terminal; Sprints verifies and releases the lane. |
| `blocked` | Held for external unblock. |

## Policy Sections

The template contains:

- `# Workflow Policy`: human-readable workflow rules.
- `# Actor: coder`: the only actor policy.

The coder receives compact variables such as:

- `{{ issue }}`
- `{{ lane }}`
- `{{ step }}`
- `{{ workspace }}`
- `{{ repository }}`
- `{{ pull_request }}`
- `{{ review_feedback }}`
- `{{ attempt }}`
- `{{ retry }}`

The actor returns JSON only:

```json
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

## Ownership

Python owns:

- eligible issue discovery
- lane claims and leases
- concurrency
- worktree creation and recovery
- runtime dispatch
- retries and tick journals
- tracker label transitions
- status and audit projection

The coder owns:

- code changes in one lane worktree
- PR creation/update
- PR feedback sweep
- validation evidence
- land skill execution in `merge`
- structured JSON handoff
