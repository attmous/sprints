"""Apply actor-driven route decisions to lanes and runtimes."""

from __future__ import annotations

from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.core.contracts import WorkflowPolicy
from sprints.workflows.board import set_lane_board_state
from sprints.workflows.board_state import BoardState
from sprints.workflows.dispatch import (
    actor_dispatch_mode,
    dispatch_stage_actor_background,
    run_stage_actor,
)
from sprints.workflows.lane_state import (
    clear_engine_retry,
    lane_summary,
    lane_transition_side,
    record_engine_lane,
    set_lane_operator_attention,
    set_lane_status,
)
from sprints.workflows.orchestrator import OrchestratorDecision
from sprints.workflows.retries import lane_retry_is_due, queue_lane_retry
from sprints.workflows.routes import ActorRoute
from sprints.workflows.sessions import active_actor_dispatch
from sprints.workflows.state_io import WorkflowState, persist_runtime_state
from sprints.workflows.transitions import release_lane, validate_actor_capacity


_DISPATCHABLE_STATUSES = {"claimed", "waiting", "review_waiting"}


def apply_actor_route(
    *,
    config: WorkflowConfig,
    policy: WorkflowPolicy,
    state: WorkflowState,
    lane: dict[str, Any],
    route: ActorRoute,
    dispatch_counts: dict[str, int],
) -> dict[str, Any]:
    if route.action == "hold":
        return _route_result(lane=lane, route=route, status="held")
    if route.action == "wait_review":
        _move_lane_stage(
            config=config,
            lane=lane,
            stage=route.stage or "review",
            status="review_waiting",
            reason=route.reason or "waiting for shared review",
        )
        record_engine_lane(config=config, lane=lane)
        persist_runtime_state(config=config, state=state)
        return _route_result(lane=lane, route=route, status="waiting")
    if route.action == "operator_attention":
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_driven_route_invalid",
            message=route.reason or "actor-driven route requires operator attention",
            artifacts={"route": route.to_dict()},
        )
        return _route_result(lane=lane, route=route, status="operator_attention")
    if route.action == "move_board":
        return _apply_board_move_route(
            config=config, state=state, lane=lane, route=route
        )
    if route.action == "release":
        release_lane(config=config, lane=lane, reason=route.reason or "released")
        record_engine_lane(config=config, lane=lane)
        persist_runtime_state(config=config, state=state)
        return _route_result(lane=lane, route=route, status="released")
    if route.action != "dispatch":
        return _route_result(lane=lane, route=route, status="skipped")

    stage = str(route.stage or "")
    actor = str(route.actor or "")
    mode = str(route.mode or "")
    if not stage or stage not in config.stages:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_driven_route_invalid",
            message=f"actor-driven route selected unknown stage {stage!r}",
            artifacts={"route": route.to_dict()},
        )
        return _route_result(lane=lane, route=route, status="operator_attention")
    if actor not in config.actors or actor not in config.stages[stage].actors:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_driven_route_invalid",
            message=f"actor-driven route selected actor {actor!r} outside stage {stage!r}",
            artifacts={"route": route.to_dict()},
        )
        return _route_result(lane=lane, route=route, status="operator_attention")
    if not _lane_can_dispatch(lane):
        return _route_result(lane=lane, route=route, status="held")
    try:
        validate_actor_capacity(
            config=config, actor_name=actor, dispatch_counts=dispatch_counts
        )
    except RuntimeError as exc:
        return _route_result(
            lane=lane,
            route=route,
            status="held",
            extra={"reason": str(exc)},
        )
    if route.board_state == BoardState.TODO.value:
        transition = set_lane_board_state(
            config=config, lane=lane, target=BoardState.IN_PROGRESS
        )
        if transition.get("status") == "failed":
            retry = _queue_route_retry(
                config=config,
                lane=lane,
                route=route,
                reason=str(transition.get("error") or "failed to set board state"),
                inputs={
                    "board_state_target": BoardState.IN_PROGRESS.value,
                    "mode": mode or "implement",
                },
            )
            persist_runtime_state(config=config, state=state)
            return _route_result(
                lane=lane,
                route=route,
                status="retry_queued",
                extra={
                    "transition": transition,
                    "retry": retry,
                },
            )
        persist_runtime_state(config=config, state=state)
    _move_lane_stage(
        config=config,
        lane=lane,
        stage=stage,
        status=None if str(lane.get("status") or "") == "retry_queued" else "claimed",
        reason=route.reason or f"dispatch {actor}",
    )
    persist_runtime_state(config=config, state=state)
    inputs = dict(route.inputs or {})
    if mode:
        inputs["mode"] = mode
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
    if not _dispatch_was_accepted(dispatch):
        return _route_result(
            lane=lane,
            route=route,
            status="held",
            extra={"dispatch": dispatch},
        )
    dispatch_counts[actor] = dispatch_counts.get(actor, 0) + 1
    return _route_result(
        lane=lane,
        route=route,
        status="dispatched",
        extra={"dispatch": dispatch},
    )


