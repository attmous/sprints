"""Teardown merge, tracker cleanup, and cleanup retry mechanics."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sprints.engine import (
    pending_retry_projection,
    retry_record,
)
from sprints.trackers import build_code_host_client, build_tracker_client
from sprints.core.config import WorkflowConfig
from sprints.workflows.state_effects import (
    completed_side_effect,
    record_side_effect_failed,
    record_side_effect_skipped,
    record_side_effect_started,
    record_side_effect_succeeded,
    side_effect_key,
)
from sprints.workflows.lane_completion import done_release_verified
from sprints.workflows.route_orchestrator import OrchestratorDecision
from sprints.workflows.lane_state import (
    code_host_config as _code_host_config,
    configured_texts as _configured_texts,
    engine_store as _engine_store,
    issue_labels as _issue_labels,
    lane_is_terminal as _lane_is_terminal,
    lane_list as _lane_list,
    lane_mapping as _lane_mapping,
    lane_run_id as _lane_run_id,
    lane_stage as _lane_stage,
    lane_transition_side as _lane_transition_side,
    now_iso as _now_iso,
    repository_path as _repository_path,
    retry_engine_entry as _retry_engine_entry,
    retry_policy as _retry_policy,
    tracker_config as _tracker_config,
)
from sprints.workflows.state_retries import lane_retry_is_due as _lane_retry_is_due

@dataclass(frozen=True)
class TeardownOps:
    set_lane_status: Callable[..., None]
    set_lane_operator_attention: Callable[..., None]
    clear_engine_retry: Callable[..., None]
    release_lane_lease: Callable[..., dict[str, Any]]
    append_engine_event: Callable[..., None]


def complete_lane(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    reason: str,
    ops: TeardownOps,
) -> None:
    if config.is_actor_driven():
        _complete_actor_driven_lane(config=config, lane=lane, reason=reason, ops=ops)
        return
    failure = _completion_contract_failure(lane)
    if failure:
        ops.set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="completion_contract_failed",
            message=failure,
            artifacts=_contract_artifacts(lane),
        )
        return
    auto_merge = _auto_merge_completed_pull_request(config=config, lane=lane, ops=ops)
    if auto_merge.get("status") == "waiting":
        lane["completion_auto_merge"] = auto_merge
        ops.set_lane_status(
            config=config,
            lane=lane,
            status="waiting",
            actor=None,
            reason=str(auto_merge.get("reason") or "auto-merge is waiting"),
        )
        return
    if auto_merge.get("status") == "error":
        ops.set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="auto_merge_failed",
            message=str(auto_merge.get("error") or "auto-merge failed"),
            artifacts={
                "auto_merge": auto_merge,
                "pull_request": lane.get("pull_request"),
            },
        )
        return
    lane["completion_auto_merge"] = auto_merge
    cleanup = _cleanup_completed_lane(config=config, lane=lane)
    if cleanup_failed(cleanup):
        lane["completion_cleanup"] = cleanup
        _queue_completion_cleanup_retry(
            config=config, lane=lane, cleanup=cleanup, ops=ops
        )
        return
    lane["completion_cleanup"] = cleanup
    lane["pending_retry"] = None
    ops.clear_engine_retry(config=config, lane=lane)
    ops.set_lane_status(config=config, lane=lane, status="complete", reason=reason)
    ops.release_lane_lease(config=config, lane=lane, reason=reason)


def _complete_actor_driven_lane(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    reason: str,
    ops: TeardownOps,
) -> None:
    if not done_release_verified(lane):
        ops.set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_driven_completion_not_verified",
            message=(
                "actor-driven completion requires merged pull request evidence, "
                "done state, and no active actor run"
            ),
            artifacts=_contract_artifacts(lane),
        )
        return
    lane["pending_retry"] = None
    ops.clear_engine_retry(config=config, lane=lane)
    ops.set_lane_status(config=config, lane=lane, status="complete", reason=reason)
    ops.release_lane_lease(config=config, lane=lane, reason=reason)


def reconcile_completion_cleanup(
    *,
    config: WorkflowConfig,
    lanes: list[dict[str, Any]],
    ops: TeardownOps,
) -> dict[str, Any]:
    retried: list[str] = []
    completed: list[str] = []
    waiting: list[str] = []
    operator_attention: list[str] = []
    for lane in lanes:
        if _lane_is_terminal(lane):
            continue
        if not cleanup_retry_pending(lane):
            continue
        if str(lane.get("status") or "").strip() != "retry_queued":
            continue
        lane_id = str(lane.get("lane_id") or "")
        if not _lane_retry_is_due(lane):
            waiting.append(lane_id)
            continue
        result = _retry_completion_cleanup(config=config, lane=lane, ops=ops)
        status = str(result.get("status") or "")
        if status == "completed":
            completed.append(lane_id)
        elif status == "operator_attention":
            operator_attention.append(lane_id)
        else:
            retried.append(lane_id)
    if not (retried or completed or waiting or operator_attention):
        return {"status": "skipped", "reason": "no completion cleanup retries"}
    return {
        "status": "ok",
        "retried": retried,
        "completed": completed,
        "waiting": waiting,
        "operator_attention": operator_attention,
    }


def cleanup_failed(cleanup: dict[str, Any]) -> bool:
    return str(cleanup.get("status") or "").strip().lower() in {"error", "partial"}


def cleanup_retry_pending(lane: dict[str, Any]) -> bool:
    pending = (
        lane.get("pending_retry") if isinstance(lane.get("pending_retry"), dict) else {}
    )
    if str(pending.get("source") or "").strip() == "completion_cleanup":
        return True
    if str(pending.get("target") or "").strip() == "completion_cleanup":
        return True
    cleanup = (
        lane.get("completion_cleanup")
        if isinstance(lane.get("completion_cleanup"), dict)
        else {}
    )
    return str(lane.get("status") or "").strip() == "retry_queued" and cleanup_failed(
        cleanup
    )


def _retry_completion_cleanup(
    *, config: WorkflowConfig, lane: dict[str, Any], ops: TeardownOps
) -> dict[str, Any]:
    cleanup = _cleanup_completed_lane(config=config, lane=lane)
    lane["completion_cleanup"] = cleanup
    if cleanup_failed(cleanup):
        return _queue_completion_cleanup_retry(
            config=config, lane=lane, cleanup=cleanup, ops=ops
        )
    lane["completion_cleanup_attempt"] = None
    lane["pending_retry"] = None
    ops.clear_engine_retry(config=config, lane=lane)
    ops.set_lane_status(
        config=config,
        lane=lane,
        status="complete",
        reason="completion cleanup completed",
    )
    ops.release_lane_lease(
        config=config,
        lane=lane,
        reason="completion cleanup completed",
    )
    return {"status": "completed", "cleanup": cleanup}


def _queue_completion_cleanup_retry(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    cleanup: dict[str, Any],
    ops: TeardownOps,
) -> dict[str, Any]:
    current_attempt = max(int(lane.get("completion_cleanup_attempt") or 1), 1)
    reason = str(cleanup.get("error") or "completion cleanup failed")
    decision = OrchestratorDecision(
        decision="retry",
        stage=_lane_stage(lane),
        lane_id=str(lane.get("lane_id") or ""),
        target="completion_cleanup",
        reason=reason,
        inputs={"cleanup": cleanup},
    )
    schedule = _engine_store(config).schedule_retry(
        work_id=str(lane.get("lane_id") or ""),
        entry={
            **_retry_engine_entry(lane),
            "current_attempt": current_attempt,
            "delay_type": "completion-cleanup",
            "error": reason,
            "target": "completion_cleanup",
        },
        policy=_retry_policy(config),
        current_attempt=current_attempt,
        error=reason,
        delay_type="completion-cleanup",
        run_id=_lane_run_id(lane),
        now_iso=_now_iso(),
    )
    record = retry_record(
        stage=decision.stage,
        target=decision.target,
        reason=decision.reason,
        inputs=decision.inputs,
        schedule=schedule,
        now_iso=_now_iso(),
    )
    record["source"] = "completion_cleanup"
    record["cleanup"] = cleanup
    _lane_list(lane, "retry_history").append(record)
    if schedule.get("status") == "limit_exceeded":
        ops.append_engine_event(
            config=config,
            lane=lane,
            event_type=f"{config.workflow_name}.lane.retry.limit_exceeded",
            payload={
                "lane_id": lane.get("lane_id"),
                "status": "limit_exceeded",
                "stage": decision.stage,
                "target": "completion_cleanup",
                "failure_reason": reason,
                "retry": _retry_event_retry(record),
                "cleanup": cleanup,
            },
            severity="error",
        )
        ops.set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="completion_cleanup_failed",
            message=(
                "completion cleanup failed after retry limit; the pull request may "
                "already be merged and tracker labels may be partially applied"
            ),
            artifacts={
                "cleanup": cleanup,
                "retry": record,
                "completion_auto_merge": lane.get("completion_auto_merge"),
                "pull_request": lane.get("pull_request"),
            },
        )
        return {
            "lane_id": lane.get("lane_id"),
            "status": "operator_attention",
            "reason": "completion_cleanup_failed",
        }

    previous = _lane_transition_side(lane)
    pending = pending_retry_projection(
        stage=decision.stage,
        target=decision.target,
        reason=decision.reason,
        inputs=decision.inputs,
        schedule=schedule,
    )
    pending["source"] = "completion_cleanup"
    pending["target"] = "completion_cleanup"
    lane["completion_cleanup_attempt"] = int(
        pending.get("attempt") or schedule.get("next_attempt") or current_attempt
    )
    lane["operator_attention"] = None
    lane["pending_retry"] = pending
    ops.set_lane_status(
        config=config,
        lane=lane,
        status="retry_queued",
        reason="completion cleanup retry queued",
        actor=None,
        previous=previous,
    )
    ops.append_engine_event(
        config=config,
        lane=lane,
        event_type=f"{config.workflow_name}.lane.completion_cleanup_retry_queued",
        payload={
            "cleanup": cleanup,
            "failure_reason": reason,
            "retry": _retry_event_retry(pending),
        },
        severity="warning",
    )
    return {
        "lane_id": lane.get("lane_id"),
        "status": "queued",
        "attempt": lane["completion_cleanup_attempt"],
        "due_at": pending.get("due_at"),
        "engine_retry": pending.get("engine_retry"),
    }


def _auto_merge_completed_pull_request(
    *, config: WorkflowConfig, lane: dict[str, Any], ops: TeardownOps
) -> dict[str, Any]:
    cfg = _completion_auto_merge_config(config)
    if not cfg["enabled"]:
        return {"status": "skipped", "reason": "auto-merge disabled"}
    existing = lane.get("completion_auto_merge")
    if isinstance(existing, dict) and existing.get("status") == "ok":
        return existing
    method = str(cfg["method"] or "").strip().lower()
    if method not in {"squash", "merge", "rebase"}:
        return {
            "status": "error",
            "error": f"unsupported auto-merge method {method!r}",
        }
    pr_number = _pull_request_number(lane)
    if not pr_number:
        return {"status": "error", "error": "pull request number missing"}
    effect_payload = {"method": method, "delete_branch": cfg["delete_branch"]}
    effect_key = side_effect_key(
        config=config,
        lane=lane,
        operation="code_host.merge_pull_request",
        target=f"pull_request:{pr_number}",
        payload=effect_payload,
    )
    completed = completed_side_effect(config=config, lane=lane, key=effect_key)
    if completed:
        _mark_pull_request_merged(lane)
        return {
            "status": "ok",
            "method": method,
            "delete_branch": cfg["delete_branch"],
            "idempotency_key": effect_key,
            "side_effect": completed,
            "pull_request": {"number": pr_number, "already_merged": True},
        }
    if _pull_request_is_merged(lane):
        skipped = record_side_effect_skipped(
            config=config,
            lane=lane,
            key=effect_key,
            operation="code_host.merge_pull_request",
            target=f"pull_request:{pr_number}",
            payload=effect_payload,
            reason="pull request already marked merged",
            result={"pull_request": {"number": pr_number, "already_merged": True}},
        )
        return {
            "status": "ok",
            "method": method,
            "delete_branch": cfg["delete_branch"],
            "idempotency_key": effect_key,
            "side_effect": skipped,
            "pull_request": {"number": pr_number, "already_merged": True},
        }
    code_host_cfg = _code_host_config(config)
    if not code_host_cfg:
        return {
            "status": "error",
            "error": "auto-merge requires code-host config",
        }
    try:
        client = build_code_host_client(
            workflow_root=config.workflow_root,
            code_host_cfg=code_host_cfg,
            repo_path=_repository_path(config),
        )
        readiness = _pull_request_merge_readiness(client, pr_number)
        if readiness.get("already_merged") or readiness.get("merged"):
            _mark_pull_request_merged(lane)
            skipped = record_side_effect_skipped(
                config=config,
                lane=lane,
                key=effect_key,
                operation="code_host.merge_pull_request",
                target=f"pull_request:{pr_number}",
                payload=effect_payload,
                reason="pull request already merged on code host",
                result={"readiness": readiness},
            )
            return {
                "status": "ok",
                "method": method,
                "delete_branch": cfg["delete_branch"],
                "readiness": readiness,
                "idempotency_key": effect_key,
                "side_effect": skipped,
                "pull_request": {"number": pr_number, "already_merged": True},
            }
        if not readiness.get("ready"):
            if merge_readiness_is_transient(readiness):
                return {
                    "status": "waiting",
                    "reason": _merge_readiness_error(readiness),
                    "readiness": readiness,
                }
            return {
                "status": "error",
                "error": _merge_readiness_error(readiness),
                "readiness": readiness,
            }
        record_side_effect_started(
            config=config,
            lane=lane,
            key=effect_key,
            operation="code_host.merge_pull_request",
            target=f"pull_request:{pr_number}",
            payload=effect_payload,
        )
        result = client.merge_pull_request(
            pr_number,
            method=method,
            squash=method == "squash",
            delete_branch=cfg["delete_branch"],
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    payload = {
        "status": "ok" if result.get("ok") is not False else "error",
        "method": method,
        "delete_branch": cfg["delete_branch"],
        "pull_request": result,
        "idempotency_key": effect_key,
    }
    if payload["status"] == "error":
        payload["error"] = str(result.get("error") or "pull request merge failed")
        record_side_effect_failed(
            config=config,
            lane=lane,
            key=effect_key,
            operation="code_host.merge_pull_request",
            target=f"pull_request:{pr_number}",
            payload=effect_payload,
            result=payload,
            error=payload["error"],
        )
        ops.append_engine_event(
            config=config,
            lane=lane,
            event_type=f"{config.workflow_name}.lane.auto_merge_failed",
            payload=payload,
            severity="error",
        )
        return payload
    _mark_pull_request_merged(lane)
    payload["side_effect"] = record_side_effect_succeeded(
        config=config,
        lane=lane,
        key=effect_key,
        operation="code_host.merge_pull_request",
        target=f"pull_request:{pr_number}",
        payload=effect_payload,
        result=payload,
    )
    ops.append_engine_event(
        config=config,
        lane=lane,
        event_type=f"{config.workflow_name}.lane.auto_merged",
        payload=payload,
    )
    return payload


def _pull_request_merge_readiness(client: Any, pr_number: str) -> dict[str, Any]:
    checker = getattr(client, "pull_request_merge_status", None)
    if not callable(checker):
        return {
            "ready": True,
            "status": "skipped",
            "reason": "code host does not expose merge readiness",
            "blockers": [],
        }
    readiness = checker(pr_number)
    if not isinstance(readiness, dict):
        return {
            "ready": False,
            "status": "blocked",
            "blockers": [
                {
                    "kind": "invalid_merge_readiness",
                    "message": "code host returned invalid merge readiness payload",
                }
            ],
        }
    return readiness


def _merge_readiness_error(readiness: dict[str, Any]) -> str:
    blockers = (
        readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
    )
    if not blockers:
        return "pull request is not ready to merge"
    first = blockers[0] if isinstance(blockers[0], dict) else {}
    message = str(first.get("message") or first.get("kind") or "").strip()
    if len(blockers) == 1:
        return message or "pull request is not ready to merge"
    return (
        f"{message or 'pull request is not ready to merge'} (+{len(blockers) - 1} more)"
    )


def merge_readiness_is_transient(readiness: dict[str, Any]) -> bool:
    blockers = (
        readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
    )
    if not blockers:
        return False
    for blocker in blockers:
        if not isinstance(blocker, dict):
            return False
        kind = str(blocker.get("kind") or "").strip()
        state = str(blocker.get("state") or "").strip().upper()
        if kind in {"mergeability_unknown", "check_pending"}:
            continue
        if kind == "merge_state_blocked" and state in {"UNKNOWN", "BLOCKED"}:
            continue
        return False
    return True


def _cleanup_completed_lane(
    *, config: WorkflowConfig, lane: dict[str, Any]
) -> dict[str, Any]:
    tracker_cfg = _tracker_config(config)
    if not tracker_cfg:
        return {"status": "skipped", "reason": "no tracker config"}
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    issue_id = str(issue.get("id") or "").strip()
    if not issue_id:
        return {"status": "skipped", "reason": "lane issue is missing id"}
    completion = _completion_labels(config)
    try:
        client = build_tracker_client(
            workflow_root=config.workflow_root,
            tracker_cfg=tracker_cfg,
            repo_path=_repository_path(config),
        )
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    fresh = _refresh_cleanup_issue(client=client, issue_id=issue_id)
    if fresh:
        issue = fresh
        lane["issue"] = fresh
    labels = _issue_labels(issue)
    remove_labels = [
        label for label in completion["remove"] if label.strip().lower() in labels
    ]
    add_labels = [
        label for label in completion["add"] if label.strip().lower() not in labels
    ]
    removed: list[str] = []
    added: list[str] = []
    failed: list[dict[str, Any]] = []
    side_effects: list[dict[str, Any]] = []
    if remove_labels:
        result = _apply_tracker_label_side_effect(
            config=config,
            lane=lane,
            operation="tracker.remove_labels",
            issue_id=issue_id,
            labels=remove_labels,
            call=lambda: client.remove_labels(issue_id, remove_labels),
        )
        side_effects.append(result)
        if result["ok"]:
            removed = remove_labels
            labels.difference_update(label.lower() for label in remove_labels)
        else:
            failed.append(
                {
                    "operation": "remove_labels",
                    "labels": remove_labels,
                    "error": result.get("error"),
                    "idempotency_key": result.get("idempotency_key"),
                }
            )
    if add_labels:
        result = _apply_tracker_label_side_effect(
            config=config,
            lane=lane,
            operation="tracker.add_labels",
            issue_id=issue_id,
            labels=add_labels,
            call=lambda: client.add_labels(issue_id, add_labels),
        )
        side_effects.append(result)
        if result["ok"]:
            added = add_labels
            labels.update(label.lower() for label in add_labels)
        else:
            failed.append(
                {
                    "operation": "add_labels",
                    "labels": add_labels,
                    "error": result.get("error"),
                    "idempotency_key": result.get("idempotency_key"),
                }
            )
    if isinstance(lane.get("issue"), dict):
        lane["issue"] = {**lane["issue"], "labels": sorted(labels)}
    result = {
        "status": "ok",
        "issue_id": issue_id,
        "remove_labels": completion["remove"],
        "add_labels": completion["add"],
        "removed": removed,
        "added": added,
        "side_effects": side_effects,
        "already_removed": [
            label
            for label in completion["remove"]
            if label.strip().lower() not in labels and label not in removed
        ],
        "already_added": [
            label
            for label in completion["add"]
            if label.strip().lower() in labels and label not in added
        ],
    }
    if failed:
        return {
            **result,
            "status": "partial" if removed or added else "error",
            "failed": failed,
            "error": "; ".join(str(item.get("error") or "") for item in failed),
        }
    return result


def _apply_tracker_label_side_effect(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    operation: str,
    issue_id: str,
    labels: list[str],
    call: Callable[[], bool],
) -> dict[str, Any]:
    target = f"issue:{issue_id}"
    payload = {"labels": sorted(labels)}
    key = side_effect_key(
        config=config,
        lane=lane,
        operation=operation,
        target=target,
        payload=payload,
    )
    record_side_effect_started(
        config=config,
        lane=lane,
        key=key,
        operation=operation,
        target=target,
        payload=payload,
    )
    try:
        ok = bool(call())
    except Exception as exc:
        error = str(exc)
        record_side_effect_failed(
            config=config,
            lane=lane,
            key=key,
            operation=operation,
            target=target,
            payload=payload,
            error=error,
        )
        return {"ok": False, "error": error, "idempotency_key": key}
    if not ok:
        error = "tracker returned false"
        record_side_effect_failed(
            config=config,
            lane=lane,
            key=key,
            operation=operation,
            target=target,
            payload=payload,
            error=error,
        )
        return {"ok": False, "error": error, "idempotency_key": key}
    side_effect = record_side_effect_succeeded(
        config=config,
        lane=lane,
        key=key,
        operation=operation,
        target=target,
        payload=payload,
        result={"labels": labels},
    )
    return {"ok": True, "idempotency_key": key, "side_effect": side_effect}


def _refresh_cleanup_issue(*, client: Any, issue_id: str) -> dict[str, Any] | None:
    refresh = getattr(client, "refresh", None)
    if not callable(refresh):
        return None
    try:
        refreshed = refresh([issue_id])
    except Exception:
        return None
    if not isinstance(refreshed, dict):
        return None
    fresh = refreshed.get(issue_id)
    return fresh if isinstance(fresh, dict) else None


def _completion_contract_failure(lane: dict[str, Any]) -> str:
    if _lane_stage(lane) != "review":
        return ""
    review = _lane_mapping(lane, "actor_outputs").get("reviewer")
    if not isinstance(review, dict):
        return "completion requires reviewer output"
    if str(review.get("status") or "").strip().lower() != "approved":
        return "completion requires reviewer status `approved`"
    if not _pull_request_url(lane):
        return "completion requires pull_request.url"
    return ""


def _contract_artifacts(lane: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": lane.get("stage"),
        "actor_outputs": lane.get("actor_outputs"),
        "pull_request": lane.get("pull_request"),
        "branch": lane.get("branch"),
        "completion_auto_merge": lane.get("completion_auto_merge"),
    }


def _pull_request_url(lane: dict[str, Any]) -> str:
    pull_request = lane.get("pull_request")
    if isinstance(pull_request, dict):
        return str(pull_request.get("url") or "").strip()
    return ""


def _pull_request_is_merged(lane: dict[str, Any]) -> bool:
    pull_request = lane.get("pull_request")
    if not isinstance(pull_request, dict):
        return False
    state = str(pull_request.get("state") or pull_request.get("status") or "").lower()
    return bool(pull_request.get("merged")) or state == "merged"


def _mark_pull_request_merged(lane: dict[str, Any]) -> None:
    pull_request = _lane_mapping(lane, "pull_request")
    pull_request["state"] = "merged"
    pull_request["merged"] = True
    pull_request["merged_at"] = pull_request.get("merged_at") or _now_iso()


def _pull_request_number(lane: dict[str, Any]) -> str:
    pull_request = lane.get("pull_request")
    if not isinstance(pull_request, dict):
        return ""
    for key in ("number", "pr_number"):
        value = pull_request.get(key)
        if value not in (None, ""):
            number = _trailing_number(value)
            if number:
                return number
    url = str(pull_request.get("url") or "").strip()
    match = re.search(r"/pull/([0-9]+)(?:$|[/?#])", url)
    if match:
        return match.group(1)
    return _trailing_number(pull_request.get("id"))


def _trailing_number(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"([0-9]+)$", text)
    return match.group(1) if match else ""


def _completion_labels(config: WorkflowConfig) -> dict[str, list[str]]:
    raw = config.raw.get("completion")
    cfg = raw if isinstance(raw, dict) else {}
    return {
        "remove": _configured_texts(cfg, "remove_labels", "remove-labels")
        or ["active"],
        "add": _configured_texts(cfg, "add_labels", "add-labels") or ["done"],
    }


def _completion_auto_merge_config(config: WorkflowConfig) -> dict[str, Any]:
    raw = config.raw.get("completion")
    completion = raw if isinstance(raw, dict) else {}
    raw_auto_merge = (
        completion.get("auto-merge")
        or completion.get("auto_merge")
        or completion.get("automerge")
    )
    cfg = raw_auto_merge if isinstance(raw_auto_merge, dict) else {}
    method = (
        str(
            cfg.get("method")
            or cfg.get("merge-method")
            or cfg.get("merge_method")
            or "squash"
        )
        .strip()
        .lower()
    )
    return {
        "enabled": _configured_bool(cfg, "enabled", default=False),
        "method": method or "squash",
        "delete_branch": _configured_bool(
            cfg, "delete-branch", "delete_branch", default=True
        ),
    }


def _retry_event_retry(retry: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": retry.get("status"),
        "stage": retry.get("stage"),
        "target": retry.get("target"),
        "reason": retry.get("reason"),
        "attempt": retry.get("attempt") or retry.get("next_attempt"),
        "current_attempt": retry.get("current_attempt"),
        "max_attempts": retry.get("max_attempts"),
        "delay_seconds": retry.get("delay_seconds"),
        "backoff_seconds": retry.get("backoff_seconds") or retry.get("delay_seconds"),
        "due_at": retry.get("due_at"),
        "due_at_epoch": retry.get("due_at_epoch"),
        "queued_at": retry.get("queued_at"),
    }

def _configured_bool(config: dict[str, Any], *keys: str, default: bool) -> bool:
    for key in keys:
        value = config.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default
