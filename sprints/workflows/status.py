"""Workflow and lane status projections."""

from __future__ import annotations

from typing import Any

from workflows import sessions
from workflows.config import WorkflowConfig
from workflows.intake import _tracker_facts
from workflows.lane_state import (
    _concurrency_config,
    _count_lanes_with_status,
    _engine_store,
    _intake_auto_activate_config,
    _lane_summary,
    _recovery_config,
    _retry_config,
    active_lanes,
    lane_is_terminal,
    lane_summary,
)
from workflows.transitions import (
    _actor_capacity_snapshot,
    actor_concurrency_usage,
    decision_ready_lanes,
    lane_needs_orchestrator_decision,
)


def build_workflow_facts(config: WorkflowConfig, state: Any) -> dict[str, Any]:
    tracker_facts = _tracker_facts(config=config, state=state)
    concurrency = _concurrency_config(config)
    actor_usage = actor_concurrency_usage(config=config, state=state)
    current_active_lanes = active_lanes(state)
    current_decision_ready_lanes = decision_ready_lanes(state)
    lane_limit = concurrency["max_lanes"]
    available_lanes = max(lane_limit - len(current_active_lanes), 0)
    return {
        "tracker": tracker_facts,
        "engine": {
            "lanes": state.lanes,
            "decision_ready_lanes": [
                lane_summary(lane) for lane in current_decision_ready_lanes
            ],
            "work_items": _engine_store(config).work_items(limit=200),
            "runtime_sessions": _engine_store(config).runtime_sessions(limit=200),
            "active_lane_count": len(current_active_lanes),
            "decision_ready_lane_count": len(current_decision_ready_lanes),
            "idle_reason": state.idle_reason,
            "due_retries": _engine_store(config).due_retries(limit=50),
            "capacity": {
                "max_lanes": lane_limit,
                "max_active_lanes": lane_limit,
                "available_lanes": available_lanes,
            },
        },
        "concurrency": {
            **concurrency,
            "lanes": {
                "limit": lane_limit,
                "active": len(current_active_lanes),
                "available": available_lanes,
            },
            "actor_usage": actor_usage,
            "actor_capacity": _actor_capacity_snapshot(
                concurrency=concurrency, actor_usage=actor_usage
            ),
        },
        "intake": {"auto_activate": _intake_auto_activate_config(config)},
        "recovery": _recovery_config(config),
        "retry": _retry_config(config),
    }


def build_lane_status(
    *, config: WorkflowConfig, state: dict[str, Any]
) -> dict[str, Any]:
    lanes = state.get("lanes") if isinstance(state.get("lanes"), dict) else {}
    active = [
        lane
        for lane in lanes.values()
        if isinstance(lane, dict) and not lane_is_terminal(lane)
    ]
    runtime_session_summaries = sessions.lane_runtime_session_summaries(lanes.values())
    scheduler = _engine_store(config).read_scheduler() or {}
    runtime_totals = (
        scheduler.get("runtime_totals")
        if isinstance(scheduler.get("runtime_totals"), dict)
        else {}
    )
    return {
        "status": state.get("status"),
        "idle_reason": state.get("idle_reason"),
        "lane_count": len(lanes),
        "active_lane_count": len(active),
        "decision_ready_count": len(
            [
                lane
                for lane in active
                if isinstance(lane, dict) and lane_needs_orchestrator_decision(lane)
            ]
        ),
        "running_count": _count_lanes_with_status(active, "running"),
        "retry_count": _count_lanes_with_status(active, "retry_queued"),
        "operator_attention_count": _count_lanes_with_status(
            active, "operator_attention"
        ),
        "total_tokens": int(runtime_totals.get("total_tokens") or 0),
        "runtime_totals": runtime_totals,
        "latest_runs": _engine_store(config).latest_runs(limit=10),
        "engine_work_items": _engine_store(config).work_items(limit=200),
        "engine_runtime_sessions": _engine_store(config).runtime_sessions(limit=200),
        "runtime_sessions": runtime_session_summaries,
        "operator_attention_lanes": [
            _lane_summary(lane)
            for lane in active
            if str(lane.get("status") or "") == "operator_attention"
        ],
        "retry_lanes": [
            _lane_summary(lane)
            for lane in active
            if str(lane.get("status") or "") == "retry_queued"
        ],
        "lanes": lanes,
    }
