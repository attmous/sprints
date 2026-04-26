# Configurable Lane Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship Daedalus issue #2 — a `lane-selection:` block in `workflow.yaml` that configures multi-criteria promotion eligibility (require-labels, allow-any-of, exclude-labels, priority, tiebreak).

**Architecture:** Replace the single-knob filter in `workflows/code_review/github.py::pick_next_lane_issue` with a multi-axis selector that consumes a parsed `lane-selection` config dict. Workspace config-load synthesizes defaults when the block is absent so back-compat is automatic. No change to the post-pick mutation in `actions.py`.

**Tech Stack:** Python 3.11 stdlib + pyyaml + jsonschema (already deps).

**Spec:** `docs/superpowers/specs/2026-04-26-lane-selection-design.md`

**Tests baseline:** 285 passing, 0 failing on `main` (snapshot taken when worktree was created). Final state: 285 + N new tests, 0 failing.

**Worktree:** `.claude/worktrees/lane-selection-issue-2` on branch `claude/lane-selection-issue-2`. All commits land here.

**Always use** `/usr/bin/python3` (system 3.11 has pyyaml + jsonschema; homebrew python3 does not).

---

## Phase 0: Preflight

### Task 0.1: Verify worktree + baseline

- [ ] **Step 1: Confirm baseline tests pass**

Run: `cd /home/radxa/WS/hermes-relay/.claude/worktrees/lane-selection-issue-2 && /usr/bin/python3 -m pytest -q 2>&1 | tail -3`
Expected: `285 passed in <X>s`. If anything else, STOP and report.

No commit.

---

## Phase 1: Schema entry

### Task 1.1: Add `lane-selection:` block to `workflows/code_review/schema.yaml`

**Files:**
- Modify: `workflows/code_review/schema.yaml`
- Test: `tests/test_workflow_code_review_lane_selection_schema.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_workflow_code_review_lane_selection_schema.py`:

```python
"""Schema validation for the lane-selection block in workflow.yaml."""
from pathlib import Path

import jsonschema
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "workflows" / "code_review" / "schema.yaml"


def _load_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _minimal_valid_config() -> dict:
    return {
        "workflow": "code-review",
        "schema-version": 1,
        "instance": {"name": "test", "engine-owner": "hermes"},
        "repository": {
            "local-path": "/tmp/x",
            "github-slug": "owner/repo",
            "active-lane-label": "active-lane",
        },
        "runtimes": {
            "acpx-codex": {
                "kind": "acpx-codex",
                "session-idle-freshness-seconds": 1,
                "session-idle-grace-seconds": 1,
                "session-nudge-cooldown-seconds": 1,
            }
        },
        "agents": {
            "coder": {"default": {"name": "x", "model": "y", "runtime": "acpx-codex"}},
            "internal-reviewer": {"name": "x", "model": "y", "runtime": "acpx-codex"},
            "external-reviewer": {"enabled": True, "name": "x"},
        },
        "gates": {"internal-review": {}, "external-review": {}, "merge": {}},
        "triggers": {"lane-selector": {"type": "github-label", "label": "active-lane"}},
        "storage": {"ledger": "l", "health": "h", "audit-log": "a"},
    }


def test_schema_accepts_config_without_lane_selection_block():
    """Back-compat: workspaces without lane-selection still validate."""
    schema = _load_schema()
    cfg = _minimal_valid_config()
    jsonschema.validate(cfg, schema)


def test_schema_accepts_full_lane_selection_block():
    schema = _load_schema()
    cfg = _minimal_valid_config()
    cfg["lane-selection"] = {
        "require-labels": ["needs-review"],
        "allow-any-of": ["urgent", "wip-codex"],
        "exclude-labels": ["blocked"],
        "priority": ["severity:critical", "severity:high"],
        "tiebreak": "oldest",
    }
    jsonschema.validate(cfg, schema)


def test_schema_accepts_partial_lane_selection_block():
    schema = _load_schema()
    cfg = _minimal_valid_config()
    cfg["lane-selection"] = {"exclude-labels": ["blocked"]}
    jsonschema.validate(cfg, schema)


def test_schema_rejects_invalid_tiebreak_value():
    schema = _load_schema()
    cfg = _minimal_valid_config()
    cfg["lane-selection"] = {"tiebreak": "lottery"}
    try:
        jsonschema.validate(cfg, schema)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected ValidationError for tiebreak='lottery'")


def test_schema_rejects_unknown_lane_selection_field():
    schema = _load_schema()
    cfg = _minimal_valid_config()
    cfg["lane-selection"] = {"unknown-axis": ["x"]}
    try:
        jsonschema.validate(cfg, schema)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected ValidationError for unknown lane-selection field")


def test_schema_rejects_non_array_require_labels():
    schema = _load_schema()
    cfg = _minimal_valid_config()
    cfg["lane-selection"] = {"require-labels": "needs-review"}  # string, not array
    try:
        jsonschema.validate(cfg, schema)
    except jsonschema.ValidationError:
        return
    raise AssertionError("expected ValidationError for non-array require-labels")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/usr/bin/python3 -m pytest tests/test_workflow_code_review_lane_selection_schema.py -v`
