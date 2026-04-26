"""Every top-level field in the result dict appears in the rendered text panel.

This catches accidental field drops as new fields are added to result dicts.
"""
import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name, relative_path):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fmt():
    return load_module("daedalus_formatters_no_info_loss_test", "formatters.py")


_ISO_TIMESTAMP_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}:\d{2})")


def _values_in_text(result, text):
    """Return list of (path, value) pairs whose value-string is missing from text.

    Treats nested dicts/lists by walking; ignores values that are themselves
    dicts/lists (only leaf values must be visible). Booleans rendered as
    yes/no/enabled/disabled are tolerated via render_bool semantics, so we
    only check non-bool primitives.

    ISO-8601 timestamps are intentionally rendered as ``HH:MM:SS UTC (Ns ago)``
    by ``format_timestamp``; treat the clock component as evidence the value
    was surfaced.
    """
    fmt = _fmt()
    missing = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [str(i)])
        else:
            if isinstance(node, bool) or node is None:
                return  # booleans are translated; None is em-dash
            value_str = str(node)
            if not value_str:
                return
            # Heuristic: values longer than 6 chars must appear verbatim.
            # Skip very short strings (likely common tokens like "1", "x").
            if len(value_str) >= 6 and value_str not in text:
                # ISO timestamps render as "HH:MM:SS UTC (Ns ago)"; tolerate.
                m = _ISO_TIMESTAMP_RE.match(value_str)
                if m and m.group(1) in text:
                    return
                missing.append((".".join(path), value_str))

    walk(result, [])
    return missing


def test_status_no_info_loss():
    fmt = _fmt()
    result = {
        "runtime_status": "running", "current_mode": "active",
        "active_orchestrator_instance_id": "daedalus-active-yoyopod",
        "schema_version": 3, "lane_count": 14,
        "db_path": "/path/to/daedalus.db",
        "event_log_path": "/path/to/daedalus-events.jsonl",
        "latest_heartbeat_at": "2026-04-26T22:43:01Z",
    }
    out = fmt.format_status(result, use_color=False, now_iso="2026-04-26T22:43:18Z")
    missing = _values_in_text(result, out)
    assert not missing, f"Missing in status output: {missing}"


def test_active_gate_status_no_info_loss():
    fmt = _fmt()
    result = {
        "allowed": True, "reasons": [],
        "execution": {"active_execution_enabled": True},
        "primary_owner": "daedalus",
        "runtime": {"runtime_status": "running", "current_mode": "active"},
    }
    out = fmt.format_active_gate_status(result, use_color=False)
    missing = _values_in_text(result, out)
    assert not missing, f"Missing in active-gate output: {missing}"


def test_doctor_no_info_loss():
    fmt = _fmt()
    result = {
        "overall_status": "pass",
        "checks": [
            {"code": "missing_lease", "status": "pass", "summary": "Runtime lease present"},
        ],
    }
    out = fmt.format_doctor(result, use_color=False)
    missing = _values_in_text(result, out)
    assert not missing, f"Missing in doctor output: {missing}"


def test_service_status_no_info_loss():
    fmt = _fmt()
    result = {
        "service_name": "daedalus-active@yoyopod.service",
        "service_mode": "active",
        "installed": True, "enabled": True, "active": True,
        "unit_path": "/path/unit.service",
        "properties": {"ExecMainPID": "12345"},
    }
    out = fmt.format_service_status(result, use_color=False)
    missing = _values_in_text(result, out)
    assert not missing, f"Missing in service-status output: {missing}"
