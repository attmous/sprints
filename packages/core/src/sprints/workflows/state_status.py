"""Workflow and lane status projections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sprints.workflows import sessions
from sprints.core.config import WorkflowConfig
from sprints.core.contracts import load_workflow_contract
from sprints.workflows.lane_intake import tracker_facts
from sprints.workflows.lane_state import (
    active_lanes,
    actor_dispatch_summary,
    concurrency_config,
    count_lanes_with_status,
    engine_store,
    intake_auto_activate_config,
    recovery_config,
    retry_config,
    lane_is_terminal,
    lane_summary,
    retry_summary,
    side_effects_summary,
)
from sprints.workflows.state_projection import (
    project_engine_first_lanes,
    projected_lane_is_terminal,
)
from sprints.workflows.lane_transitions import (
    actor_capacity_snapshot,
    actor_concurrency_usage,
    decision_ready_lanes,
    lane_needs_orchestrator_decision,
)


def build_status(workflow_root: Path) -> dict[str, Any]:
    root = Path(workflow_root).expanduser().resolve()
    contract = load_workflow_contract(root)
    config = WorkflowConfig.from_raw(raw=contract.config, workflow_root=root)
    state: dict[str, Any] = {}
    if config.storage.state_path.exists():
        try:
            state = json.loads(config.storage.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    lane_status = build_lane_status(config=config, state=state)
    return {
        "workflow": config.workflow_name,
        "health": "ok" if state or lane_status.get("engine_lane_count") else "unknown",
        "workflow_root": str(root),
        "contract_path": str(contract.source_path),
        "state_path": str(config.storage.state_path),
        "audit_log_path": str(config.storage.audit_log_path),
        **lane_status,
        "canceling_count": 0,
    }


def build_workflow_facts(config: WorkflowConfig, state: Any) -> dict[str, Any]:
    tracker_facts_payload = tracker_facts(config=config, state=state)
    concurrency = concurrency_config(config)
    actor_usage = actor_concurrency_usage(config=config, state=state)
    current_active_lanes = active_lanes(state)
    current_decision_ready_lanes = _ready_lanes(config=config, state=state)
    terminal_lanes = [
        lane
        for lane in state.lanes.values()
        if isinstance(lane, dict) and lane_is_terminal(lane)
    ]
    terminal_by_status: dict[str, int] = {}
    for lane in terminal_lanes:
        status = str(lane.get("status") or "unknown")
        terminal_by_status[status] = terminal_by_status.get(status, 0) + 1
    lane_limit = concurrency["max_lanes"]
    available_lanes = max(lane_limit - len(current_active_lanes), 0)
    store = engine_store(config)
    return {
        "tracker": tracker_facts_payload,
        "engine": {
            "lanes": [lane_summary(lane) for lane in current_active_lanes],
            "lane_count": len(state.lanes),
            "terminal_lane_count": len(terminal_lanes),
            "terminal_lanes_by_status": terminal_by_status,
            "decision_ready_lanes": [
                lane_summary(lane) for lane in current_decision_ready_lanes
            ],
            "work_items": store.work_items(limit=50),
            "runtime_sessions": store.runtime_sessions(limit=50),
            "active_lane_count": len(current_active_lanes),
            "decision_ready_lane_count": len(current_decision_ready_lanes),
            "idle_reason": state.idle_reason,
            "due_retries": store.due_retries(limit=50),
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
            "actor_capacity": actor_capacity_snapshot(
                concurrency=concurrency, actor_usage=actor_usage
            ),
        },
        "intake": {"auto_activate": intake_auto_activate_config(config)},
        "recovery": recovery_config(config),
        "retry": retry_config(config),
    }


def build_lane_status(
    *, config: WorkflowConfig, state: dict[str, Any]
) -> dict[str, Any]:
    lanes = state.get("lanes") if isinstance(state.get("lanes"), dict) else {}
    state_active = [
        lane
        for lane in lanes.values()
        if isinstance(lane, dict) and not lane_is_terminal(lane)
    ]
    store = engine_store(config)
    engine_work_items = store.work_items(limit=500)
    engine_runtime_sessions = store.runtime_sessions(limit=500)
    projected_lanes = project_engine_first_lanes(config=config, state=state)
    active = [
        lane
        for lane in projected_lanes.values()
        if isinstance(lane, dict) and not projected_lane_is_terminal(lane)
    ]
    runtime_session_summaries = (
        engine_runtime_sessions
        or sessions.lane_runtime_session_summaries(lanes.values())
    )
    scheduler = store.read_scheduler() or {}
    runtime_totals = (
        scheduler.get("runtime_totals")
        if isinstance(scheduler.get("runtime_totals"), dict)
        else {}
    )
    retry_audit = build_retry_audit(state)
    due_retries = store.due_retries(limit=50)
    retry_wakeup = store.retry_wakeup()
    status = "running" if active else str(state.get("status") or "idle")
    latest_runs = store.latest_runs(limit=10)
    latest_tick_runs = store.latest_runs(mode="tick", limit=5)
    latest_tick_events = (
        store.events_for_run(str(latest_tick_runs[0]["run_id"]), limit=25)
        if latest_tick_runs
        else []
    )
    return {
        "status": status,
        "idle_reason": None if active else state.get("idle_reason"),
        "lane_status_source": "engine_work_items",
        "lane_count": len(projected_lanes),
        "state_lane_count": len(lanes),
        "engine_lane_count": len(engine_work_items),
        "active_lane_count": len(active),
        "decision_ready_count": len(
            [
                lane
                for lane in state_active
                if isinstance(lane, dict)
                and _lane_needs_runner_decision(config=config, lane=lane)
            ]
        ),
        "running_count": count_lanes_with_status(active, "running"),
        "retry_count": count_lanes_with_status(active, "retry_queued"),
        "operator_attention_count": count_lanes_with_status(
            active, "operator_attention"
        ),
        "total_tokens": int(runtime_totals.get("total_tokens") or 0),
        "runtime_totals": runtime_totals,
        "retry_policy": retry_config(config),
        "due_retries": due_retries,
        "retry_wakeup": retry_wakeup,
        "next_retry_due_in_seconds": retry_wakeup.get("next_due_in_seconds"),
        "retry_audit": retry_audit,
        "active_dispatch_count": len(
            [lane for lane in active if sessions.active_actor_dispatch(lane)]
        ),
        "dispatch_audit": build_dispatch_audit(state),
        "side_effect_count": sum(
            int(lane.get("side_effect_count") or 0)
            for lane in active
            if isinstance(lane, dict)
        ),
        "side_effect_audit": build_side_effect_audit(state),
        "latest_runs": latest_runs,
        "latest_tick_runs": latest_tick_runs,
        "latest_tick_events": latest_tick_events,
        "engine_work_items": engine_work_items,
        "engine_runtime_sessions": engine_runtime_sessions,
        "runtime_sessions": runtime_session_summaries,
        "operator_attention_lanes": [
            lane
            for lane in active
            if str(lane.get("status") or "") == "operator_attention"
        ],
        "retry_lanes": [
            lane for lane in active if str(lane.get("status") or "") == "retry_queued"
        ],
        "lanes": projected_lanes,
        "state_lanes": lanes,
    }


def _ready_lanes(*, config: WorkflowConfig, state: Any) -> list[dict[str, Any]]:
    if config.is_actor_driven():
        from sprints.workflows.route_rules import actor_driven_ready_lanes

        return actor_driven_ready_lanes(config=config, state=state)
    return decision_ready_lanes(state)


def _lane_needs_runner_decision(
    *, config: WorkflowConfig, lane: dict[str, Any]
) -> bool:
    if config.is_actor_driven():
        from sprints.workflows.route_rules import lane_needs_actor_driven_route

        return lane_needs_actor_driven_route(config=config, lane=lane)
    return lane_needs_orchestrator_decision(lane)


def build_retry_audit(state: dict[str, Any]) -> list[dict[str, Any]]:
    lanes = state.get("lanes") if isinstance(state.get("lanes"), dict) else {}
    audit: list[dict[str, Any]] = []
    for lane_id, lane in lanes.items():
        if not isinstance(lane, dict):
            continue
        retry = retry_summary(lane)
        if retry is None:
            continue
        audit.append(
            {
                "lane_id": lane.get("lane_id") or lane_id,
                "stage": lane.get("stage"),
                "status": lane.get("status"),
                **retry,
            }
        )
    return audit


def build_dispatch_audit(state: dict[str, Any]) -> list[dict[str, Any]]:
    lanes = state.get("lanes") if isinstance(state.get("lanes"), dict) else {}
    audit: list[dict[str, Any]] = []
    for lane_id, lane in lanes.items():
        if not isinstance(lane, dict):
            continue
        dispatch = actor_dispatch_summary(lane)
        if dispatch is None:
            continue
        audit.append(
            {
                "lane_id": lane.get("lane_id") or lane_id,
                "lane_status": lane.get("status"),
                **dispatch,
                "journal_count": len(lane.get("dispatch_journal") or []),
            }
        )
    return audit


def build_side_effect_audit(state: dict[str, Any]) -> list[dict[str, Any]]:
    lanes = state.get("lanes") if isinstance(state.get("lanes"), dict) else {}
    audit: list[dict[str, Any]] = []
    for lane_id, lane in lanes.items():
        if not isinstance(lane, dict):
            continue
        for entry in side_effects_summary(lane, limit=50):
            audit.append(
                {
                    "lane_id": lane.get("lane_id") or lane_id,
                    "lane_status": lane.get("status"),
                    **entry,
                }
            )
    return audit
