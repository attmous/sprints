"""Lane reconciliation against runtime sessions, trackers, and pull requests."""

from __future__ import annotations

import time
from typing import Any

from trackers import build_code_host_client, build_tracker_client
from workflows import sessions
from workflows import teardown as teardown_flow
from workflows.config import WorkflowConfig
from workflows.lane_state import (
    _append_engine_event,
    _code_host_config,
    _completion_cleanup_retry_pending,
    _issue_is_still_active,
    _iso_to_epoch,
    _normalize_pull_request,
    _now_iso,
    _recovery_config,
    _release_lane_lease,
    _repository_path,
    _tracker_config,
    active_lanes,
    lane_is_terminal,
    lane_mapping,
    set_lane_operator_attention,
    set_lane_status,
)
from workflows.orchestrator import OrchestratorDecision
from workflows.retries import queue_lane_retry
from workflows.sessions import record_actor_runtime_interrupted
from workflows.transitions import _teardown_ops


def reconcile_lanes(*, config: WorkflowConfig, state: Any) -> dict[str, Any]:
    active = active_lanes(state)
    if not active:
        return {"status": "skipped", "reason": "no active lanes"}
    runtime_result = reconcile_runtime_lanes(config=config, lanes=active)
    cleanup_result = _reconcile_completion_cleanup(config=config, lanes=active)
    tracker_result = _reconcile_tracker_lanes(config=config, lanes=active)
    pr_result = _reconcile_pull_requests(config=config, lanes=active)
    return {
        "status": "ok",
        "runtime": runtime_result,
        "completion_cleanup": cleanup_result,
        "tracker": tracker_result,
        "pull_requests": pr_result,
    }


def reconcile_runtime_lanes(
    *, config: WorkflowConfig, lanes: list[dict[str, Any]]
) -> dict[str, Any]:
    cfg = _recovery_config(config)
    stale_seconds = cfg["running_stale_seconds"]
    if stale_seconds <= 0:
        return {"status": "skipped", "reason": "running stale detection disabled"}
    now = time.time()
    interrupted: list[str] = []
    recovery_queued: list[str] = []
    operator_attention: list[str] = []
    for lane in lanes:
        if str(lane.get("status") or "") != "running":
            continue
        session = lane_mapping(lane, "runtime_session")
        heartbeat = sessions.runtime_heartbeat(lane)
        timestamp = sessions.runtime_updated_at(lane) or str(
            lane.get("last_progress_at") or ""
        )
        age = now - _iso_to_epoch(timestamp, default=now)
        process_missing = sessions.runtime_process_is_missing(session)
        if age < stale_seconds and not process_missing:
            continue
        message = (
            "actor process is no longer running"
            if process_missing
            else (
                "actor was still marked running from an earlier tick; "
                f"last update was {int(age)}s ago"
            )
        )
        record_actor_runtime_interrupted(
            config=config,
            lane=lane,
            reason="actor_interrupted",
            message=message,
            age_seconds=int(age),
        )
        recovery = _runtime_recovery_record(
            lane=lane,
            session=session,
            age_seconds=int(age),
            message=message,
            heartbeat=heartbeat,
        )
        lane["runtime_recovery"] = recovery
        queued = _queue_interrupted_actor_recovery(
            config=config,
            lane=lane,
            recovery=recovery,
            enabled=cfg["auto_retry_interrupted"],
        )
        if queued.get("status") == "queued":
            recovery_queued.append(str(lane.get("lane_id") or ""))
        else:
            operator_attention.append(str(lane.get("lane_id") or ""))
        interrupted.append(str(lane.get("lane_id") or ""))
    if interrupted:
        return {
            "status": "interrupted",
            "lanes": interrupted,
            "recovery_queued": recovery_queued,
            "operator_attention": operator_attention,
        }
    return {"status": "ok", "interrupted": []}


def _reconcile_tracker_lanes(
    *, config: WorkflowConfig, lanes: list[dict[str, Any]]
) -> dict[str, Any]:
    tracker_cfg = _tracker_config(config)
    if not tracker_cfg:
        return {"status": "skipped", "reason": "no tracker config"}
    issue_ids = [
        str((lane.get("issue") or {}).get("id") or "").strip()
        for lane in lanes
        if isinstance(lane.get("issue"), dict)
    ]
    issue_ids = [issue_id for issue_id in issue_ids if issue_id]
    if not issue_ids:
        return {"status": "skipped", "reason": "no lane issue ids"}
    try:
        client = build_tracker_client(
            workflow_root=config.workflow_root,
            tracker_cfg=tracker_cfg,
            repo_path=_repository_path(config),
        )
        refreshed = client.refresh(issue_ids)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    updated: list[str] = []
    released: list[str] = []
    for lane in lanes:
        if lane_is_terminal(lane):
            continue
        if _completion_cleanup_retry_pending(lane):
            continue
        issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
        issue_id = str(issue.get("id") or "").strip()
        fresh = refreshed.get(issue_id)
        if not fresh:
            continue
        lane["issue"] = fresh
        updated.append(str(lane.get("lane_id") or ""))
        if not _issue_is_still_active(tracker_cfg=tracker_cfg, issue=fresh):
            set_lane_status(
                config=config,
                lane=lane,
                status="released",
                reason="tracker issue is no longer eligible",
            )
            _release_lane_lease(
                config=config, lane=lane, reason="tracker issue is no longer eligible"
            )
            released.append(str(lane.get("lane_id") or ""))
    return {"status": "ok", "updated": updated, "released": released}


