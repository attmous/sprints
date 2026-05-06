"""Deterministic tick routing for actor-driven workflows."""

from __future__ import annotations

import json
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.core.contracts import WorkflowPolicy
from sprints.core.loader import load_workflow_policy
from sprints.workflows.lane_intake import claim_new_lanes
from sprints.workflows.lane_state import (
    active_lanes,
    now_iso,
)
from sprints.workflows.lane_reconcile import reconcile_lanes
from sprints.workflows.route_effects import apply_actor_route
from sprints.workflows.route_rules import (
    ActorRoute,
    route_lane,
)
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
from sprints.workflows.lane_transitions import actor_concurrency_usage


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


def _reconcile_blocks_routing(reconcile: dict[str, Any]) -> bool:
    for key in ("tracker", "pull_requests", "review_signals"):
        value = reconcile.get(key)
        if isinstance(value, dict) and value.get("status") == "error":
            return True
    return False


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
