"""Lane decisions, transitions, actor outputs, and release mechanics."""

from __future__ import annotations

from typing import Any

from sprints.workflows import runtime_sessions as sessions
from sprints.core.config import WorkflowConfig
from sprints.workflows.lane_state import (
    clear_engine_retry,
    concurrency_config,
    release_lane_lease,
    active_lanes,
    lane_recovery_artifacts,
    set_lane_operator_attention,
    set_lane_status,
)


def validate_actor_capacity(
    *,
    config: WorkflowConfig,
    actor_name: str,
    dispatch_counts: dict[str, int],
) -> None:
    concurrency = concurrency_config(config)
    actor_limits = (
        concurrency.get("actor_limits")
        if isinstance(concurrency.get("actor_limits"), dict)
        else {}
    )
    limit = int(actor_limits.get(actor_name) or concurrency["max_lanes"])
    if dispatch_counts.get(actor_name, 0) >= limit:
        raise RuntimeError(f"concurrency limit reached for actor {actor_name}")


def actor_concurrency_usage(*, config: WorkflowConfig, state: Any) -> dict[str, int]:
    return sessions.actor_concurrency_usage(
        config=config,
        lanes=active_lanes(state),
    )


def actor_capacity_snapshot(
    *, concurrency: dict[str, Any], actor_usage: dict[str, int]
) -> dict[str, dict[str, int]]:
    capacities = (
        concurrency.get("actor_limits")
        if isinstance(concurrency.get("actor_limits"), dict)
        else {}
    )
    return {
        actor_name: {
            "limit": int(limit),
            "running": int(actor_usage.get(actor_name, 0)),
            "available": max(int(limit) - int(actor_usage.get(actor_name, 0)), 0),
        }
        for actor_name, limit in sorted(capacities.items())
    }


def guard_actor_dispatch(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    actor_name: str,
    stage_name: str,
) -> dict[str, Any]:
    lane_id = str(lane.get("lane_id") or "").strip()
    conflicts = sessions.actor_dispatch_conflicts(
        config=config,
        lane=lane,
        lane_id=lane_id,
        actor_name=actor_name,
        stage_name=stage_name,
    )
    if not conflicts:
        return {"allowed": True, "conflicts": []}
    set_lane_operator_attention(
        config=config,
        lane=lane,
        reason="duplicate_dispatch_guard",
        message=(
            f"refusing to dispatch {actor_name} for lane {lane_id}; "
            "active runtime work is already recorded"
        ),
        artifacts=lane_recovery_artifacts(
            lane,
            {
                "actor": actor_name,
                "stage": stage_name,
                "conflicts": conflicts,
            },
        ),
    )
    return {
        "allowed": False,
        "reason": "duplicate_dispatch_guard",
        "conflicts": conflicts,
    }


def complete_lane(*, config: WorkflowConfig, lane: dict[str, Any], reason: str) -> None:
    lane["pending_retry"] = None
    clear_engine_retry(config=config, lane=lane)
    set_lane_status(
        config=config,
        lane=lane,
        status="complete",
        reason=reason,
        actor=None,
    )
    release_lane_lease(config=config, lane=lane, reason=reason)


def release_lane(*, config: WorkflowConfig, lane: dict[str, Any], reason: str) -> None:
    lane["pending_retry"] = None
    clear_engine_retry(config=config, lane=lane)
    set_lane_status(
        config=config,
        lane=lane,
        status="released",
        reason=reason,
        actor=None,
    )
    release_lane_lease(config=config, lane=lane, reason=reason)


def record_actor_runtime_start(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    actor_name: str,
    stage_name: str,
    runtime_meta: dict[str, Any],
) -> None:
    sessions.record_actor_runtime_start(
        config=config,
        lane=lane,
        actor_name=actor_name,
        stage_name=stage_name,
        runtime_meta=runtime_meta,
    )


def record_actor_dispatch_planned(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    actor_name: str,
    stage_name: str,
    runtime_meta: dict[str, Any],
) -> dict[str, Any]:
    return sessions.record_actor_dispatch_planned(
        config=config,
        lane=lane,
        actor_name=actor_name,
        stage_name=stage_name,
        runtime_meta=runtime_meta,
    )


def record_actor_runtime_progress(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    runtime_meta: dict[str, Any],
) -> None:
    sessions.record_actor_runtime_progress(
        config=config,
        lane=lane,
        runtime_meta=runtime_meta,
    )


def record_actor_runtime_result(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    runtime_meta: dict[str, Any],
    status: str,
) -> None:
    sessions.record_actor_runtime_result(
        config=config,
        lane=lane,
        runtime_meta=runtime_meta,
        status=status,
    )


def record_actor_runtime_interrupted(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    reason: str,
    message: str,
    age_seconds: int,
) -> None:
    sessions.record_actor_runtime_interrupted(
        config=config,
        lane=lane,
        reason=reason,
        message=message,
        age_seconds=age_seconds,
    )


def save_scheduler_snapshot(*, config: WorkflowConfig, state: Any) -> None:
    sessions.save_scheduler_snapshot(
        config=config,
        lanes=state.lanes.values(),
    )