Expected: the "accept" tests pass (schema currently allows unknown top-level keys), the "reject" tests fail with `"expected ValidationError"`. Tests will go all-green after Step 3.

- [ ] **Step 3: Add `lane-selection` block to schema**

In `workflows/code_review/schema.yaml`, locate the existing `properties:` block (top-level). Insert the following entry alphabetically — after `instance:` and before `prompts:` is fine, or at the end of `properties:` if simpler. Order doesn't matter for jsonschema. Place it right before the `definitions:` top-level key:

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

- [ ] **Step 4: Run tests to verify all pass**

Run: `/usr/bin/python3 -m pytest tests/test_workflow_code_review_lane_selection_schema.py -v`
Expected: 6 passed.

Run: `/usr/bin/python3 -m pytest -q 2>&1 | tail -3`
Expected: 285+6 = 291 passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add workflows/code_review/schema.yaml tests/test_workflow_code_review_lane_selection_schema.py
git commit -m "feat(schema): add lane-selection block to code-review workflow

Five optional fields: require-labels (AND), allow-any-of (OR),
exclude-labels, priority (ordered list), tiebreak (oldest|newest|random).
additionalProperties: false catches typos. Block is optional —
existing workflow.yaml files without it continue to validate."
```

---

## Phase 2: Selection algorithm

### Task 2.1: Synthesize default lane-selection config from raw yaml

**Files:**
- Create: `workflows/code_review/lane_selection.py`
- Test: `tests/test_workflow_code_review_lane_selection_config.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_workflow_code_review_lane_selection_config.py`:

```python
"""Synthesizing the parsed lane-selection config from workflow.yaml."""
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _module():
    return load_module(
        "daedalus_workflow_lane_selection_config_test",
        "workflows/code_review/lane_selection.py",
    )


def test_synthesize_defaults_when_block_absent():
    ls = _module()
    cfg = ls.parse_config(workflow_yaml={}, active_lane_label="active-lane")
    assert cfg["require-labels"] == []
    assert cfg["allow-any-of"] == []
    # The active-lane label is auto-excluded so the picker can never pick
    # an already-promoted issue, even if the operator forgets to list it.
    assert "active-lane" in cfg["exclude-labels"]
    assert cfg["priority"] == []
    assert cfg["tiebreak"] == "oldest"


def test_synthesize_uses_active_lane_label_in_excludes():
    ls = _module()
    cfg = ls.parse_config(workflow_yaml={}, active_lane_label="custom-active")
    assert "custom-active" in cfg["exclude-labels"]


def test_user_excludes_are_merged_with_active_lane_label():
    ls = _module()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"exclude-labels": ["blocked", "do-not-touch"]}},
        active_lane_label="active-lane",
    )
    # Both user-provided and auto-injected
    assert set(cfg["exclude-labels"]) == {"blocked", "do-not-touch", "active-lane"}


def test_user_explicit_active_lane_label_in_excludes_does_not_duplicate():
    ls = _module()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"exclude-labels": ["active-lane", "blocked"]}},
        active_lane_label="active-lane",
    )
    # Set semantics — no duplicate
    assert cfg["exclude-labels"].count("active-lane") == 1
    assert "blocked" in cfg["exclude-labels"]


def test_full_block_passes_through():
    ls = _module()
    cfg = ls.parse_config(
        workflow_yaml={
            "lane-selection": {
                "require-labels": ["needs-review"],
                "allow-any-of": ["urgent", "p0"],
                "exclude-labels": ["blocked"],
                "priority": ["severity:critical", "severity:high"],
                "tiebreak": "newest",
            }
        },
        active_lane_label="active-lane",
    )
    assert cfg["require-labels"] == ["needs-review"]
    assert cfg["allow-any-of"] == ["urgent", "p0"]
    assert cfg["priority"] == ["severity:critical", "severity:high"]
    assert cfg["tiebreak"] == "newest"
    assert "active-lane" in cfg["exclude-labels"]


def test_label_strings_are_lowercased():
    """GitHub label matching is case-insensitive in our existing label_set helper.
    The parsed config should normalize so set comparisons later are clean."""
    ls = _module()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"require-labels": ["Needs-Review"], "exclude-labels": ["BLOCKED"]}},
        active_lane_label="Active-Lane",
    )
    assert cfg["require-labels"] == ["needs-review"]
    assert "blocked" in cfg["exclude-labels"]
    assert "active-lane" in cfg["exclude-labels"]
```

- [ ] **Step 2: Run failing tests**

Run: `/usr/bin/python3 -m pytest tests/test_workflow_code_review_lane_selection_config.py -v`
Expected: All fail — `lane_selection.py` doesn't exist yet.

- [ ] **Step 3: Implement parser**

Create `workflows/code_review/lane_selection.py`:

```python
"""Lane-selection config parser.

Synthesizes a fully-populated config dict from the (optional) ``lane-selection:``
block in workflow.yaml. Defaults preserve current behavior exactly so workspaces
without the block see no change in promotion semantics.
"""
from __future__ import annotations

from typing import Any, Mapping


_VALID_TIEBREAKS = {"oldest", "newest", "random"}


