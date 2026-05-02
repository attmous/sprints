from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from workflows.change_delivery.config import change_delivery_storage_paths_from_config


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def change_delivery_storage_paths(
    workflow_root: Path,
    config: dict[str, Any] | None = None,
) -> dict[str, Path]:
    return change_delivery_storage_paths_from_config(workflow_root, config)


def default_idle_ledger(*, now_iso: str | None = None) -> dict[str, Any]:
    now_iso = now_iso or _now_iso()
    return {
        "schemaVersion": 6,
        "activeLane": None,
        "workflowIdle": True,
        "workflowState": "idle",
        "reviewState": "idle",
        "reviewLoopState": "idle",
        "branch": None,
        "openActiveLanePr": None,
        "blockedReason": None,
        "approval": {
            "status": "not-approved",
            "approvedAt": None,
            "approvedHeadSha": None,
            "pendingReason": None,
        },
        "reviews": {},
        "repairBrief": None,
        "updatedAt": now_iso,
    }


def default_health_payload(*, now_iso: str | None = None) -> dict[str, Any]:
    now_iso = now_iso or _now_iso()
    return {
        "workflow": "change-delivery",
        "health": "unknown",
        "ledger": {
            "workflowState": "idle",
            "reviewState": "idle",
            "workflowIdle": True,
        },
        "updatedAt": now_iso,
    }


def default_scheduler_payload(*, now_iso: str | None = None) -> dict[str, Any]:
    now_iso = now_iso or _now_iso()
    return {
        "workflow": "change-delivery",
        "updatedAt": now_iso,
        "running": [],
        "retry_queue": [],
        "runtime_sessions": {},
        "runtime_totals": {},
    }


def _write_json_if_missing(path: Path, payload: dict[str, Any]) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return True


def ensure_change_delivery_state_files(
    workflow_root: Path,
    config: dict[str, Any] | None = None,
    *,
    now_iso: str | None = None,
) -> dict[str, Any]:
    now_iso = now_iso or _now_iso()
    paths = change_delivery_storage_paths(workflow_root, config)
    created = {
        "ledger": _write_json_if_missing(paths["ledger"], default_idle_ledger(now_iso=now_iso)),
        "health": _write_json_if_missing(paths["health"], default_health_payload(now_iso=now_iso)),
        "scheduler": _write_json_if_missing(paths["scheduler"], default_scheduler_payload(now_iso=now_iso)),
        "audit_log": False,
    }
    audit_log = paths["audit_log"]
    if not audit_log.exists():
        audit_log.parent.mkdir(parents=True, exist_ok=True)
        audit_log.touch()
        created["audit_log"] = True
    return {
        "ok": True,
        "paths": {key: str(path) for key, path in paths.items()},
        "created": created,
    }
