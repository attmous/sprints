"""Deterministic tick routing for actor-driven workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.core.contracts import WorkflowPolicy
from sprints.core.loader import load_workflow_policy
from sprints.trackers import build_tracker_client
from sprints.workflows.effects import (
    completed_side_effect,
    record_side_effect_failed,
    record_side_effect_skipped,
    record_side_effect_started,
    record_side_effect_succeeded,
    side_effect_key,
)
from sprints.workflows.board_state import (
    BoardState,
    desired_state_mutation,
    state_from_labels,
)
from sprints.workflows.dispatch import (
    actor_dispatch_mode,
    dispatch_stage_actor_background,
    run_stage_actor,
)
from sprints.workflows.intake import claim_new_lanes
from sprints.workflows.orchestrator import OrchestratorDecision
from sprints.workflows.lane_state import (
    active_lanes,
    append_engine_event,
    clear_engine_retry,
    completion_cleanup_retry_pending,
    lane_is_terminal,
    lane_summary,
    lane_transition_side,
    now_iso,
    record_engine_lane,
    refresh_lane_board_metadata,
    repository_path,
    set_lane_operator_attention,
    set_lane_status,
    tracker_config,
)
from sprints.workflows.reconcile import reconcile_lanes
from sprints.workflows.review_state import (
    review_actor_enabled,
    review_has_required_changes,
    review_required_changes,
    reviewer_actor_running,
)
from sprints.workflows.retries import lane_retry_is_due, queue_lane_retry
from sprints.workflows.sessions import active_actor_dispatch
from sprints.workflows.state_io import (
    WorkflowState,
    append_audit,
    load_state,
    persist_runtime_state,
    refresh_state_status,
    save_state_event,
    validate_state,
)
from sprints.workflows.tick_journal import (
    TickJournal,
    finish_tick_journal,
    record_tick_journal,
    result_summaries,
    start_tick_journal,
)
from sprints.workflows.transitions import (
    actor_concurrency_usage,
    release_lane,
    validate_actor_capacity,
)


_DISPATCHABLE_STATUSES = {"claimed", "waiting", "review_waiting"}


@dataclass(frozen=True)
class ActorRoute:
    lane_id: str
    board_state: str
    action: str
    stage: str | None = None
    actor: str | None = None
    mode: str | None = None
    target_board_state: str | None = None
    reason: str = ""
    inputs: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def tick_actor_driven_locked(
    config: WorkflowConfig, *, orchestrator_output: str
) -> int:
    if str(orchestrator_output or "").strip():
        raise RuntimeError("actor-driven ticks do not accept orchestrator output")

    journal = start_tick_journal(config=config, orchestrator_output=orchestrator_output)
    state: WorkflowState | None = None
    intake: dict[str, Any] = {}
    reconcile: dict[str, Any] = {}
    routes: list[ActorRoute] = []
    results: list[dict[str, Any]] = []
    selected_count = 0
    try:
        policy = load_workflow_policy(config.workflow_root)
        record_tick_journal(
            config=config,
            journal=journal,
            state=state,
            event="actor_driven.policy_loaded",
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
            event="actor_driven.state_loaded",
            details={"state_path": str(config.storage.state_path)},
        )
        reconcile = reconcile_lanes(config=config, state=state)
        record_tick_journal(
            config=config,
            journal=journal,
            state=state,
            event="actor_driven.reconciled",
            details={"reconcile": reconcile},
        )
        if _reconcile_blocks_routing(reconcile):
            state.status = "running" if active_lanes(state) else "idle"
            state.idle_reason = "reconcile failed; routing held"
            _save_actor_driven_tick(
                config=config,
                state=state,
                event="actor_driven_reconcile_blocked",
                extra={
                    "reconcile": reconcile,
                    "tick_journal": journal.to_dict(),
                },
            )
            finish_tick_journal(
                config=config,
                journal=journal,
                state=state,
                status="completed",
                terminal_event="actor_driven.reconcile_blocked",
                selected_count=len(active_lanes(state)),
                completed_count=0,
                details={"reconcile": reconcile},
            )
            return 0
        intake = claim_new_lanes(config=config, state=state)
        record_tick_journal(
            config=config,
            journal=journal,
            state=state,
            event="actor_driven.intake_completed",
            details={"intake": intake},
        )
        selected_count = len(active_lanes(state))
        if not active_lanes(state):
            state.status = "idle"
            state.idle_reason = intake.get("reason") or "no active lanes"
            _save_actor_driven_tick(
                config=config,
                state=state,
                event="actor_driven_idle",
                extra={
                    "intake": intake,
                    "reconcile": reconcile,
                    "tick_journal": journal.to_dict(),
                },
            )
            finish_tick_journal(
                config=config,
                journal=journal,
                state=state,
                status="completed",
                terminal_event="actor_driven.idle",
                selected_count=selected_count,
                completed_count=0,
                details={"reason": state.idle_reason},
            )
            return 0

        state.status = "running"
        state.idle_reason = None
        persist_runtime_state(config=config, state=state)
        dispatch_counts = actor_concurrency_usage(config=config, state=state)
        routes, results = route_actor_driven_lanes(
            config=config,
            policy=policy,
            state=state,
            dispatch_counts=dispatch_counts,
        )
        record_tick_journal(
            config=config,
            journal=journal,
            state=state,
            event="actor_driven.routes_applied",
            details={
                "routes": [route.to_dict() for route in routes],
                "results": result_summaries(results),
            },
        )
        refresh_state_status(state, idle_reason="no active lanes")
        _save_actor_driven_tick(
            config=config,
            state=state,
            event="actor_driven_tick",
            extra={
                "intake": intake,
                "reconcile": reconcile,
                "routes": [route.to_dict() for route in routes],
                "results": results,
                "tick_journal": journal.to_dict(),
            },
        )
        finish_tick_journal(
            config=config,
            journal=journal,
            state=state,
            status="completed",
            terminal_event="actor_driven.completed",
            selected_count=selected_count,
            completed_count=len(results),
            details={
                "route_count": len(routes),
                "result_count": len(results),
            },
        )
    except Exception as exc:
        journal_error: Exception | None = None
        try:
            if state is not None:
                _save_failed_actor_driven_tick(
                    config=config,
                    state=state,
                    intake=intake,
                    reconcile=reconcile,
                    routes=routes,
                    results=results,
                    error=exc,
                    tick_journal=journal,
                )
            else:
                record_tick_journal(
                    config=config,
                    journal=journal,
                    state=state,
                    event="actor_driven.failed_before_state",
                    details={
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                    severity="error",
                )
        except Exception as failed_save_error:
            journal_error = failed_save_error
        try:
            finish_tick_journal(
                config=config,
                journal=journal,
                state=state,
                status="failed",
                terminal_event="actor_driven.failed",
                selected_count=selected_count,
                completed_count=len(results),
                error=exc,
                details={
                    "intake": intake,
                    "reconcile": reconcile,
                    "routes": [route.to_dict() for route in routes],
                    "results": result_summaries(results),
                },
            )
        except Exception as failed_finish_error:
            journal_error = journal_error or failed_finish_error
        if journal_error is not None:
            raise journal_error from exc
        raise
    return 0


def route_actor_driven_lanes(
    *,
    config: WorkflowConfig,
    policy: WorkflowPolicy,
    state: WorkflowState,
    dispatch_counts: dict[str, int],
) -> tuple[list[ActorRoute], list[dict[str, Any]]]:
    routes: list[ActorRoute] = []
    results: list[dict[str, Any]] = []
    for lane in list(active_lanes(state)):
        route = route_lane(config=config, lane=lane)
        routes.append(route)
        result = apply_actor_route(
            config=config,
            policy=policy,
            state=state,
            lane=lane,
            route=route,
            dispatch_counts=dispatch_counts,
        )
        results.append(result)
    return routes, results


def route_lane(*, config: WorkflowConfig, lane: dict[str, Any]) -> ActorRoute:
    lane_id = str(lane.get("lane_id") or "")
    board_state = lane_board_state(config=config, lane=lane) or ""
    if lane_is_terminal(lane):
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="lane is terminal",
        )
    if active_actor_dispatch(lane):
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="actor dispatch already active",
        )
    lane_status = str(lane.get("status") or "").strip().lower()
    if lane_status == "running":
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="actor runtime is running",
        )
    if lane_status == "operator_attention":
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="operator attention required",
        )
    if lane_status == "workpad_failed":
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="workpad repair must succeed first",
        )
    if lane_status == "retry_queued" and not lane_retry_is_due(lane):
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="retry is not due yet",
        )
    if lane_status == "retry_queued":
        if completion_cleanup_retry_pending(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                reason="completion cleanup retry is runner-owned",
            )
        retry_route = _due_retry_route(lane=lane, board_state=board_state)
        if retry_route is not None:
            return retry_route
    if board_state == BoardState.BACKLOG.value:
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="release",
            reason="board state is backlog",
        )
    if board_state == BoardState.DONE.value:
        if not _done_release_verified(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                reason="done label is present but completion is not verified",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="release",
            reason="board state is done",
        )
    if board_state == BoardState.TODO.value:
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="deliver",
            actor="implementer",
            mode="implement",
            reason="todo lane enters implementation",
            inputs={"mode": "implement"},
        )
    if board_state == BoardState.IN_PROGRESS.value:
        if _last_actor_mode(lane) == "implement" and lane_status in {
            "waiting",
            "review_waiting",
        }:
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="move_board",
                stage="review",
                target_board_state=BoardState.REVIEW.value,
                reason="implementation output is ready for review",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="deliver",
            actor="implementer",
            mode="implement",
            reason="in-progress lane needs implementation",
            inputs={"mode": "implement"},
        )
    if board_state == BoardState.REVIEW.value:
        if review_has_required_changes(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="move_board",
                stage="deliver",
                target_board_state=BoardState.REWORK.value,
                reason="review signals require rework",
                inputs={"required_fixes": review_required_changes(lane)},
            )
        if reviewer_actor_running(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                stage="review",
                reason="reviewer actor is still running",
            )
        if _last_actor_mode(lane) == "review" and lane_status in {
            "waiting",
            "review_waiting",
        }:
            if lane_status == "review_waiting":
                return ActorRoute(
                    lane_id=lane_id,
                    board_state=board_state,
                    action="hold",
                    stage="review",
                    reason="waiting for human merge signal",
                )
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="wait_review",
                stage="review",
                reason="review actor result is waiting for human merge signal",
            )
        if "reviewer" not in config.actors or not review_actor_enabled(config):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold" if lane_status == "review_waiting" else "wait_review",
                stage="review",
                reason="no reviewer actor configured; waiting for human review",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="review",
            actor="reviewer",
            mode="review",
            reason="review lane needs shared AI review",
            inputs={"mode": "review"},
        )
    if board_state == BoardState.REWORK.value:
        if _last_actor_mode(lane) == "rework" and lane_status in {
            "waiting",
            "review_waiting",
        }:
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="move_board",
                stage="review",
                target_board_state=BoardState.REVIEW.value,
                reason="rework output is ready for review",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="deliver",
            actor="implementer",
            mode="rework",
            reason="rework lane needs implementer fixes",
            inputs={"mode": "rework"},
        )
    if board_state == BoardState.MERGING.value:
        if review_has_required_changes(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="move_board",
                stage="deliver",
                target_board_state=BoardState.REWORK.value,
                reason="required changes take priority over merge signal",
                inputs={"required_fixes": review_required_changes(lane)},
            )
        if reviewer_actor_running(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                stage="review",
                reason="merge signal is waiting for reviewer actor to finish",
            )
        if _last_actor_mode(lane) == "land" and lane_status in {
            "waiting",
            "review_waiting",
        }:
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                reason="land output is waiting for merge reconciliation",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="deliver",
            actor="implementer",
            mode="land",
            reason="merge authority seen; implementer should run land skill",
            inputs={"mode": "land"},
        )
    return ActorRoute(
        lane_id=lane_id,
        board_state=board_state,
        action="hold",
        reason="lane has no routable board state",
    )


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


def actor_driven_ready_lanes(
    *, config: WorkflowConfig, state: WorkflowState
) -> list[dict[str, Any]]:
    return [
        lane
        for lane in active_lanes(state)
        if lane_needs_actor_driven_route(config=config, lane=lane)
    ]


def lane_needs_actor_driven_route(
    *, config: WorkflowConfig, lane: dict[str, Any]
) -> bool:
    route = route_lane(config=config, lane=lane)
    return route.action in {"dispatch", "release", "wait_review", "move_board"}


def lane_board_state(*, config: WorkflowConfig, lane: dict[str, Any]) -> str | None:
    tracker = lane.get("tracker") if isinstance(lane.get("tracker"), dict) else {}
    board_state = str(
        tracker.get("board_state") or lane.get("board_state") or ""
    ).strip()
    if board_state:
        return board_state
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    return state_from_labels(issue.get("labels") or [], config)


def set_lane_board_state(
    *, config: WorkflowConfig, lane: dict[str, Any], target: BoardState
) -> dict[str, Any]:
    tracker_cfg = tracker_config(config)
    if not tracker_cfg:
        return {"status": "skipped", "reason": "no tracker config"}
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    issue_id = issue.get("id")
    try:
        mutation = desired_state_mutation(issue.get("labels") or [], target, config)
    except Exception as exc:
        return {"status": "failed", "error": str(exc), "target": target.value}
    if not mutation.add and not mutation.remove:
        refresh_lane_board_metadata(config=config, lane=lane, issue=issue)
        skipped = _record_board_state_side_effect_skipped(
            config=config,
            lane=lane,
            issue_id=issue_id,
            target=target,
            mutation=mutation,
            reason="state labels already match target",
        )
        return {
            "status": "ok",
            "changed": False,
            "target": target.value,
            "side_effect": skipped,
        }
    effect_key = _board_state_side_effect_key(
        config=config,
        lane=lane,
        issue_id=issue_id,
        target=target,
        mutation=mutation,
    )
    completed = completed_side_effect(config=config, lane=lane, key=effect_key)
    if completed:
        _apply_label_mutation(issue=issue, add=mutation.add, remove=mutation.remove)
        refresh_lane_board_metadata(config=config, lane=lane, issue=issue)
        return {
            "status": "ok",
            "changed": False,
            "target": target.value,
            "idempotency_key": effect_key,
            "side_effect": completed,
            "reason": "board state side effect already completed",
        }
    payload = {
        "target": target.value,
        "add": mutation.add,
        "remove": mutation.remove,
    }
    record_side_effect_started(
        config=config,
        lane=lane,
        key=effect_key,
        operation="tracker.set_issue_state_label",
        target=f"issue:{issue_id or 'missing'}:state:{target.value}",
        payload=payload,
    )
    try:
        client = build_tracker_client(
            workflow_root=config.workflow_root,
            tracker_cfg=tracker_cfg,
            repo_path=repository_path(config),
        )
        changed = client.set_issue_state_label(
            issue_id, add=mutation.add, remove=mutation.remove
        )
    except Exception as exc:
        record_side_effect_failed(
            config=config,
            lane=lane,
            key=effect_key,
            operation="tracker.set_issue_state_label",
            target=f"issue:{issue_id or 'missing'}:state:{target.value}",
            payload=payload,
            error=str(exc),
        )
        append_engine_event(
            config=config,
            lane=lane,
            event_type=f"{config.workflow_name}.lane.board_state_update_failed",
            payload={
                "target": target.value,
                "add": mutation.add,
                "remove": mutation.remove,
                "error": str(exc),
            },
            severity="warning",
        )
        return {"status": "failed", "error": str(exc), "target": target.value}
    if not changed:
        record_side_effect_failed(
            config=config,
            lane=lane,
            key=effect_key,
            operation="tracker.set_issue_state_label",
            target=f"issue:{issue_id or 'missing'}:state:{target.value}",
            payload=payload,
            error="tracker did not apply requested state label mutation",
        )
        return {
            "status": "failed",
            "error": "tracker did not apply requested state label mutation",
            "target": target.value,
            "add": mutation.add,
            "remove": mutation.remove,
        }
    _apply_label_mutation(issue=issue, add=mutation.add, remove=mutation.remove)
    refresh_lane_board_metadata(config=config, lane=lane, issue=issue)
    side_effect = record_side_effect_succeeded(
        config=config,
        lane=lane,
        key=effect_key,
        operation="tracker.set_issue_state_label",
        target=f"issue:{issue_id or 'missing'}:state:{target.value}",
        payload=payload,
        result={"changed": changed},
    )
    append_engine_event(
        config=config,
        lane=lane,
        event_type=f"{config.workflow_name}.lane.board_state_updated",
        payload={
            "target": target.value,
            "changed": changed,
            "add": mutation.add,
            "remove": mutation.remove,
        },
    )
    return {
        "status": "ok",
        "changed": changed,
        "target": target.value,
        "add": mutation.add,
        "remove": mutation.remove,
        "idempotency_key": effect_key,
        "side_effect": side_effect,
    }


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


def _due_retry_route(*, lane: dict[str, Any], board_state: str) -> ActorRoute | None:
    pending = (
        lane.get("pending_retry") if isinstance(lane.get("pending_retry"), dict) else {}
    )
    inputs = pending.get("inputs") if isinstance(pending.get("inputs"), dict) else {}
    lane_id = str(lane.get("lane_id") or "")
    board_target = str(inputs.get("board_state_target") or "").strip()
    if board_target:
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="move_board",
            stage=str(pending.get("stage") or lane.get("stage") or "") or None,
            actor=str(pending.get("target") or "") or None,
            mode=str(inputs.get("mode") or "") or None,
            target_board_state=board_target,
            reason=str(pending.get("reason") or "retry board state update"),
            inputs=dict(inputs),
        )
    stage = str(pending.get("stage") or lane.get("stage") or "").strip()
    target = str(pending.get("target") or "").strip()
    if not stage or not target:
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="operator_attention",
            reason="due retry is missing stage or target",
            inputs=dict(inputs),
        )
    return ActorRoute(
        lane_id=lane_id,
        board_state=board_state,
        action="dispatch",
        stage=stage,
        actor=target,
        mode=_retry_actor_mode(
            actor=target,
            board_state=board_state,
            lane=lane,
            inputs=inputs,
        ),
        reason=str(pending.get("reason") or "dispatch due retry"),
        inputs=dict(inputs),
    )


def _retry_actor_mode(
    *, actor: str, board_state: str, lane: dict[str, Any], inputs: dict[str, Any]
) -> str | None:
    mode = str(inputs.get("mode") or "").strip().lower()
    if mode:
        return mode
    actor_name = str(actor or "").strip().lower()
    if actor_name == "reviewer":
        return "review"
    if actor_name == "implementer":
        if board_state == BoardState.REWORK.value:
            return "rework"
        if board_state == BoardState.MERGING.value:
            return "land"
        last_mode = _last_actor_mode(lane)
        if last_mode in {"implement", "rework", "land"}:
            return last_mode
        return "implement"
    return None


def _last_actor_mode(lane: dict[str, Any]) -> str:
    dispatch = (
        lane.get("actor_dispatch")
        if isinstance(lane.get("actor_dispatch"), dict)
        else {}
    )
    runtime = (
        dispatch.get("runtime") if isinstance(dispatch.get("runtime"), dict) else {}
    )
    return str(runtime.get("actor_mode") or runtime.get("mode") or "").strip().lower()


def _done_release_verified(lane: dict[str, Any]) -> bool:
    if active_actor_dispatch(lane):
        return False
    if str(lane.get("status") or "").strip().lower() == "running":
        return False
    tracker = lane.get("tracker") if isinstance(lane.get("tracker"), dict) else {}
    state_labels = {
        str(label).strip().lower() for label in tracker.get("state_labels") or []
    }
    if len(state_labels) > 1:
        return False
    pull_request = (
        lane.get("pull_request") if isinstance(lane.get("pull_request"), dict) else {}
    )
    pr_state = str(pull_request.get("state") or "").strip().lower()
    if bool(pull_request.get("merged")) or pr_state == "merged":
        return True
    actor_outputs = (
        lane.get("actor_outputs") if isinstance(lane.get("actor_outputs"), dict) else {}
    )
    implementation = (
        actor_outputs.get("implementer")
        if isinstance(actor_outputs.get("implementer"), dict)
        else {}
    )
    output_pr = (
        implementation.get("pull_request")
        if isinstance(implementation.get("pull_request"), dict)
        else {}
    )
    output_state = str(output_pr.get("state") or "").strip().lower()
    return bool(output_pr.get("merged")) or output_state == "merged"


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


def _reconcile_blocks_routing(reconcile: dict[str, Any]) -> bool:
    for key in ("tracker", "pull_requests", "review_signals"):
        value = reconcile.get(key)
        if isinstance(value, dict) and value.get("status") == "error":
            return True
    return False


def _apply_label_mutation(
    *, issue: dict[str, Any], add: list[str], remove: list[str]
) -> None:
    current = [label for label in issue.get("labels") or [] if str(label).strip()]
    remove_lower = {label.lower() for label in remove}
    labels = [
        label
        for label in current
        if str(label.get("name") if isinstance(label, dict) else label).strip().lower()
        not in remove_lower
    ]
    existing_lower = {
        str(label.get("name") if isinstance(label, dict) else label).strip().lower()
        for label in labels
    }
    for label in add:
        if label.lower() not in existing_lower:
            labels.append(label)
    issue["labels"] = labels


def _board_state_side_effect_key(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    issue_id: Any,
    target: BoardState,
    mutation: Any,
) -> str:
    return side_effect_key(
        config=config,
        lane=lane,
        operation="tracker.set_issue_state_label",
        target=_board_state_side_effect_target(issue_id=issue_id, target=target),
        payload={
            "target": target.value,
            "add": list(mutation.add or []),
            "remove": list(mutation.remove or []),
        },
    )


def _record_board_state_side_effect_skipped(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    issue_id: Any,
    target: BoardState,
    mutation: Any,
    reason: str,
) -> dict[str, Any]:
    key = _board_state_side_effect_key(
        config=config,
        lane=lane,
        issue_id=issue_id,
        target=target,
        mutation=mutation,
    )
    return record_side_effect_skipped(
        config=config,
        lane=lane,
        key=key,
        operation="tracker.set_issue_state_label",
        target=_board_state_side_effect_target(issue_id=issue_id, target=target),
        payload={
            "target": target.value,
            "add": list(mutation.add or []),
            "remove": list(mutation.remove or []),
        },
        reason=reason,
    )


def _board_state_side_effect_target(*, issue_id: Any, target: BoardState) -> str:
    return f"issue:{issue_id or 'missing'}:state:{target.value}"


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


def _save_actor_driven_tick(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    event: str,
    extra: dict[str, Any] | None = None,
) -> None:
    save_state_event(config=config, state=state, event=event, extra=extra)
    print(json.dumps(state.to_dict(), indent=2, sort_keys=True))


def _save_failed_actor_driven_tick(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    intake: dict[str, Any],
    reconcile: dict[str, Any],
    routes: list[ActorRoute],
    results: list[dict[str, Any]],
    error: Exception,
    tick_journal: TickJournal,
) -> None:
    persist_runtime_state(config=config, state=state)
    append_audit(
        config.storage.audit_log_path,
        {
            "event": f"{config.workflow_name}.actor_driven_tick_failed",
            "state": state.to_dict(),
            "intake": intake,
            "reconcile": reconcile,
            "routes": [route.to_dict() for route in routes],
            "results": results,
            "error": str(error),
            "error_type": type(error).__name__,
            "tick_journal": tick_journal.to_dict(),
            "failed_at": now_iso(),
        },
    )
