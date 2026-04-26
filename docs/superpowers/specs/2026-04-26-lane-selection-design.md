# Configurable Lane Selection — Design Spec

**Issue:** [moustafattia/daedalus #2](https://github.com/moustafattia/daedalus/issues/2)
**Date:** 2026-04-26
**Status:** Approved (auto-mode)

## 1. Problem

Today's `pick_next_lane_issue` in `workflows/code_review/github.py:41-51` is a single-knob picker:

```python
def pick_next_lane_issue(items, *, active_lane_label="active-lane"):
    # candidates = open issues NOT yet labeled active-lane,
    # sorted by [P1] / [P2] title-priority then issue number
```

Real selection patterns operators want — multiple required labels, exclusion labels, label-based priority routing, alternative tiebreaks — have no surface in `workflow.yaml`.

## 2. Goals (in scope)

1. New top-level `lane-selection:` block in `workflow.yaml` with five optional fields: `require-labels`, `allow-any-of`, `exclude-labels`, `priority`, `tiebreak`.
2. Refactored `pick_next_lane_issue` that consumes the parsed config and applies multi-criteria selection.
3. Backwards-compat: workspaces with no `lane-selection:` block see identical behavior (any non-`active-lane` open issue, `[P1]` title priority, oldest fallback).
4. Schema validation entries for the new block.
5. Unit tests covering each selection axis + back-compat fallback.
6. Doc snippet showing severity-priority routing as a real-world example.

## 3. Non-goals

- Changing the lane-promotion mechanism in `actions.py:139-145` (the `merge-and-promote` step that *applies* the active-lane label). The new block configures *which issues become candidates*, not the post-pick mutation.
- Refactoring `get_active_lane_from_repo` (which finds the *currently* active lane). That stays a single-label query — `active-lane` is still the outcome label.
- Multi-workflow active-lane sharing or cross-workflow priority arbitration.
- Webhook-based selection. Polling-on-tick stays the model.

## 4. Architecture decisions

### 4.1 Promotion-rules model (per user clarification)

`lane-selection` configures *which open issues are eligible to be promoted next*. The `active-lane` label is automatically excluded from candidates because it's the outcome (it gets applied in `actions.py` after the picker fires). This matches the current code's behavior.

`lane-selection` does **not** drive `get_active_lane_from_repo` — that's a separate concern (find-currently-active, not pick-next-to-promote).

### 4.2 Title-priority preserved as tertiary tiebreak

The existing `parse_priority_from_title` (`[P1]`, `[P2]` from titles) remains in effect:
- When no `lane-selection.priority` configured: title priority is the **primary** sort (current behavior preserved exactly).
- When `lane-selection.priority` configured: label priority is primary, title priority becomes the **tertiary** tiebreak (after explicit `tiebreak: oldest|newest|random`, before issue number).

This gives projects with `[P1]/[P2]` title conventions a graceful upgrade path — they keep working, and label-based priority layers cleanly on top.

### 4.3 `repository.active-lane-label` stays independent

The `active-lane-label` setting remains the post-promotion "I'm working on this now" marker. It is automatically added to `exclude-labels` at config-parse time so the picker can never select an already-active lane. Operators don't need to repeat it in `lane-selection.exclude-labels`.

### 4.4 Per-workflow ownership of selection logic

The `lane-selection` schema and code live entirely in the workflow package (`workflows/code_review/`). A future testing workflow gets its own block + parser. Daedalus core is unaware of label semantics.

## 5. Configuration schema

New top-level `lane-selection:` block in workflow.yaml. All fields optional:

```yaml
lane-selection:
  # Logical AND — issue must have ALL of these labels to be a candidate.
  # Empty list / omitted = no required labels (any open issue eligible).
  require-labels:
    - needs-review

  # Logical OR — issue must have AT LEAST ONE of these labels.
  # Empty list / omitted = no requirement.
  allow-any-of:
    - daedalus-active
    - wip-codex

  # Issues with ANY of these labels are excluded.
  # The repository.active-lane-label is automatically added.
  exclude-labels:
    - blocked
    - do-not-touch

  # Higher in the list = higher priority. First matching label wins.
  # Issues with no priority label are tied at the bottom.
  priority:
    - severity:critical
    - severity:high
    - severity:medium
    - severity:low

  # Used when priority labels tie or all candidates lack priority labels.
  # One of: oldest | newest | random
  tiebreak: oldest
```

Schema entry to add to `workflows/code_review/schema.yaml` top-level `properties:`:

```yaml
lane-selection:
  type: object
  additionalProperties: false
  properties:
    require-labels:
      type: array
      items: {type: string}
    allow-any-of:
      type: array
      items: {type: string}
    exclude-labels:
      type: array
      items: {type: string}
    priority:
      type: array
      items: {type: string}
    tiebreak:
      type: string
      enum: [oldest, newest, random]
```

Defaults when block absent (synthesized at config-load):
- `require-labels: []` — no requirement (matches current "any open issue" behavior)
- `allow-any-of: []` — no requirement
- `exclude-labels: [<active-lane-label>]` — auto-populated from `repository.active-lane-label`
- `priority: []` — no label-based priority (title `[P1]/[P2]` rules)
- `tiebreak: oldest` — issue number ASC

## 6. Selection algorithm

```
function pick_next_lane_issue(items, lane_selection_cfg, active_lane_label):
    require    = lane_selection_cfg["require-labels"]
    any_of     = lane_selection_cfg["allow-any-of"]
    exclude    = lane_selection_cfg["exclude-labels"] | {active_lane_label}
    priority   = lane_selection_cfg["priority"]      # ordered list
    tiebreak   = lane_selection_cfg["tiebreak"]      # oldest|newest|random

    candidates = []
    for issue in items:
        labels = label_set(issue)

        # exclude wins
        if labels & set(exclude):
            continue
        # AND-required labels
        if require and not set(require).issubset(labels):
            continue
        # OR-required labels
        if any_of and not (labels & set(any_of)):
            continue

        label_priority = first_matching_index(priority, labels) or len(priority)  # bottom bucket
        title_priority = parse_priority_from_title(issue["title"])                # [P1] etc, default 999
        candidates.append((label_priority, title_priority, issue))

    if not candidates:
        return None

    # Primary: label priority (lower index = higher priority)
    # Within bucket: tiebreak (oldest=createdAt ASC, newest=createdAt DESC, random=shuffle)
    # Tertiary: title priority
    # Final: issue number ASC
    return sorted_with_tiebreak(candidates, tiebreak)[0].issue
```

Tiebreak `oldest` and `newest` use `createdAt` (already in gh's JSON output if requested — we add it to the `--json` flags of `pick_next_lane_issue_from_repo`). `random` uses Python's `random.choice` over the bucket; deterministic for tests via injectable seed.

## 7. Module layout

```
workflows/code_review/
  github.py              # MODIFIED — pick_next_lane_issue takes lane_selection_cfg
  workspace.py           # MODIFIED — parse + synthesize defaults at config load
  schema.yaml            # MODIFIED — add lane-selection block

tests/
  test_workflow_code_review_lane_selection.py    # NEW — multi-axis selection tests
  test_workflow_code_review_github.py            # MODIFIED — extend existing pick_next tests
```

## 8. Test strategy

### 8.1 Unit tests (pure function)

- Back-compat: empty config, behaves like current `pick_next_lane_issue`
- `require-labels` AND combination (1 label, 2 labels)
- `allow-any-of` OR combination
- `exclude-labels` filters out matching issues
- Auto-injection: `repository.active-lane-label` always excluded
- `priority` ordering: critical beats high beats medium
- `priority` tie inside bucket: tiebreak applied
- `tiebreak: oldest` (createdAt ASC), `newest` (createdAt DESC)
- `tiebreak: random` deterministic with seed (injectable RNG)
- Title-priority demoted to tertiary when label priority active
- Title-priority remains primary when label priority empty

### 8.2 Integration tests (config load)

- workflow.yaml without `lane-selection:` block → synthesized defaults match current behavior exactly
- workflow.yaml with full block → all fields parsed and threaded through
- workflow.yaml with invalid `tiebreak` value → schema rejects (tested via existing schema test pattern)

## 9. Backwards compatibility

- `lane-selection:` absent → synthesized config = `{require: [], any-of: [], exclude: [active-lane], priority: [], tiebreak: oldest}`. Selection delegates to title-priority + issue-number sort, which is exactly today's behavior.
- `pick_next_lane_issue(items, *, active_lane_label="active-lane")` keeps its current signature for direct callers; new optional `lane_selection_cfg` kwarg defaults to None (synthesizes the empty config in-function).
- Live YoYoPod workspace at `/home/radxa/.hermes/workflows/yoyopod/config/workflow.yaml` has no `lane-selection:` block → unchanged behavior.

## 10. Doc updates

- README or skills/operator/SKILL.md gets a short "Configurable lane selection" section with one realistic example (severity-priority routing).
- `docs/slash-commands-catalog.md` not affected — there's no slash command for lane selection (it's pure config).

## 11. Acceptance criteria

- [ ] Schema validates `lane-selection:` block with all five optional fields; rejects unknown fields and invalid `tiebreak` enum
- [ ] Live YoYoPod workflow.yaml validates against tightened schema without modification
- [ ] No `lane-selection:` block → identical behavior to today (verified by an explicit back-compat test)
- [ ] All five selection axes covered by unit tests (require / allow-any-of / exclude / priority / tiebreak)
- [ ] `repository.active-lane-label` auto-excluded even when not in `exclude-labels`
- [ ] Title `[P1]/[P2]` priority preserved as primary when `priority:` empty; demoted to tertiary tiebreak when populated
- [ ] All existing tests pass (baseline 285)
- [ ] Doc example present
