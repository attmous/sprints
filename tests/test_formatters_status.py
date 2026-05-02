"""Per-command formatter for /daedalus status."""
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1] / "daedalus"


def load_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fmt():
    return load_module("daedalus_formatters_status_test", "formatters.py")


def _example_status() -> dict:
    return {
        "runtime_status": "running",
        "current_mode": "active",
        "active_orchestrator_instance_id": "daedalus-active-workflow-example",
        "schema_version": 3,
        "lane_count": 14,
        "db_path": "/home/x/.hermes/workflows/workflow-example/runtime/state/daedalus/daedalus.db",
        "event_log_path": "/home/x/.hermes/workflows/workflow-example/runtime/memory/daedalus-events.jsonl",
        "latest_heartbeat_at": "2026-04-26T22:43:01Z",
    }


def test_format_status_includes_title_and_state():
    fmt = _fmt()
    out = fmt.format_status(_example_status(), use_color=False, now_iso="2026-04-26T22:43:18Z")
    assert "Daedalus runtime" in out
    assert "running" in out
    # Mode appears alongside state
    assert "active" in out


def test_format_status_includes_owner_and_schema():
    fmt = _fmt()
    out = fmt.format_status(_example_status(), use_color=False, now_iso="2026-04-26T22:43:18Z")
    assert "daedalus-active-workflow-example" in out
    assert "v3" in out or "schema" in out


def test_format_status_includes_lane_count():
    fmt = _fmt()
    out = fmt.format_status(_example_status(), use_color=False, now_iso="2026-04-26T22:43:18Z")
    assert "14" in out


def test_format_status_paths_section_includes_both_paths():
    fmt = _fmt()
    out = fmt.format_status(_example_status(), use_color=False, now_iso="2026-04-26T22:43:18Z")
    assert "daedalus.db" in out
    assert "daedalus-events.jsonl" in out


def test_format_status_heartbeat_renders_as_clock_with_age():
    fmt = _fmt()
    out = fmt.format_status(_example_status(), use_color=False, now_iso="2026-04-26T22:43:18Z")
    assert "22:43:01" in out
    assert "17s ago" in out


def test_format_status_handles_missing_optional_fields():
    fmt = _fmt()
    minimal = {"runtime_status": "blocked", "current_mode": None, "lane_count": 0}
    out = fmt.format_status(minimal, use_color=False)
    assert "blocked" in out
    # No crash on missing keys; em-dash for empty values
    assert "—" in out


def test_format_status_no_raw_python_bools_leak():
    fmt = _fmt()
    minimal = {"runtime_status": "running", "current_mode": "active", "lane_count": 0,
               "active_orchestrator_instance_id": "x"}
    out = fmt.format_status(minimal, use_color=False)
    assert " True" not in out
    assert " False" not in out


def test_format_status_issue_runner_renders_scheduler_and_tokens():
    fmt = _fmt()
    result = {
        "workflow": "issue-runner",
        "workflowRoot": "/tmp/attmous-daedalus-issue-runner",
        "health": "healthy",
        "tracker": {
            "kind": "github",
            "path": "/tmp/repo",
            "issueCount": 12,
            "eligibleCount": 3,
        },
        "scheduler": {
            "max_concurrent_agents": 2,
            "running": [{"issue_id": "123"}],
            "retry_queue": [{"issue_id": "124"}],
            "runtime_totals": {
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
                "rate_limits": {"requests_remaining": 99},
            },
        },
        "selectedIssue": {
            "identifier": "#123",
            "title": "Important issue",
            "state": "open",
        },
        "lastRun": {
            "ok": True,
            "attempt": 2,
            "updatedAt": "2026-04-30T12:00:00Z",
        },
        "metrics": {
            "tokens": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
            "rate_limits": {"requests_remaining": 99},
        },
    }
    out = fmt.format_status(result, use_color=False, now_iso="2026-04-30T12:00:15Z")
    assert "Issue runner" in out
    assert "github" in out
    assert "running" in out and "1" in out
    assert "retry" in out and "1" in out
    assert "#123" in out
    assert "Important issue" in out
    assert "18" in out
    assert "requests_remaining" in out