def _norm_list(values) -> list[str]:
    """Lowercase + strip + drop empties. Preserves caller order."""
    out: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        if not isinstance(v, str):
            continue
        s = v.strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def parse_config(
    *,
    workflow_yaml: Mapping[str, Any],
    active_lane_label: str,
) -> dict[str, Any]:
    """Return a fully-populated lane-selection config.

    Defaults (when the block or any field is absent):

      - require-labels: []
      - allow-any-of:   []
      - exclude-labels: [<active-lane-label>]   (auto-injected — never picked)
      - priority:       []
      - tiebreak:       "oldest"

    All label strings are normalized to lowercase to keep set-comparisons in
    the picker uniform with our existing ``issue_label_names`` helper, which
    lowercases on read.
    """
    block = (workflow_yaml or {}).get("lane-selection") or {}

    require = _norm_list(block.get("require-labels"))
    any_of = _norm_list(block.get("allow-any-of"))
    user_exclude = _norm_list(block.get("exclude-labels"))
    priority = _norm_list(block.get("priority"))

    # Auto-inject the active-lane label so the picker can never pick a
    # currently-active lane, even when the operator forgets to list it.
    auto_exclude = (active_lane_label or "").strip().lower()
    exclude = list(user_exclude)
    if auto_exclude and auto_exclude not in exclude:
        exclude.append(auto_exclude)

    raw_tiebreak = block.get("tiebreak") or "oldest"
    tiebreak = raw_tiebreak if raw_tiebreak in _VALID_TIEBREAKS else "oldest"

    return {
        "require-labels": require,
        "allow-any-of": any_of,
        "exclude-labels": exclude,
        "priority": priority,
        "tiebreak": tiebreak,
    }
```

- [ ] **Step 4: Run tests + verify pass**

Run: `/usr/bin/python3 -m pytest tests/test_workflow_code_review_lane_selection_config.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add workflows/code_review/lane_selection.py tests/test_workflow_code_review_lane_selection_config.py
git commit -m "feat(lane-selection): parse_config synthesizes defaults

Pure-function parser produces a fully-populated config dict with all
five fields. Auto-injects the active-lane label into exclude-labels
so the picker can never select a currently-active lane. All label
strings lowercase-normalized to match our existing label_set helper."
```

---

### Task 2.2: Refactor `pick_next_lane_issue` to multi-criteria selector

**Files:**
- Modify: `workflows/code_review/github.py:41-65`
- Test: `tests/test_workflow_code_review_lane_selection.py` (new)

- [ ] **Step 1: Write the failing test (multi-axis selection)**

Create `tests/test_workflow_code_review_lane_selection.py`:

```python
"""Multi-axis lane selection: require / allow-any-of / exclude / priority / tiebreak."""
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _gh():
    return load_module("daedalus_workflow_github_test", "workflows/code_review/github.py")


def _ls():
    return load_module("daedalus_workflow_lane_selection_test_2", "workflows/code_review/lane_selection.py")


def _issue(number, labels=None, title=None, created_at=None):
    """Build a fake gh-issue dict matching `gh issue list --json`'s shape."""
    return {
        "number": number,
        "title": title or f"Issue {number}",
        "labels": [{"name": l} for l in (labels or [])],
        "createdAt": created_at,
    }


def _empty_cfg(active_lane_label="active-lane"):
    """Synthesized default config — same shape parse_config returns."""
    return _ls().parse_config(workflow_yaml={}, active_lane_label=active_lane_label)


# ─── Back-compat ─────────────────────────────────────────────────────

def test_back_compat_picks_lowest_p_priority_then_lowest_number():
    """No lane-selection block → pure title-priority + issue-number sort (current behavior)."""
    gh = _gh()
    items = [
        _issue(10, title="Issue 10"),               # title priority 999 (no [P])
        _issue(20, title="[P2] medium", labels=[]),
        _issue(30, title="[P1] high"),
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=_empty_cfg())
    assert chosen["number"] == 30  # [P1] wins


def test_back_compat_excludes_active_lane_label():
    gh = _gh()
    items = [
        _issue(10, labels=["active-lane"], title="[P1] in progress"),
        _issue(20, title="[P2] candidate"),
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=_empty_cfg())
    assert chosen["number"] == 20  # 10 excluded


# ─── require-labels (AND) ────────────────────────────────────────────

def test_require_labels_AND_combination():
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"require-labels": ["needs-review", "ready"]}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(10, labels=["needs-review"]),                    # missing ready
        _issue(20, labels=["needs-review", "ready"]),
        _issue(30, labels=["needs-review", "ready", "extra"]),
    ]
    # Both 20 and 30 qualify; oldest tiebreak → lowest number = 20
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 20


def test_require_labels_returns_none_when_no_match():
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"require-labels": ["needs-review"]}},
        active_lane_label="active-lane",
    )
    items = [_issue(10, labels=["other"])]
    assert gh.pick_next_lane_issue(items, lane_selection_cfg=cfg) is None


# ─── allow-any-of (OR) ────────────────────────────────────────────

def test_allow_any_of_OR_combination():
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"allow-any-of": ["urgent", "wip-codex"]}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(10, labels=["other"]),       # neither
        _issue(20, labels=["wip-codex"]),
        _issue(30, labels=["urgent"]),
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 20  # oldest of 20/30 wins


# ─── exclude-labels ────────────────────────────────────────────

