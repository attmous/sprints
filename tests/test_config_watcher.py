"""S-2 tests: ConfigWatcher (mtime-poll hot-reload) — Symphony §6.2."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


_VALID_YAML = textwrap.dedent("""\
    workflow: code-review
    schema-version: 1
    instance:
      name: test-instance
      engine-owner: hermes
    repository:
      local-path: /tmp/test
      github-slug: org/repo
      active-lane-label: active-lane
    runtimes:
      r1:
        kind: claude-cli
        max-turns-per-invocation: 4
        timeout-seconds: 60
    agents:
      coder:
        t1:
          name: coder
          model: claude
          runtime: r1
      internal-reviewer:
        name: internal
        model: claude
        runtime: r1
      external-reviewer:
        enabled: false
        name: external
    gates:
      internal-review: {}
      external-review: {}
      merge: {}
    triggers:
      lane-selector:
        type: github-issue-label
        label: active-lane
    storage:
      ledger: ledger.json
      health: health.json
      audit-log: audit.log
""")


def test_parse_and_validate_returns_snapshot(tmp_path):
    from workflows.code_review.config_watcher import parse_and_validate

    p = tmp_path / "workflow.yaml"
    p.write_text(_VALID_YAML)
    snap = parse_and_validate(p)
    assert snap.config["workflow"] == "code-review"
    assert snap.source_mtime == p.stat().st_mtime
    assert snap.loaded_at > 0


def test_parse_and_validate_raises_on_yaml_syntax_error(tmp_path):
    from workflows.code_review.config_watcher import parse_and_validate, ParseError

    p = tmp_path / "workflow.yaml"
    p.write_text("workflow: [unclosed\n")
    with pytest.raises(ParseError):
        parse_and_validate(p)


def test_parse_and_validate_raises_on_schema_violation(tmp_path):
    from workflows.code_review.config_watcher import parse_and_validate, ValidationError

    p = tmp_path / "workflow.yaml"
    p.write_text("workflow: code-review\n")  # missing required fields
    with pytest.raises(ValidationError):
        parse_and_validate(p)


def _seed_snapshot(tmp_path: Path):
    """Helper: write valid yaml + return (path, snapshot)."""
    from workflows.code_review.config_watcher import parse_and_validate

    p = tmp_path / "workflow.yaml"
    p.write_text(_VALID_YAML)
    return p, parse_and_validate(p)


def test_watcher_poll_swaps_on_mtime_change(tmp_path):
    import os
    from workflows.code_review.config_snapshot import AtomicRef
    from workflows.code_review.config_watcher import ConfigWatcher

    p, initial = _seed_snapshot(tmp_path)
    ref = AtomicRef(initial)
    events: list[tuple[str, dict]] = []
    w = ConfigWatcher(p, ref, lambda t, d: events.append((t, d)))

    # Edit file with a future mtime
    new_yaml = _VALID_YAML.replace("test-instance", "edited-instance")
    p.write_text(new_yaml)
    os.utime(p, (initial.source_mtime + 5, initial.source_mtime + 5))

    w.poll()
    assert ref.get().config["instance"]["name"] == "edited-instance"
    assert any(t == "daedalus.config_reloaded" for t, _ in events)


def test_watcher_poll_no_change_is_noop(tmp_path):
    from workflows.code_review.config_snapshot import AtomicRef
    from workflows.code_review.config_watcher import ConfigWatcher

    p, initial = _seed_snapshot(tmp_path)
    ref = AtomicRef(initial)
    events: list[tuple[str, dict]] = []
    w = ConfigWatcher(p, ref, lambda t, d: events.append((t, d)))

    w.poll()
    w.poll()
    assert ref.get() is initial
    assert events == []
