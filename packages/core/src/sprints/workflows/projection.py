"""Shared engine-first lane projections for status and watch surfaces."""

from __future__ import annotations

from typing import Any

from sprints.engine.work import work_item_from_issue
from sprints.workflows.lane_state import lane_summary

TERMINAL_ENGINE_STATES = {"complete", "released", "merged", "closed", "archived"}


def project_lane_map(
    *,
    workflow_name: str,
    state_lanes: dict[str, Any],
    engine_work_items: list[dict[str, Any]],
    engine_runtime_sessions: list[dict[str, Any]] | dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    runtime_by_work_id = _runtime_by_work_id(engine_runtime_sessions)
    projected: dict[str, dict[str, Any]] = {}
    for work_item in engine_work_items:
        if not isinstance(work_item, dict):
            continue
        lane_id = str(work_item.get("work_id") or work_item.get("issue_id") or "")
        if not lane_id:
            continue
        state_lane = state_lanes.get(lane_id)
        projected[lane_id] = project_engine_lane(
            workflow_name=workflow_name,
            work_item=work_item,
            state_lane=state_lane if isinstance(state_lane, dict) else {},
            runtime_session=runtime_by_work_id.get(lane_id) or {},
        )
    for lane_id, lane in state_lanes.items():
        if lane_id in projected or not isinstance(lane, dict):
            continue
        projected[lane_id] = {
            **project_state_lane(lane, workflow_name=workflow_name),
            "lane_status_source": "workflow_state",
            "state_json_present": True,
        }
    return projected


def project_engine_lane(
    *,
    workflow_name: str,
    work_item: dict[str, Any],
    state_lane: dict[str, Any],
    runtime_session: dict[str, Any],
) -> dict[str, Any]:
    metadata = (
        work_item.get("metadata") if isinstance(work_item.get("metadata"), dict) else {}
    )
    state_entry = (
        project_state_lane(state_lane, workflow_name=workflow_name)
        if isinstance(state_lane, dict) and state_lane
        else {}
    )
    state_summary = lane_summary(state_lane) if state_lane else {}
    lane_id = str(work_item.get("work_id") or state_entry.get("lane_id") or "")
    issue = (
        state_summary.get("issue")
        if isinstance(state_summary.get("issue"), dict)
        else {}
    )
    pull_request = metadata.get("pull_request") or state_summary.get(
        "pull_request"
    ) or state_entry.get("pull_request")
    pending_retry = metadata.get("pending_retry") or state_summary.get(
        "pending_retry"
    )
    operator_attention = metadata.get("operator_attention") or state_summary.get(
        "operator_attention"
    )
    review_signals = metadata.get("review_signals") or state_summary.get(
        "review_signals"
    )
    merge_signal = metadata.get("merge_signal") or state_summary.get("merge_signal")
    tracker = metadata.get("tracker") if isinstance(metadata.get("tracker"), dict) else {}
    if not tracker and isinstance(state_summary.get("tracker"), dict):
        tracker = state_summary.get("tracker") or {}
    runtime_metadata = (
        runtime_session.get("metadata")
        if isinstance(runtime_session.get("metadata"), dict)
        else {}
    )
    actor_mode = (
        runtime_session.get("actor_mode")
        or runtime_metadata.get("actor_mode")
        or runtime_metadata.get("mode")
        or metadata.get("actor_mode")
        or state_entry.get("actor_mode")
    )
    work_item_ref = work_item_from_issue(
        {
            "id": lane_id or work_item.get("identifier") or "unknown",
            "identifier": work_item.get("identifier") or lane_id,
            "title": work_item.get("title") or "",
            "url": work_item.get("url"),
            "state": work_item.get("state"),
        },
        source=workflow_name,
    ).to_dict()
    return {
        **state_entry,
        **state_summary,
        "lane_id": lane_id,
        "state": metadata.get("stage")
        or state_entry.get("state")
        or work_item.get("state"),
        "workflow_state": metadata.get("stage")
        or state_entry.get("workflow_state")
        or work_item.get("state"),
        "status": work_item.get("state") or state_summary.get("status"),
        "lane_status": work_item.get("state") or state_entry.get("lane_status"),
        "stage": metadata.get("stage") or state_summary.get("stage"),
        "actor": metadata.get("actor") or state_summary.get("actor"),
        "actor_mode": actor_mode,
        "attempt": metadata.get("attempt") or state_summary.get("attempt"),
        "issue": {
            "identifier": work_item.get("identifier")
            or issue.get("identifier")
            or lane_id,
            "title": work_item.get("title") or issue.get("title"),
            "url": work_item.get("url") or issue.get("url"),
        },
        "issue_identifier": work_item.get("identifier")
        or state_entry.get("issue_identifier")
        or lane_id,
        "issue_title": work_item.get("title") or state_entry.get("issue_title"),
        "board_state": tracker.get("board_state") or state_entry.get("board_state"),
        "tracker": tracker or state_entry.get("tracker"),
        "branch": metadata.get("branch") or state_summary.get("branch"),
        "pull_request": pull_request,
        "pull_request_number": (pull_request or {}).get("number")
        if isinstance(pull_request, dict)
        else state_entry.get("pull_request_number"),
        "pull_request_url": (pull_request or {}).get("url")
        if isinstance(pull_request, dict)
        else state_entry.get("pull_request_url"),
        "review_signals": review_signals,
        "merge_signal": merge_signal,
        "review_required_change_count": _required_change_count(review_signals),
        "reviewer_actor_running": _reviewer_actor_running(review_signals),
        "merge_signal_seen": _merge_signal_seen(
            review_signals=review_signals, merge_signal=merge_signal
        ),
        "operator_attention": operator_attention,
        "operator_attention_reason": (operator_attention or {}).get("reason")
        if isinstance(operator_attention, dict)
        else state_entry.get("operator_attention_reason"),
        "operator_attention_message": (operator_attention or {}).get("message")
        if isinstance(operator_attention, dict)
        else state_entry.get("operator_attention_message"),
        "pending_retry": pending_retry,
        "retry_at": (pending_retry or {}).get("due_at")
        if isinstance(pending_retry, dict)
        else state_entry.get("retry_at"),
        "retry_target": (pending_retry or {}).get("target")
        if isinstance(pending_retry, dict)
        else state_entry.get("retry_target"),
        "retry_attempt": (pending_retry or {}).get("attempt")
        if isinstance(pending_retry, dict)
        else state_entry.get("retry_attempt"),
        "last_transition": metadata.get("last_transition")
        or state_summary.get("last_transition"),
        "transition_history_count": metadata.get("transition_history_count")
        or state_summary.get("transition_history_count"),
        "thread_id": runtime_session.get("thread_id")
        or metadata.get("thread_id")
        or runtime_metadata.get("thread_id")
        or state_summary.get("thread_id"),
        "turn_id": runtime_session.get("turn_id")
        or metadata.get("turn_id")
        or runtime_metadata.get("turn_id")
        or state_summary.get("turn_id"),
        "runtime_status": runtime_session.get("status")
        or state_entry.get("runtime_status"),
        "runtime_session": runtime_session or None,
        "last_progress_at": runtime_session.get("updated_at")
        or work_item.get("updated_at")
        or state_summary.get("last_progress_at"),
        "engine_updated_at": work_item.get("updated_at"),
        "engine_work_item": work_item,
        "lane_status_source": "engine_work_items",
        "state_json_present": bool(state_lane),
        "kind": work_item.get("state") or state_entry.get("kind"),
        "work_item": work_item_ref,
    }


def project_state_lane(
    lane: dict[str, Any], *, workflow_name: str
) -> dict[str, Any]:
    summary = lane_summary(lane)
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    lane_id = str(lane.get("lane_id") or issue.get("id") or "").strip()
    identifier = str(
        issue.get("identifier") or issue.get("number") or lane_id or "unknown"
    )
    status = str(lane.get("status") or "active").strip() or "active"
    stage = str(lane.get("stage") or status).strip() or status
    pull_request = (
        lane.get("pull_request") if isinstance(lane.get("pull_request"), dict) else {}
    )
    pending_retry = (
        lane.get("pending_retry") if isinstance(lane.get("pending_retry"), dict) else {}
    )
    retry_history = [
        record for record in lane.get("retry_history") or [] if isinstance(record, dict)
    ]
    retry_latest = retry_history[-1] if retry_history else {}
    attention = (
        lane.get("operator_attention")
        if isinstance(lane.get("operator_attention"), dict)
        else {}
    )
    runtime_session = (
        lane.get("runtime_session")
        if isinstance(lane.get("runtime_session"), dict)
        else {}
    )
    actor_dispatch = (
        lane.get("actor_dispatch")
        if isinstance(lane.get("actor_dispatch"), dict)
        else {}
    )
    dispatch_runtime = (
        actor_dispatch.get("runtime")
        if isinstance(actor_dispatch.get("runtime"), dict)
        else {}
    )
    tracker = lane.get("tracker") if isinstance(lane.get("tracker"), dict) else {}
    review_signals = (
        lane.get("review_signals")
        if isinstance(lane.get("review_signals"), dict)
        else {}
    )
    merge_signal = (
        lane.get("merge_signal") if isinstance(lane.get("merge_signal"), dict) else {}
    )
    work_item = work_item_from_issue(
        {
            "id": issue.get("id") or lane_id or identifier,
            "identifier": identifier,
            "title": issue.get("title") or "",
            "url": issue.get("url"),
            "state": status,
        },
        source=workflow_name,
    ).to_dict()
    return {
        **summary,
        "lane_id": lane_id or identifier,
        "state": stage,
        "workflow_state": stage,
        "issue_number": issue.get("number"),
        "issue_identifier": identifier,
        "issue_title": issue.get("title"),
        "lane_status": status,
        "status": status,
        "stage": stage,
        "actor": lane.get("actor"),
        "actor_mode": runtime_session.get("actor_mode")
        or dispatch_runtime.get("actor_mode")
        or dispatch_runtime.get("mode"),
        "attempt": lane.get("attempt"),
        "board_state": tracker.get("board_state") or lane.get("board_state"),
        "tracker": tracker or None,
        "branch": lane.get("branch"),
        "pull_request": pull_request or None,
        "pull_request_number": pull_request.get("number"),
        "pull_request_url": pull_request.get("url"),
        "review_signals": review_signals or None,
        "merge_signal": merge_signal or None,
        "review_required_change_count": _required_change_count(review_signals),
        "reviewer_actor_running": _reviewer_actor_running(review_signals),
        "merge_signal_seen": _merge_signal_seen(
            review_signals=review_signals, merge_signal=merge_signal
        ),
        "retry_at": pending_retry.get("due_at"),
        "retry_target": pending_retry.get("target"),
        "retry_attempt": pending_retry.get("attempt"),
        "retry_current_attempt": pending_retry.get("current_attempt")
        or retry_latest.get("current_attempt"),
        "retry_max_attempts": pending_retry.get("max_attempts")
        or retry_latest.get("max_attempts"),
        "retry_delay_seconds": pending_retry.get("delay_seconds")
        or retry_latest.get("delay_seconds"),
        "retry_backoff_seconds": pending_retry.get("delay_seconds")
        or retry_latest.get("delay_seconds"),
        "retry_reason": pending_retry.get("reason") or retry_latest.get("reason"),
        "retry_history_count": len(retry_history),
        "operator_attention_reason": attention.get("reason"),
        "operator_attention_message": attention.get("message"),
        "last_progress_at": lane.get("last_progress_at"),
        "runtime_status": runtime_session.get("status"),
        "dispatch_id": actor_dispatch.get("dispatch_id"),
        "dispatch_status": actor_dispatch.get("status"),
        "dispatch_actor": actor_dispatch.get("actor"),
        "dispatch_stage": actor_dispatch.get("stage"),
        "dispatch_mode": dispatch_runtime.get("dispatch_mode"),
        "dispatch_updated_at": actor_dispatch.get("updated_at"),
        "dispatch_journal_count": len(lane.get("dispatch_journal") or []),
        "side_effect_count": len(lane.get("side_effects") or []),
        "thread_id": lane.get("thread_id") or runtime_session.get("thread_id"),
        "turn_id": lane.get("turn_id") or runtime_session.get("turn_id"),
        "kind": status,
        "work_item": work_item,
    }


def projected_lane_is_terminal(lane: dict[str, Any]) -> bool:
    return str(lane.get("status") or "").strip().lower() in TERMINAL_ENGINE_STATES


def _runtime_by_work_id(
    sessions: list[dict[str, Any]] | dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if isinstance(sessions, dict):
        return sessions
    return {
        str(session.get("work_id") or session.get("issue_id") or ""): session
        for session in sessions
        if isinstance(session, dict)
    }


def _required_change_count(review_signals: Any) -> int:
    if not isinstance(review_signals, dict):
        return 0
    return len(review_signals.get("required_changes") or [])


def _reviewer_actor_running(review_signals: Any) -> Any:
    if not isinstance(review_signals, dict):
        return None
    return review_signals.get("reviewer_actor_running")


def _merge_signal_seen(*, review_signals: Any, merge_signal: Any) -> Any:
    if isinstance(merge_signal, dict) and merge_signal.get("seen"):
        return merge_signal.get("seen")
    if isinstance(review_signals, dict):
        return review_signals.get("merge_signal_seen")
    return None