def test_exclude_labels_filters_out_blocked():
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"exclude-labels": ["blocked"]}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(10, labels=["blocked"]),
        _issue(20),
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 20


def test_exclude_wins_over_require():
    """If an issue has BOTH a required label AND an excluded label, exclude wins."""
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"require-labels": ["needs-review"], "exclude-labels": ["blocked"]}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(10, labels=["needs-review", "blocked"]),
        _issue(20, labels=["needs-review"]),
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 20


# ─── priority ────────────────────────────────────────────

def test_priority_critical_beats_high():
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"priority": ["severity:critical", "severity:high"]}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(10, labels=["severity:high"]),
        _issue(20, labels=["severity:critical"]),
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 20


def test_priority_unmatched_issues_fall_to_bottom_bucket():
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"priority": ["severity:critical"]}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(10),                                # no priority label
        _issue(20, labels=["severity:critical"]),
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 20


def test_priority_multiple_labels_picks_highest():
    """When an issue has multiple priority labels, the highest-ranked wins."""
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"priority": ["severity:critical", "severity:high"]}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(10, labels=["severity:high"]),
        _issue(20, labels=["severity:high", "severity:critical"]),  # has both
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 20  # picks via critical


# ─── tiebreak ────────────────────────────────────────────

def test_tiebreak_oldest_uses_created_at_asc():
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"tiebreak": "oldest"}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(20, created_at="2026-04-26T12:00:00Z"),
        _issue(10, created_at="2026-04-25T12:00:00Z"),  # older
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 10


def test_tiebreak_newest_uses_created_at_desc():
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"tiebreak": "newest"}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(20, created_at="2026-04-26T12:00:00Z"),  # newer
        _issue(10, created_at="2026-04-25T12:00:00Z"),
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 20


def test_tiebreak_random_with_seeded_rng_is_deterministic():
    gh, ls = _gh(), _ls()
    import random
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"tiebreak": "random"}},
        active_lane_label="active-lane",
    )
    items = [_issue(10), _issue(20), _issue(30)]
    rng = random.Random(42)
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg, rng=rng)
    # Don't assert a specific number — just that the function returns something
    # from the candidate set, and that the same seed is reproducible.
    assert chosen["number"] in {10, 20, 30}
    rng2 = random.Random(42)
    chosen2 = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg, rng=rng2)
    assert chosen["number"] == chosen2["number"]


# ─── title-priority interaction ────────────────────────────────────────────

def test_title_priority_remains_primary_when_label_priority_empty():
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(workflow_yaml={"lane-selection": {}}, active_lane_label="active-lane")
    items = [
        _issue(10, title="[P3] low"),
        _issue(20, title="[P1] urgent"),
    ]
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 20  # [P1] wins


def test_title_priority_demoted_to_tertiary_when_label_priority_active():
    """When label priority is configured, it's primary; title priority becomes a tertiary tiebreak."""
    gh, ls = _gh(), _ls()
    cfg = ls.parse_config(
        workflow_yaml={"lane-selection": {"priority": ["severity:critical"]}},
        active_lane_label="active-lane",
    )
    items = [
        _issue(10, labels=["severity:critical"], title="[P3] low priority title"),
        _issue(20, title="[P1] high title but no severity label"),
    ]
    # 10 has the critical label → wins despite worse title priority
    chosen = gh.pick_next_lane_issue(items, lane_selection_cfg=cfg)
    assert chosen["number"] == 10


# ─── back-compat function signature ────────────────────────────────────────────

def test_pick_next_lane_issue_back_compat_positional_call():
    """Existing callers using `pick_next_lane_issue(items, active_lane_label='X')` keep working."""
    gh = _gh()
    items = [
        _issue(10, labels=["active-lane"]),
        _issue(20),
    ]
    # Old-style call — no lane_selection_cfg passed
    chosen = gh.pick_next_lane_issue(items, active_lane_label="active-lane")
    assert chosen["number"] == 20