def _reconcile_completion_cleanup(
    *, config: WorkflowConfig, lanes: list[dict[str, Any]]
) -> dict[str, Any]:
    return teardown_flow.reconcile_completion_cleanup(
        config=config,
        lanes=lanes,
        ops=_teardown_ops(),
    )


def _reconcile_pull_requests(
    *, config: WorkflowConfig, lanes: list[dict[str, Any]]
) -> dict[str, Any]:
    code_host_cfg = _code_host_config(config)
    if not code_host_cfg:
        return {"status": "skipped", "reason": "no code-host config"}
    lanes_by_branch = {
        str(lane.get("branch") or "").strip(): lane
        for lane in lanes
        if str(lane.get("branch") or "").strip()
    }
    if not lanes_by_branch:
        return {"status": "skipped", "reason": "no lane branches"}
    try:
        client = build_code_host_client(
            workflow_root=config.workflow_root,
            code_host_cfg=code_host_cfg,
            repo_path=_repository_path(config),
        )
        prs = client.list_open_pull_requests()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    updated: list[str] = []
    for pr in prs:
        branch = str(pr.get("headRefName") or "").strip()
        lane = lanes_by_branch.get(branch)
        if not lane:
            continue
        lane["pull_request"] = _normalize_pull_request(pr)
        lane["last_progress_at"] = _now_iso()
        updated.append(str(lane.get("lane_id") or ""))
    return {"status": "ok", "updated": updated}


def _runtime_recovery_record(
    *,
    lane: dict[str, Any],
    session: dict[str, Any],
    age_seconds: int,
    message: str,
    heartbeat: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actor_name = str(session.get("actor") or lane.get("actor") or "").strip()
    stage_name = str(session.get("stage") or lane.get("stage") or "").strip()
    resume_session_id = str(
        session.get("thread_id") or session.get("session_id") or ""
    ).strip()
    return {
        "status": "pending",
        "reason": "actor_interrupted",
        "message": message,
        "lane_id": lane.get("lane_id"),
        "stage": stage_name,
        "actor": actor_name,
        "resume_session_id": resume_session_id or None,
        "runtime_session": dict(session),
        "heartbeat": heartbeat or None,
        "process_id": session.get("process_id"),
        "age_seconds": age_seconds,
        "branch": lane.get("branch"),
        "pull_request": lane.get("pull_request"),
        "created_at": _now_iso(),
    }


def _queue_interrupted_actor_recovery(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    recovery: dict[str, Any],
    enabled: bool,
) -> dict[str, Any]:
    actor_name = str(recovery.get("actor") or "").strip()
    stage_name = str(recovery.get("stage") or "").strip()
    message = str(recovery.get("message") or "actor was interrupted")
    if not enabled:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_interrupted",
            message=message,
            artifacts={"recovery": recovery},
        )
        return {"status": "operator_attention", "reason": "auto recovery disabled"}
    if not actor_name or not stage_name:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_interrupted",
            message="cannot recover interrupted actor without actor and stage",
            artifacts={"recovery": recovery},
        )
        return {"status": "operator_attention", "reason": "missing actor or stage"}
    decision = OrchestratorDecision(
        decision="retry",
        stage=stage_name,
        lane_id=str(lane.get("lane_id") or ""),
        target=actor_name,
        reason="resume interrupted actor session",
        inputs={
            "feedback": message,
            "recovery": recovery,
            "resume_session_id": recovery.get("resume_session_id"),
        },
    )
    queued = queue_lane_retry(config=config, lane=lane, decision=decision)
    if queued.get("status") == "queued":
        recovery["status"] = "queued"
        recovery["retry"] = queued
        _append_engine_event(
            config=config,
            lane=lane,
            event_type=f"{config.workflow_name}.lane.runtime_recovery_queued",
            payload={"recovery": recovery},
            severity="warning",
        )
    return queued