def _apply_board_move_route(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    lane: dict[str, Any],
    route: ActorRoute,
) -> dict[str, Any]:
    target = str(route.target_board_state or "").strip()
    try:
        target_state = BoardState(target)
    except ValueError:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_driven_route_invalid",
            message=f"actor-driven route selected unknown board state {target!r}",
            artifacts={"route": route.to_dict()},
        )
        return _route_result(lane=lane, route=route, status="operator_attention")
    transition = set_lane_board_state(config=config, lane=lane, target=target_state)
    if transition.get("status") == "failed":
        retry = _queue_route_retry(
            config=config,
            lane=lane,
            route=route,
            reason=str(transition.get("error") or "failed to set board state"),
            inputs={"board_state_target": target_state.value},
        )
        persist_runtime_state(config=config, state=state)
        return _route_result(
            lane=lane,
            route=route,
            status="retry_queued",
            extra={"transition": transition, "retry": retry},
        )
    if route.stage:
        lane["pending_retry"] = None
        clear_engine_retry(config=config, lane=lane)
        _move_lane_stage(
            config=config,
            lane=lane,
            stage=route.stage,
            status="claimed",
            reason=route.reason or f"moved board state to {target_state.value}",
        )
    record_engine_lane(config=config, lane=lane)
    persist_runtime_state(config=config, state=state)
    return _route_result(
        lane=lane,
        route=route,
        status="board_moved",
        extra={"transition": transition},
    )


def _move_lane_stage(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    stage: str,
    status: str | None,
    reason: str,
) -> None:
    previous = lane_transition_side(lane)
    lane["stage"] = stage
    if status is None:
        return
    current_status = str(lane.get("status") or "").strip()
    if current_status == status and previous.get("stage") == stage:
        return
    set_lane_status(
        config=config,
        lane=lane,
        status=status,
        reason=reason,
        actor=None,
        previous=previous,
    )


def _lane_can_dispatch(lane: dict[str, Any]) -> bool:
    if active_actor_dispatch(lane):
        return False
    status = str(lane.get("status") or "").strip().lower()
    if status == "retry_queued":
        return lane_retry_is_due(lane)
    return status in _DISPATCHABLE_STATUSES


def _dispatch_was_accepted(dispatch: Any) -> bool:
    if not isinstance(dispatch, dict):
        return True
    if dispatch.get("allowed") is False:
        return False
    return str(dispatch.get("reason") or "") != "duplicate_dispatch_guard"


def _queue_route_retry(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    route: ActorRoute,
    reason: str,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    retry_inputs = {**dict(route.inputs or {}), **dict(inputs or {})}
    decision = OrchestratorDecision(
        decision="retry",
        stage=route.stage or str(lane.get("stage") or config.first_stage),
        lane_id=str(lane.get("lane_id") or ""),
        target=route.actor,
        reason=reason,
        inputs=retry_inputs,
    )
    return queue_lane_retry(config=config, lane=lane, decision=decision)


def _route_result(
    *,
    lane: dict[str, Any],
    route: ActorRoute,
    status: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "lane_id": lane.get("lane_id"),
        "status": status,
        "route": route.to_dict(),
        "lane": lane_summary(lane),
        **dict(extra or {}),
    }