```

- [ ] **Step 2: Run failing tests**

Run: `/usr/bin/python3 -m pytest tests/test_workflow_code_review_lane_selection.py -v`
Expected: All fail — `pick_next_lane_issue` doesn't accept `lane_selection_cfg` kwarg yet.

- [ ] **Step 3: Refactor `pick_next_lane_issue`**

Replace the existing `pick_next_lane_issue` function in `workflows/code_review/github.py` (lines ~41-51) with the multi-criteria implementation. The new signature keeps `active_lane_label` for back-compat but adds an optional `lane_selection_cfg` kwarg:

```python
def pick_next_lane_issue(
    items: list[dict[str, Any]] | None,
    *,
    active_lane_label: str = "active-lane",
    lane_selection_cfg: dict[str, Any] | None = None,
    rng=None,
) -> dict[str, Any] | None:
    """Pick the next open issue eligible for promotion to active lane.

    The ``lane_selection_cfg`` is the parsed config from
    :mod:`workflows.code_review.lane_selection.parse_config`. When ``None``,
    we synthesize a back-compat config (no required labels, the active-lane
    label auto-excluded, oldest tiebreak) which preserves pre-issue-#2
    behavior exactly.

    ``rng`` is injectable for the ``tiebreak: random`` path so tests are
    deterministic. Defaults to a fresh ``random.Random()``.
    """
    import random

    # Synthesize back-compat config when caller didn't pass one — this is the
    # path existing direct callers (test code, retired wrapper) take.
    if lane_selection_cfg is None:
        # Lazy import to avoid a circular import at module-load.
        try:
            from .lane_selection import parse_config as _parse
        except ImportError:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                "daedalus_lane_selection_for_picker",
                Path(__file__).resolve().parent / "lane_selection.py",
            )
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _parse = _mod.parse_config
        lane_selection_cfg = _parse(workflow_yaml={}, active_lane_label=active_lane_label)

    require = set(lane_selection_cfg.get("require-labels") or [])
    any_of = set(lane_selection_cfg.get("allow-any-of") or [])
    exclude = set(lane_selection_cfg.get("exclude-labels") or [])
    priority = lane_selection_cfg.get("priority") or []
    tiebreak = lane_selection_cfg.get("tiebreak") or "oldest"
    has_label_priority = bool(priority)

    candidates = []
    for item in items or []:
        labels = issue_label_names(item)

        # Exclude wins over everything.
        if labels & exclude:
            continue
        # AND-required labels must all be present.
        if require and not require.issubset(labels):
            continue
        # OR-required labels: at least one must be present.
        if any_of and not (labels & any_of):
            continue

        # Label-priority bucket: lowest index = highest priority. Issues with
        # no matching priority label fall into the bottom bucket (len(priority)).
        label_bucket = len(priority)
        for idx, plabel in enumerate(priority):
            if plabel in labels:
                label_bucket = idx
                break

        title_pri = parse_priority_from_title(item.get("title"))
        candidates.append({
            "label_bucket": label_bucket,
            "title_pri": title_pri,
            "issue": item,
        })

    if not candidates:
        return None

    # Sort by primary key. Within bucket, apply tiebreak. Title priority is
    # primary when no label priority is configured (preserves current behavior),
    # tertiary when label priority is configured.
    if has_label_priority:
        primary_key = lambda c: c["label_bucket"]
    else:
        primary_key = lambda c: c["title_pri"]

    candidates.sort(key=primary_key)
    top_value = primary_key(candidates[0])
    top_bucket = [c for c in candidates if primary_key(c) == top_value]

    if len(top_bucket) == 1:
        return top_bucket[0]["issue"]

    # Resolve within-bucket tiebreak.
    if tiebreak == "newest":
        top_bucket.sort(key=lambda c: c["issue"].get("createdAt") or "", reverse=True)
    elif tiebreak == "random":
        rng = rng or random.Random()
        return rng.choice(top_bucket)["issue"]
    else:  # "oldest" (default)
        top_bucket.sort(key=lambda c: c["issue"].get("createdAt") or "")

    if has_label_priority:
        # Tertiary: title priority within tiebreak group of 1 createdAt.
        # Re-stable-sort so equal-createdAt rows fall back to title pri.
        top_bucket.sort(key=lambda c: c["title_pri"])  # stable sort preserves tiebreak order

    # Final tiebreak: issue number ASC.
    top_bucket.sort(key=lambda c: int(c["issue"].get("number") or 0))
    if has_label_priority:
        top_bucket.sort(key=lambda c: c["title_pri"])  # primary among final tiebreak set

    return top_bucket[0]["issue"]
```

Wait — the layered-sort logic above is fiddly. Replace the post-tiebreak section with a single `key=` that encodes the entire ordering:

```python
def _sort_key(candidate):
    issue = candidate["issue"]
    created = issue.get("createdAt") or ""
    if tiebreak == "newest":
        time_key = (-_iso_to_unix(created),)  # negative for descending
    elif tiebreak == "oldest":
        time_key = (created,)
    else:  # random
        time_key = (0,)  # uniform — tiebreak applied separately below
    return (
        candidate["label_bucket"] if has_label_priority else candidate["title_pri"],
        *time_key,
        candidate["title_pri"] if has_label_priority else 0,
        int(issue.get("number") or 0),
    )

if tiebreak == "random":
    candidates.sort(key=_sort_key)
    top_value = _sort_key(candidates[0])[0]
    top_bucket = [c for c in candidates if _sort_key(c)[0] == top_value]
    rng = rng or random.Random()
    return rng.choice(top_bucket)["issue"]
