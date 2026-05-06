"""Step-based tick runner for the code workflow."""

from __future__ import annotations

import json
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.core.loader import load_workflow_policy
from sprints.workflows.lane_intake import claim_new_lanes
from sprints.workflows.lane_reconcile import reconcile_lanes
from sprints.workflows.lane_state import (
    active_lanes,
    lane_mapping,
    record_engine_lane,
    set_lane_status,
)
from sprints.workflows.lane_transitions import (
    actor_concurrency_usage,
    release_lane,
    validate_actor_capacity,
)
from sprints.workflows.runtime_dispatch import (
    actor_dispatch_mode,
    dispatch_stage_actor_background,
    run_stage_actor,
)
from sprints.workflows.state_io import (
    WorkflowState,
    load_state,
    persist_runtime_state,
    refresh_state_status,
    save_state_event,
    validate_state,
    with_state_lock,
)
from sprints.workflows.step_labels import set_lane_step_label
from sprints.workflows.step_routes import StepRoute, next_step_after_actor_output, route_code_lane
from sprints.workflows.tick_journal import (
    finish_tick_journal,
    record_tick_journal,
    result_summaries,
    start_tick_journal,
)


def tick_step(config: WorkflowConfig) -> int:
    return with_state_lock(
        config=config,
        owner_role="workflow-step-tick",
        callback=lambda: tick_step_locked(config),
    )


def tick_step_locked(config: WorkflowConfig) -> int:
    journal = start_tick_journal(config=config)
    state: WorkflowState | None = None
    intake: dict[str, Any] = {}
    reconcile: dict[str, Any] = {}
    routes: list[StepRoute] = []
    results: list[dict[str, Any]] = []
    try:
        policy = load_workflow_policy(config.workflow_root)
        record_tick_journal(
            config=config,
            journal=journal,
            state=state,
            event="step.policy_loaded",
            details={"workflow_root": str(config.workflow_root)},
        )
        state = load_state(
            config.storage.state_path,
            workflow=config.workflow_name,
            first_stage=config.first_stage,
        )
        validate_state(config, state)
        record_tick_journal(
            config=config,
            journal=journal,
            state=state,
            event="step.state_loaded",
            details={"state_path": str(config.storage.state_path)},
        )
        reconcile = reconcile_lanes(config=config, state=state)
        record_tick_journal(
            config=config,
            journal=journal,
            state=state,
            event="step.reconciled",
            details={"reconcile": reconcile},
        )
        intake = claim_new_lanes(config=config, state=state)
        record_tick_journal(
            config=config,
            journal=journal,
            state=state,
            event="step.intake_completed",
            details={"intake": intake},
        )
        if not active_lanes(state):
            state.status = "idle"
            state.idle_reason = intake.get("reason") or "no active lanes"
            _save_step_tick(
                config=config,
                state=state,
                event="step_idle",
                extra={"intake": intake, "reconcile": reconcile},
            )
            finish_tick_journal(
                config=config,
                journal=journal,
                state=state,
                status="completed",
                terminal_event="step.idle",
                selected_count=0,
                completed_count=0,
            )
            return 0
        state.status = "running"
        state.idle_reason = None
        persist_runtime_state(config=config, state=state)
        dispatch_counts = actor_concurrency_usage(config=config, state=state)
        for lane in list(active_lanes(state)):
            route = route_code_lane(config=config, lane=lane)
            routes.append(route)
            result = apply_step_route(
                config=config,
                policy=policy,
                state=state,
                lane=lane,
                route=route,
                dispatch_counts=dispatch_counts,
            )
            results.append(result)
        refresh_state_status(state, idle_reason="no active lanes")
        _save_step_tick(
            config=config,
            state=state,
            event="step_tick",
            extra={
                "intake": intake,
                "reconcile": reconcile,
                "routes": [route.to_dict() for route in routes],
                "results": results,
            },
        )
        finish_tick_journal(
            config=config,
            journal=journal,
            state=state,
            status="completed",
            terminal_event="step.completed",
            selected_count=len(active_lanes(state)),
            completed_count=len(results),
            details={"results": result_summaries(results)},
        )
        return 0
    except Exception as exc:
        if state is not None:
            persist_runtime_state(config=config, state=state)
        finish_tick_journal(
            config=config,
            journal=journal,
            state=state,
            status="failed",
            terminal_event="step.failed",
            selected_count=len(active_lanes(state)) if state else 0,
            completed_count=len(results),
            error=exc,
        )
        raise


