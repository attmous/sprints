"""Small shared workflow state helpers."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.core.paths import runtime_paths
from sprints.engine import EngineStore

TERMINAL_LANE_STATUSES = {"complete", "released"}


def lane_mapping(lane: dict[str, Any], key: str) -> dict[str, Any]:
    value = lane.get(key)
    if isinstance(value, dict):
        return value
    lane[key] = {}
    return lane[key]


def lane_list(lane: dict[str, Any], key: str) -> list[Any]:
    value = lane.get(key)
    if isinstance(value, list):
        return value
    lane[key] = []
    return lane[key]


def lane_stage(lane: dict[str, Any]) -> str:
    return str(lane.get("stage") or "").strip()


def lane_is_terminal(lane: dict[str, Any]) -> bool:
    return str(lane.get("status") or "").strip() in TERMINAL_LANE_STATUSES


def engine_store(config: WorkflowConfig) -> EngineStore:
    return EngineStore(
        db_path=runtime_paths(config.workflow_root)["db_path"],
        workflow=config.workflow_name,
    )


def iso_to_epoch(value: str, *, default: float) -> float:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return default


def epoch_to_iso(value: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def positive_int(config: dict[str, Any], *keys: str, default: int) -> int:
    for key in keys:
        value = config.get(key)
        if value in (None, ""):
            continue
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return default
    return default


def nonnegative_int(config: dict[str, Any], *keys: str, default: int) -> int:
    for key in keys:
        value = config.get(key)
        if value in (None, ""):
            continue
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return default
    return default


def positive_float(
    config: dict[str, Any],
    *keys: str,
    default: float,
    min_value: float = 0.01,
) -> float:
    for key in keys:
        value = config.get(key)
        if value in (None, ""):
            continue
        try:
            return max(float(value), min_value)
        except (TypeError, ValueError):
            return default
    return default


def configured_bool(config: dict[str, Any], *keys: str, default: bool) -> bool:
    for key in keys:
        value = config.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default