candidates.sort(key=_sort_key)
return candidates[0]["issue"]
```

Add a helper near the top of `github.py`:

```python
def _iso_to_unix(iso_str: str) -> int:
    """Return Unix epoch seconds, or 0 if unparseable. Used for tiebreak sort keys."""
    if not iso_str:
        return 0
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return 0
```

Final implementation of `pick_next_lane_issue`:

```python
def pick_next_lane_issue(
    items: list[dict[str, Any]] | None,
    *,
    active_lane_label: str = "active-lane",
    lane_selection_cfg: dict[str, Any] | None = None,
    rng=None,
) -> dict[str, Any] | None:
    """Pick the next open issue eligible for promotion to active lane.

    ``lane_selection_cfg`` is the parsed config from
    :mod:`workflows.code_review.lane_selection.parse_config`. When ``None``,
    we synthesize a back-compat config (no required labels, the active-lane
    label auto-excluded, oldest tiebreak) preserving pre-issue-#2 behavior.

    ``rng`` is injectable for the ``tiebreak: random`` path so tests are
    deterministic. Defaults to a fresh ``random.Random()``.
    """
    import random

    if lane_selection_cfg is None:
        try:
            from .lane_selection import parse_config as _parse
        except ImportError:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                "daedalus_lane_selection_for_picker",
                Path(__file__).resolve().parent / "lane_selection.py",
            )
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _parse = _mod.parse_config
        lane_selection_cfg = _parse(workflow_yaml={}, active_lane_label=active_lane_label)

    require = set(lane_selection_cfg.get("require-labels") or [])
    any_of = set(lane_selection_cfg.get("allow-any-of") or [])
    exclude = set(lane_selection_cfg.get("exclude-labels") or [])
    priority = lane_selection_cfg.get("priority") or []
    tiebreak = lane_selection_cfg.get("tiebreak") or "oldest"
    has_label_priority = bool(priority)

    candidates = []
    for item in items or []:
        labels = issue_label_names(item)
        if labels & exclude:
            continue
        if require and not require.issubset(labels):
            continue
        if any_of and not (labels & any_of):
            continue

        label_bucket = len(priority)
        for idx, plabel in enumerate(priority):
            if plabel in labels:
                label_bucket = idx
                break

        candidates.append({
            "label_bucket": label_bucket,
            "title_pri": parse_priority_from_title(item.get("title")),
            "issue": item,
        })

    if not candidates:
        return None

    def _sort_key(c):
        issue = c["issue"]
        created = issue.get("createdAt") or ""
        if tiebreak == "newest":
            time_key = -_iso_to_unix(created)
        elif tiebreak == "oldest":
            time_key = _iso_to_unix(created)
        else:  # random — placeholder, picker handles random separately
            time_key = 0
        # Build the full sort tuple. Primary = label or title priority depending
        # on whether label priority is configured.
        if has_label_priority:
            return (c["label_bucket"], time_key, c["title_pri"], int(issue.get("number") or 0))
        return (c["title_pri"], time_key, int(issue.get("number") or 0))

    if tiebreak == "random":
        # Identify the top primary-bucket, then pick uniformly from it.
        candidates.sort(key=_sort_key)
        primary_top = _sort_key(candidates[0])[0]
        top_bucket = [c for c in candidates if _sort_key(c)[0] == primary_top]
        rng = rng or random.Random()
        return rng.choice(top_bucket)["issue"]

    candidates.sort(key=_sort_key)
    return candidates[0]["issue"]
```

Also: `pick_next_lane_issue_from_repo` needs to (a) thread `lane_selection_cfg` through, and (b) request `createdAt` in the gh JSON output. Update lines ~55-65:

```python
def pick_next_lane_issue_from_repo(
    repo_path: Path,
    *,
    run_json: Callable[..., list[dict[str, Any]]],
    active_lane_label: str = "active-lane",
    lane_selection_cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    items = run_json(
        ["gh", "issue", "list", "--state", "open", "--limit", "100",
         "--json", "number,title,url,labels,createdAt"],
        cwd=repo_path,
    )
    return pick_next_lane_issue(
        items,
        active_lane_label=active_lane_label,
        lane_selection_cfg=lane_selection_cfg,
    )
```

- [ ] **Step 4: Run new tests**

Run: `/usr/bin/python3 -m pytest tests/test_workflow_code_review_lane_selection.py -v`
Expected: All 16 passed.

- [ ] **Step 5: Run existing github.py tests for regressions**

Run: `/usr/bin/python3 -m pytest tests/ -k "github" -v 2>&1 | tail -10`
Expected: any pre-existing tests for `pick_next_lane_issue` still pass (they call the old positional form, which back-compat preserves).

- [ ] **Step 6: Run full suite**

Run: `/usr/bin/python3 -m pytest -q 2>&1 | tail -5`
Expected: 285 + 6 (Phase 1) + 6 (Task 2.1) + 16 (Task 2.2) = 313 passed, 0 failed.

- [ ] **Step 7: Commit**

```bash
git add workflows/code_review/github.py tests/test_workflow_code_review_lane_selection.py
git commit -m "feat(github): pick_next_lane_issue accepts lane_selection_cfg

Multi-criteria selection: require (AND) / allow-any-of (OR) / exclude /
priority / tiebreak. Active-lane label auto-excluded. Title-priority
remains primary when no label priority configured (full back-compat),
demoted to tertiary tiebreak when label priority is active.

Tiebreak random path takes injectable RNG for determinism in tests.
gh issue list --json now requests createdAt so tiebreak=oldest|newest
can sort by issue creation time."
```

---

## Phase 3: Workspace integration

### Task 3.1: Thread `lane_selection_cfg` through `workspace.build_workspace`

**Files:**
- Modify: `workflows/code_review/workspace.py:781` (and config-load surface)
- Test: `tests/test_workflow_code_review_lane_selection_workspace.py` (new)

- [ ] **Step 1: Read existing call site to find variable names**

Run: `grep -n "pick_next_lane_issue\|active_lane_label" workflows/code_review/workspace.py | head -10`

You'll see calls around line 781 that look something like:
```python
return _gh_module().pick_next_lane_issue(items, active_lane_label=ns.ACTIVE_LANE_LABEL)
```

Note the exact call line(s). The refactor adds `lane_selection_cfg=ns.LANE_SELECTION_CFG`.

- [ ] **Step 2: Write the failing integration test**

Create `tests/test_workflow_code_review_lane_selection_workspace.py`:

```python
"""Workspace bootstrap parses lane-selection block and threads it to the picker."""
import importlib.util
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name, relative_path):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lane_selection_cfg_synthesized_when_block_absent():
    """A workspace built from a yaml without lane-selection still gets a parsed config attached."""
    workspace = load_module("daedalus_workspace_lane_selection_test_a", "workflows/code_review/workspace.py")
    yaml_cfg = {
        "workflow": "code-review",
        "schema-version": 1,
        "instance": {"name": "x", "engine-owner": "hermes"},
        "repository": {"local-path": "/tmp", "github-slug": "o/r", "active-lane-label": "active-lane"},
        "runtimes": {"acpx-codex": {"kind": "acpx-codex", "session-idle-freshness-seconds": 1, "session-idle-grace-seconds": 1, "session-nudge-cooldown-seconds": 1}},
        "agents": {"coder": {"default": {"name": "x", "model": "y", "runtime": "acpx-codex"}}, "internal-reviewer": {"name": "x", "model": "y", "runtime": "acpx-codex"}, "external-reviewer": {"enabled": True, "name": "x"}},
        "gates": {"internal-review": {}, "external-review": {}, "merge": {}},
        "triggers": {"lane-selector": {"type": "github-label", "label": "active-lane"}},
        "storage": {"ledger": "l", "health": "h", "audit-log": "a"},
    }
    cfg = workspace._derive_lane_selection_cfg(yaml_cfg, active_lane_label="active-lane")
    assert cfg["require-labels"] == []
    assert "active-lane" in cfg["exclude-labels"]
    assert cfg["tiebreak"] == "oldest"


