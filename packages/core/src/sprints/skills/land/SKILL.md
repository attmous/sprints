---
name: land
description: Land one reviewed Sprints lane when workflow merge authority is present.
---

# Land

Use this in coder `merge` step after the lane input shows merge authority,
usually through the `merge` step label or merge signal. The runner must not
call `gh pr merge` directly from workflow Python; this skill owns
the landing mechanics for the assigned lane.

## Rules

- Do not merge without explicit workflow or operator authority.
- Do not bypass failed checks.
- Do not ignore unresolved review comments.
- Do not land a different PR, issue, branch, or lane.
- Return `blocked` when merge permission, CI, conflicts, or review state blocks
  landing.
- After merge, explicitly close the source issue. Do not rely on GitHub
  auto-closing from the PR body.
- After the issue is closed, remove active workflow labels and add `done`.
- Do not return success until the source issue state is `closed`.
- Return structured JSON; do not ask for interactive follow-up.

## Steps

1. Locate the PR for the current branch with `gh pr view`.
2. Confirm the PR belongs to the assigned lane and merge authority is present.
3. Check mergeability, checks, review state, and unresolved review threads.
4. If review feedback requires changes, return `blocked` with concrete blockers;
   do not merge.
5. If the PR has conflicts, use the `pull` skill and push the resolved branch.
6. Inspect failing checks before making changes.
7. If checks fail and the fix is local, fix, commit, push, and wait again.
8. If checks pass and approval/authority is present, merge through the documented
   GitHub flow.
9. Close the source issue explicitly with the tracker or `gh issue close`.
10. Verify the source issue state is `closed`.
11. Clean tracker state for this lane: remove `code`, `review`, and `merge`; add
   `done`.
12. Update the Sprints workpad if available.

## Merged Output Shape

```json
{
  "status": "done",
  "mode": "land",
  "summary": "PR landed and lane cleanup completed",
  "pull_request": {
    "url": "https://github.com/owner/repo/pull/123",
    "number": 123,
    "state": "merged",
    "merged": true,
    "merge_commit": "merge commit sha if known"
  },
  "cleanup": {
    "removed_labels": ["code", "review", "merge"],
    "added_labels": ["done"],
    "issue_state": "closed",
    "issue_url": "https://github.com/owner/repo/issues/20"
  },
  "checks": [],
  "reviews": [],
  "blockers": [],
  "artifacts": {}
}
```

## Waiting Output Shape

Return `waiting` only for bounded, retryable waits such as GitHub still
computing mergeability or checks still running.

```json
{
  "status": "waiting",
  "mode": "land",
  "summary": "PR is waiting for checks to finish",
  "pull_request": {
    "url": "https://github.com/owner/repo/pull/123",
    "number": 123,
    "state": "open"
  },
  "checks": [],
  "blockers": [],
  "artifacts": {}
}
```

## Blocked Output Shape

```json
{
  "status": "blocked",
  "mode": "land",
  "summary": "PR cannot be landed yet",
  "blockers": [
    {
      "kind": "review_required",
      "command": "gh pr view",
      "message": "Pull request has unresolved review feedback."
    }
  ],
  "artifacts": {
    "pull_request": {}
  }
}
```
