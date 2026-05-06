"""Lane retry projection over engine retry mechanics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sprints.engine import pending_retry_projection, retry_is_due, retry_record
from sprints.core.config import WorkflowConfig
from sprints.workflows.lane_state import (
    append_engine_event,
    clear_engine_retry,
    completion_cleanup_retry_pending,
    engine_store,
    lane_list,
    lane_run_id,
    lane_transition_side,
    now_iso,
    retry_engine_entry,
    retry_policy,
    set_lane_operator_attention,
    set_lane_status,
)


@dataclass(frozen=True)
class RetryRequest:
    stage: str
    target: str | None = None
    lane_id: str | None = None
    reason: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)


def queue_lane_retry(
    *, config: WorkflowConfig, lane: dict[str, Any], request: RetryRequest
) -> dict[str, Any]:
    current_attempt = max(int(lane.get("attempt") or 1), 1)
    schedule = engine_store(config).schedule_retry(
        work_id=str(lane.get("lane_id") or ""),
        entry=retry_engine_entry(lane),
        policy=retry_policy(config),
        current_attempt=current_attempt,
        error=request.reason or "retry requested",
        delay_type="workflow-retry",
        run_id=lane_run_id(lane),
        now_iso=now_iso(),
    )
    record = retry_record(
        stage=request.stage,
        target=request.target,
        reason=request.reason,
        inputs=request.inputs,
        schedule=schedule,
        now_iso=now_iso(),
    )
    retry_history = lane_list(lane, "retry_history")
    if schedule.get("status") == "limit_exceeded":
        retry_history.append(record)
        append_engine_event(
            config=config,
            lane=lane,
            event_type=f"{config.workflow_name}.lane.retry.limit_exceeded",
            payload=_retry_event_payload(
                lane=lane,
                request=request,
                retry=record,
                status="limit_exceeded",
            ),
            severity="error",
        )
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="retry_limit_exceeded",
            message=(
                f"retry limit exceeded for stage {request.stage!r}; "
                f"attempt {current_attempt} reached max {schedule['max_attempts']}"
            ),
            artifacts={
                "retry": record,
                "last_actor_output": lane.get("last_actor_output"),
                "branch": lane.get("branch"),
                "pull_request": lane.get("pull_request"),
            },
        )
        return {
            "lane_id": lane.get("lane_id"),
            "decision": "retry",
            "status": "operator_attention",
            "reason": "retry_limit_exceeded",
        }

    pending = pending_retry_projection(
        stage=request.stage,
        target=request.target,
        reason=request.reason,
        inputs=request.inputs,
        schedule=schedule,
    )
    previous = lane_transition_side(lane)
    next_attempt = int(pending.get("attempt") or current_attempt)
    lane["attempt"] = next_attempt
    lane["stage"] = request.stage
    lane["operator_attention"] = None
    lane["pending_retry"] = pending
    retry_history.append(record)
    set_lane_status(
        config=config,
        lane=lane,
        status="retry_queued",
        reason=request.reason or "retry requested",
        actor=None,
        previous=previous,
    )
    append_engine_event(
        config=config,
        lane=lane,
        event_type=f"{config.workflow_name}.lane.retry.scheduled",
        payload=_retry_event_payload(
            lane=lane,
            request=request,
            retry=pending,
            status="queued",
        ),
        severity="warning",
    )
    return {
        "lane_id": lane.get("lane_id"),
        "decision": "retry",
        "status": "queued",
        "attempt": next_attempt,
        "due_at": pending["due_at"],
        "engine_retry": pending.get("engine_retry"),
    }


def consume_lane_retry(*, config: WorkflowConfig, lane: dict[str, Any]) -> None:
    if not isinstance(lane.get("pending_retry"), dict):
        return
    lane["pending_retry"] = None
    clear_engine_retry(config=config, lane=lane)


def lane_retry_inputs(
    *, lane: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, Any]:
    if str(lane.get("status") or "").strip() != "retry_queued":
        return inputs
    if completion_cleanup_retry_pending(lane):
        return inputs
    pending = (
        lane.get("pending_retry") if isinstance(lane.get("pending_retry"), dict) else {}
    )
    retry_inputs = (
        pending.get("inputs") if isinstance(pending.get("inputs"), dict) else {}
    )
    return {**retry_inputs, **inputs, "retry": pending}


def lane_retry_is_due(lane: dict[str, Any], *, now_epoch: float | None = None) -> bool:
    pending = (
        lane.get("pending_retry") if isinstance(lane.get("pending_retry"), dict) else {}
    )
    return retry_is_due(pending, now_epoch=now_epoch)


def _retry_event_payload(
    *,
    lane: dict[str, Any],
    request: RetryRequest,
    retry: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    return {
        "lane_id": lane.get("lane_id"),
        "status": status,
        "stage": request.stage,
        "target": request.target,
        "failure_reason": request.reason,
        "retry": {
            "status": retry.get("status") or status,
            "stage": retry.get("stage") or request.stage,
            "target": retry.get("target") or request.target,
            "reason": retry.get("reason") or request.reason,
            "attempt": retry.get("attempt") or retry.get("next_attempt"),
            "current_attempt": retry.get("current_attempt"),
            "max_attempts": retry.get("max_attempts"),
            "delay_seconds": retry.get("delay_seconds"),
            "backoff_seconds": retry.get("backoff_seconds")
            or retry.get("delay_seconds"),
            "due_at": retry.get("due_at"),
            "due_at_epoch": retry.get("due_at_epoch"),
            "queued_at": retry.get("queued_at"),
        },
    }