def test_lane_selection_cfg_picked_up_when_block_present():
    workspace = load_module("daedalus_workspace_lane_selection_test_b", "workflows/code_review/workspace.py")
    yaml_cfg = {
        "lane-selection": {
            "require-labels": ["needs-review"],
            "exclude-labels": ["blocked"],
            "priority": ["severity:critical"],
            "tiebreak": "newest",
        }
    }
    cfg = workspace._derive_lane_selection_cfg(yaml_cfg, active_lane_label="active-lane")
    assert cfg["require-labels"] == ["needs-review"]
    assert cfg["priority"] == ["severity:critical"]
    assert cfg["tiebreak"] == "newest"
    assert "active-lane" in cfg["exclude-labels"]
    assert "blocked" in cfg["exclude-labels"]
```

- [ ] **Step 3: Run failing test**

Run: `/usr/bin/python3 -m pytest tests/test_workflow_code_review_lane_selection_workspace.py -v`
Expected: All fail — `_derive_lane_selection_cfg` doesn't exist.

- [ ] **Step 4: Add helper + thread through workspace**

In `workflows/code_review/workspace.py`, add a module-level helper near the top (before `build_workspace` or whatever the main builder is named — search for `def build_workspace` or `def make_workspace`):

```python
def _derive_lane_selection_cfg(yaml_cfg, *, active_lane_label):
    """Synthesize the parsed lane-selection config from raw workflow.yaml.

    Lazy-import to avoid a circular-import at module load (workspace is the
    central bootstrap site).
    """
    try:
        from .lane_selection import parse_config
    except ImportError:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "daedalus_lane_selection_for_workspace",
            Path(__file__).resolve().parent / "lane_selection.py",
        )
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        parse_config = _mod.parse_config
    return parse_config(workflow_yaml=yaml_cfg or {}, active_lane_label=active_lane_label)
