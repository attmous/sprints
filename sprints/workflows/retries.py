"""Lane retry projection over engine retry mechanics."""

from __future__ import annotations

import time
from typing import Any

from workflows.config import WorkflowConfig
from workflows.lane_state import (
    _clear_engine_retry,
    _completion_cleanup_retry_pending,
    _engine_store,
    _epoch_to_iso,
    _iso_to_epoch,
    _lane_run_id,
    _now_iso,
    _retry_engine_entry,
    _retry_policy,
    lane_list,
    set_lane_operator_attention,
    set_lane_status,
)
from workflows.orchestrator import OrchestratorDecision


def queue_lane_retry(
    *, config: WorkflowConfig, lane: dict[str, Any], decision: OrchestratorDecision
) -> dict[str, Any]:
    current_attempt = max(int(lane.get("attempt") or 1), 1)
    schedule = _engine_store(config).schedule_retry(
        work_id=str(lane.get("lane_id") or ""),
        entry=_retry_engine_entry(lane),
        policy=_retry_policy(config),
        current_attempt=current_attempt,
        error=decision.reason or "retry requested",
        delay_type="workflow-retry",
        run_id=_lane_run_id(lane),
        now_iso=_now_iso(),
    )
    record = _retry_record(
        decision=decision,
        schedule=schedule,
    )
    retry_history = lane_list(lane, "retry_history")
    if schedule.get("status") == "limit_exceeded":
        retry_history.append(record)
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="retry_limit_exceeded",
            message=(
                f"retry limit exceeded for stage {decision.stage!r}; "
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

    pending = _pending_retry_projection(decision=decision, schedule=schedule)
    next_attempt = int(pending.get("attempt") or current_attempt)
    lane["attempt"] = next_attempt
    lane["stage"] = decision.stage
    lane["operator_attention"] = None
    lane["pending_retry"] = pending
    retry_history.append(record)
    set_lane_status(
        config=config,
        lane=lane,
        status="retry_queued",
        reason=decision.reason or "retry requested",
        actor=None,
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
    _clear_engine_retry(config=config, lane=lane)


def lane_retry_inputs(
    *, lane: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, Any]:
    if str(lane.get("status") or "").strip() != "retry_queued":
        return inputs
    if _completion_cleanup_retry_pending(lane):
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
    due_at_epoch = _retry_due_at_epoch(pending)
    return (time.time() if now_epoch is None else now_epoch) >= due_at_epoch


def _retry_record(
    *,
    decision: OrchestratorDecision,
    schedule: dict[str, Any],
) -> dict[str, Any]:
    due_at_epoch = _schedule_due_at_epoch(schedule)
    return {
        "status": schedule.get("status"),
        "queued_at": _engine_retry_updated_at(schedule) or _now_iso(),
        "stage": decision.stage,
        "target": decision.target,
        "reason": decision.reason,
        "inputs": decision.inputs,
        "current_attempt": int(schedule.get("current_attempt") or 0),
        "next_attempt": int(schedule.get("next_attempt") or 0),
        "max_attempts": int(schedule.get("max_attempts") or 0),
        "delay_seconds": schedule.get("delay_seconds"),
        "due_at": _epoch_to_iso(due_at_epoch) if due_at_epoch is not None else None,
        "due_at_epoch": due_at_epoch,
        "engine_retry": schedule.get("engine_retry") or None,
    }


def _pending_retry_projection(
    *, decision: OrchestratorDecision, schedule: dict[str, Any]
) -> dict[str, Any]:
    due_at_epoch = _schedule_due_at_epoch(schedule)
    return {
        "source": "engine_retry_queue",
        "stage": decision.stage,
        "target": decision.target,
        "reason": decision.reason,
        "inputs": decision.inputs,
        "attempt": int(schedule.get("next_attempt") or 0),
        "current_attempt": int(schedule.get("current_attempt") or 0),
        "queued_at": _engine_retry_updated_at(schedule) or _now_iso(),
        "delay_seconds": int(schedule.get("delay_seconds") or 0),
        "due_at": _epoch_to_iso(due_at_epoch or time.time()),
        "due_at_epoch": due_at_epoch if due_at_epoch is not None else time.time(),
        "max_attempts": int(schedule.get("max_attempts") or 0),
        "engine_retry": schedule.get("engine_retry") or None,
    }


def _engine_retry_updated_at(schedule: dict[str, Any]) -> str:
    engine_retry = (
        schedule.get("engine_retry")
        if isinstance(schedule.get("engine_retry"), dict)
        else {}
    )
    return str(engine_retry.get("updated_at") or "").strip()


def _schedule_due_at_epoch(schedule: dict[str, Any]) -> float | None:
    value = schedule.get("due_at_epoch")
    if value in (None, ""):
        engine_retry = (
            schedule.get("engine_retry")
            if isinstance(schedule.get("engine_retry"), dict)
            else {}
        )
        value = engine_retry.get("due_at_epoch")
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _retry_due_at_epoch(pending_retry: dict[str, Any]) -> float:
    value = pending_retry.get("due_at_epoch")
    if value not in (None, ""):
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    return _iso_to_epoch(str(pending_retry.get("due_at") or ""), default=time.time())