def apply_step_route(
    *,
    config: WorkflowConfig,
    policy: Any,
    state: WorkflowState,
    lane: dict[str, Any],
    route: StepRoute,
    dispatch_counts: dict[str, int],
) -> dict[str, Any]:
    if route.action == "hold":
        return {"lane_id": lane.get("lane_id"), "status": "held", "route": route.to_dict()}
    if route.action == "release":
        release_lane(config=config, lane=lane, reason=route.reason or "released")
        record_engine_lane(config=config, lane=lane)
        persist_runtime_state(config=config, state=state)
        return {
            "lane_id": lane.get("lane_id"),
            "status": "released",
            "route": route.to_dict(),
        }
    if route.action == "move_step":
        target = str(route.target_step or "")
        set_lane_step(
            config=config,
            state=state,
            lane=lane,
            target_step=target,
            reason=route.reason,
        )
        return {
            "lane_id": lane.get("lane_id"),
            "status": "step_moved",
            "route": route.to_dict(),
        }
    if route.action == "dispatch":
        actor = str(route.actor or "coder")
        validate_actor_capacity(
            config=config, actor_name=actor, dispatch_counts=dispatch_counts
        )
        inputs = {"step": route.step, **dict(route.inputs or {})}
        if actor_dispatch_mode(config) == "background":
            dispatch = dispatch_stage_actor_background(
                config=config,
                policy=policy,
                state=state,
                lane=lane,
                actor_name=actor,
                inputs=inputs,
            )
        else:
            dispatch = run_stage_actor(
                config=config,
                policy=policy,
                state=state,
                lane=lane,
                actor_name=actor,
                inputs=inputs,
            )
        dispatch_counts[actor] = dispatch_counts.get(actor, 0) + 1
        return {
            "lane_id": lane.get("lane_id"),
            "status": "dispatched",
            "route": route.to_dict(),
            "dispatch": dispatch,
        }
    return {"lane_id": lane.get("lane_id"), "status": "skipped", "route": route.to_dict()}


def apply_step_after_actor_output(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    lane: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    target = next_step_after_actor_output(lane=lane, output=output)
    if not target:
        return {
            "status": "held",
            "reason": "actor output did not request step transition",
        }
    return set_lane_step(
        config=config,
        state=state,
        lane=lane,
        target_step=target,
        reason=f"actor completed step {output.get('step') or lane.get('step')}",
    )


def set_lane_step(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    lane: dict[str, Any],
    target_step: str,
    reason: str,
) -> dict[str, Any]:
    transition = set_lane_step_label(
        config=config,
        lane=lane,
        target_step=target_step,
    )
    if transition.get("status") == "failed":
        raise RuntimeError(
            str(transition.get("error") or f"failed to move lane to {target_step}")
        )
    tracker = lane_mapping(lane, "tracker")
    tracker["step"] = target_step
    set_lane_status(
        config=config,
        lane=lane,
        status="claimed",
        actor=None,
        reason=reason or f"moved to {target_step}",
    )
    record_engine_lane(config=config, lane=lane)
    persist_runtime_state(config=config, state=state)
    return {
        "status": "step_moved",
        "target_step": target_step,
        "transition": transition,
    }


def _save_step_tick(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    event: str,
    extra: dict[str, Any] | None = None,
) -> None:
    save_state_event(config=config, state=state, event=event, extra=extra)
    print(json.dumps(state.to_dict(), indent=2, sort_keys=True))