```

Then in the workspace builder, after the existing `active_lane_label = str(...)` line (~322), add:

```python
lane_selection_cfg = _derive_lane_selection_cfg(yaml_cfg, active_lane_label=active_lane_label)
```

(Use the local name for the raw yaml dict — search the function for whatever variable holds it. The Phase-1 audit suggests it's named `yaml_cfg` in this file.)

Add to the `ns = SimpleNamespace(...)` block:

```python
LANE_SELECTION_CFG=lane_selection_cfg,
```

Update the call-site at workspace.py:781 (`pick_next_lane_issue(items, active_lane_label=ns.ACTIVE_LANE_LABEL)`) to also pass `lane_selection_cfg=ns.LANE_SELECTION_CFG`. There may be a similar call to `pick_next_lane_issue_from_repo` elsewhere — `grep` and update both:

```bash
grep -n "pick_next_lane_issue\(\|pick_next_lane_issue_from_repo" workflows/code_review/*.py
```

- [ ] **Step 5: Run test + full suite**

Run: `/usr/bin/python3 -m pytest tests/test_workflow_code_review_lane_selection_workspace.py -v`
Expected: 2 passed.

Run: `/usr/bin/python3 -m pytest -q 2>&1 | tail -5`
Expected: 313 + 2 = 315 passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add workflows/code_review/workspace.py tests/test_workflow_code_review_lane_selection_workspace.py
git commit -m "feat(workspace): thread lane_selection_cfg through to the picker

build_workspace now derives a parsed lane-selection config at bootstrap
and exposes it via ns.LANE_SELECTION_CFG. The pick_next_lane_issue
call site passes it through. Workspaces with no lane-selection: block
get the synthesized defaults (full back-compat)."
```

---

### Task 3.2: Verify the live YoYoPod workflow.yaml validates

- [ ] **Step 1: Validate live yaml against new schema**

Run:
```bash
/usr/bin/python3 -c "
import yaml, jsonschema
schema = yaml.safe_load(open('workflows/code_review/schema.yaml'))
config = yaml.safe_load(open('/home/radxa/.hermes/workflows/yoyopod/config/workflow.yaml'))
jsonschema.validate(config, schema)
print('OK — live workflow.yaml validates')
"
```
Expected: `OK — live workflow.yaml validates`. (The live yaml has no `lane-selection:` block; default synthesis kicks in.)

- [ ] **Step 2: No commit (verification only)**

If it fails, STOP — debugging needed before proceeding to Phase 4.

---

## Phase 4: Docs

### Task 4.1: Add operator-facing example

**Files:**
- Modify: `skills/operator/SKILL.md` (or create new doc if SKILL.md is too crowded — operator's call)

- [ ] **Step 1: Find existing operator skill**

Run: `ls skills/operator/ 2>&1 | head -5`
Expected: `SKILL.md` exists (per project-instruction CLAUDE.md mentioning it).

- [ ] **Step 2: Append a Lane Selection section**

Append to `skills/operator/SKILL.md` (or create `docs/lane-selection.md` if SKILL.md is hard to extend):

```markdown
## Configurable Lane Selection

Daedalus picks "the next issue to promote to active lane" via `pick_next_lane_issue`.
Default behavior: any open issue not yet labeled `active-lane`, sorted by `[P1]/[P2]`
title priority, then issue number ASC. To customize, add a `lane-selection:` block
to `workflow.yaml`:

```yaml
# Severity-priority routing example
lane-selection:
  require-labels:
    - needs-review              # only promote issues marked ready
  exclude-labels:
    - blocked                   # operator escape-hatch
    - do-not-touch
  priority:
    - severity:critical         # higher in list = higher priority
    - severity:high
    - severity:medium
  tiebreak: oldest              # within bucket: oldest createdAt wins
```

All five fields are optional. The `active-lane` label is auto-injected into
`exclude-labels` so the picker can never select an already-promoted lane.

`tiebreak` options: `oldest` (default), `newest`, `random`.

When `priority:` is configured, label priority becomes primary and the legacy
`[P1]`/`[P2]` title priority is demoted to a tertiary tiebreak. When `priority:`
is empty, title priority remains primary (full back-compat).
```

- [ ] **Step 3: Commit**

```bash
git add skills/operator/SKILL.md
git commit -m "docs(operator): document lane-selection config block

Adds a real-world severity-priority routing example with all five
fields illustrated. Notes the auto-exclusion of active-lane and the
title-priority interaction (primary when label priority empty,
tertiary otherwise)."
```

---

## Phase 5: Cleanup

### Task 5.1: Final audit

- [ ] **Step 1: Full test suite**

Run: `/usr/bin/python3 -m pytest -q 2>&1 | tail -5`
Expected: 315+ passed, 0 failed.

- [ ] **Step 2: Grep for missed wiring**

Run:
```bash
grep -rn "TODO\|FIXME\|XXX" workflows/code_review/lane_selection.py 2>&1 | grep -v ".pyc:"
```
Expected: empty.

- [ ] **Step 3: Verify install payload**

Run: `grep -A 25 "PAYLOAD_ITEMS\s*=" scripts/install.py | head -30`
Expected: includes `workflows` (which sweeps in `workflows/code_review/lane_selection.py` automatically — no separate entry needed since the parent dir is already in PAYLOAD_ITEMS).

- [ ] **Step 4: Verify no other call site was missed**

Run: `grep -rn "pick_next_lane_issue\b" workflows/ tests/ 2>&1 | grep -v __pycache__ | grep -v ".pyc:"`

For each call site outside `tests/`, confirm `lane_selection_cfg` is passed (or the no-cfg path is intentional, e.g. test fixtures).

- [ ] **Step 5: Branch summary**

Run: `git log --oneline main..HEAD`

Should look like:
- `feat(schema): add lane-selection block ...`
- `feat(lane-selection): parse_config synthesizes defaults`
- `feat(github): pick_next_lane_issue accepts lane_selection_cfg`
- `feat(workspace): thread lane_selection_cfg through to the picker`
- `docs(operator): document lane-selection config block`
- (plus the spec + this plan)

If anything's missing, STOP and report.

---

## Acceptance criteria check (against spec §11)

- [ ] Schema validates `lane-selection:` block; rejects unknown fields + invalid `tiebreak`: Task 1.1
- [ ] Live YoYoPod workflow.yaml validates: Task 3.2
- [ ] No `lane-selection:` block → identical behavior: Task 2.2's back-compat tests
- [ ] All five selection axes covered: Task 2.2's test file
- [ ] `repository.active-lane-label` auto-excluded: Task 2.1's test
- [ ] Title `[P1]/[P2]` priority interaction tested both directions: Task 2.2's title-priority tests
- [ ] All existing tests pass (baseline 285): every task verifies
- [ ] Doc example present: Task 4.1
