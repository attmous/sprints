"""Shared review signal reconciliation for actor-driven lanes."""

from __future__ import annotations

import re
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.trackers import build_code_host_client
from sprints.workflows.board_state import BoardState, state_from_labels
from sprints.workflows.lane_state import (
    append_engine_event,
    code_host_config,
    lane_mapping,
    normalize_pull_request,
    now_iso,
    repository_path,
)
from sprints.workflows.review_context import (
    collect_review_context,
    compact_review_context,
)
from sprints.workflows.sessions import active_actor_dispatch


_REQUIRED_BLOCKER_KINDS = {
    "check_failed",
    "merge_conflict",
    "unresolved_review_thread",
}
_PENDING_BLOCKER_KINDS = {
    "check_pending",
    "mergeability_unknown",
    "review_not_approved",
}
def reconcile_review_signals(
    *, config: WorkflowConfig, lanes: list[dict[str, Any]]
) -> dict[str, Any]:
    if not config.is_actor_driven():
        return {"status": "skipped", "reason": "workflow is not actor-driven"}
    review_lanes = [lane for lane in lanes if _pull_request_number(lane)]
    if not review_lanes:
        return {"status": "skipped", "reason": "no lane pull requests"}
    code_host_cfg = code_host_config(config)
    if not code_host_cfg:
        return {"status": "skipped", "reason": "no code-host config"}
    try:
        client = build_code_host_client(
            workflow_root=config.workflow_root,
            code_host_cfg=code_host_cfg,
            repo_path=repository_path(config),
        )
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    updated: list[str] = []
    errors: list[dict[str, Any]] = []
    for lane in review_lanes:
        pr_number = _pull_request_number(lane)
        try:
            readiness = client.pull_request_merge_status(pr_number)
        except Exception as exc:
            errors.append(
                {
                    "lane_id": lane.get("lane_id"),
                    "pull_request": pr_number,
                    "error": str(exc),
                }
            )
            continue
        if not isinstance(readiness, dict):
            errors.append(
                {
                    "lane_id": lane.get("lane_id"),
                    "pull_request": pr_number,
                    "error": "code host returned invalid review signal payload",
                }
            )
            continue
        context = collect_review_context(client=client, pr_number=pr_number)
        signals = build_review_signals(
            config=config,
            lane=lane,
            readiness=readiness,
            context=context,
        )
        previous = lane.get("review_signals")
        lane["review_signals"] = signals
        lane["merge_signal"] = merge_signal_for_lane(config=config, lane=lane)
        _refresh_pull_request_from_readiness(lane=lane, readiness=readiness)
        if previous != signals:
            append_engine_event(
                config=config,
                lane=lane,
                event_type=f"{config.workflow_name}.lane.review_signals",
                payload={"review_signals": signals},
            )
        updated.append(str(lane.get("lane_id") or ""))
    if errors and not updated:
        return {"status": "error", "errors": errors}
    return {
        "status": "ok" if not errors else "partial",
        "updated": updated,
        "errors": errors,
    }


def build_review_signals(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    readiness: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = readiness if isinstance(readiness, dict) else {}
    blockers = [
        blocker for blocker in readiness.get("blockers") or [] if isinstance(blocker, dict)
    ]
    compact_context = compact_review_context(context or {})
    reviewer = _reviewer_output(lane)
    required_changes = _required_changes_from_reviewer(reviewer)
    required_changes.extend(_required_changes_from_blockers(blockers))
    pending = _pending_review_items(blockers)
    approvals = _approval_items(reviewer=reviewer, readiness=readiness)
    merge_signal = merge_signal_for_lane(config=config, lane=lane)
    reviewer_running = reviewer_actor_running(lane)
    pull_request = readiness.get("pull_request")
    return {
        key: value
        for key, value in {
            "required_changes": required_changes,
            "approvals": approvals,
            "pending": pending,
            "blockers": blockers,
            "checks": _check_items(blockers),
            **compact_context,
            "reviewer_actor_running": reviewer_running,
            "reviewer_actor_result": _compact_reviewer_output(reviewer),
            "merge_signal_seen": bool(merge_signal.get("seen")),
            "merge_signal": merge_signal or None,
            "merge_readiness": _compact_merge_readiness(readiness),
            "pull_request": pull_request if isinstance(pull_request, dict) else None,
            "updated_at": now_iso(),
        }.items()
        if value not in (None, "", [], {})
    }


def merge_signal_for_lane(*, config: WorkflowConfig, lane: dict[str, Any]) -> dict[str, Any]:
    board_state = _lane_board_state(config=config, lane=lane)
    configured = _merge_signal_state(config)
    seen = board_state == configured
    return {
        "seen": seen,
        "state": board_state,
        "required_state": configured,
        "source": "labels",
    }


def review_required_changes(lane: dict[str, Any]) -> list[dict[str, Any]]:
    signals = (
        lane.get("review_signals")
        if isinstance(lane.get("review_signals"), dict)
        else {}
    )
    changes = signals.get("required_changes")
    return [item for item in changes or [] if isinstance(item, dict)]


def review_has_required_changes(lane: dict[str, Any]) -> bool:
    return bool(review_required_changes(lane))


def reviewer_actor_running(lane: dict[str, Any]) -> bool:
    dispatch = active_actor_dispatch(lane)
    if dispatch and str(dispatch.get("actor") or "").strip() == "reviewer":
        return True
    if (
        str(lane.get("status") or "").strip() == "running"
        and str(lane.get("actor") or "").strip() == "reviewer"
    ):
        return True
    session = lane.get("runtime_session") if isinstance(lane.get("runtime_session"), dict) else {}
    return (
        str(session.get("actor") or "").strip() == "reviewer"
        and str(session.get("status") or "").strip() in {"running", "dispatching"}
    )


def review_actor_enabled(config: WorkflowConfig) -> bool:
    raw = config.raw.get("review")
    review_cfg = raw if isinstance(raw, dict) else {}
    actor_cfg = review_cfg.get("actor") if isinstance(review_cfg.get("actor"), dict) else {}
    enabled = actor_cfg.get("enabled")
    if enabled is None:
        return "reviewer" in config.actors
    if isinstance(enabled, bool):
        return enabled
    return str(enabled).strip().lower() in {"1", "true", "yes", "on"}


def _required_changes_from_reviewer(reviewer: dict[str, Any]) -> list[dict[str, Any]]:
    status = str(reviewer.get("status") or "").strip().lower()
    if status not in {"changes_requested", "needs_changes"}:
        return []
    fixes = reviewer.get("required_fixes")
    if isinstance(fixes, list) and fixes:
        return [
            {
                "source": "reviewer",
                "kind": "reviewer_required_fix",
                "message": _required_fix_message(item),
                "detail": item,
            }
            for item in fixes
        ]
    return [
        {
            "source": "reviewer",
            "kind": "reviewer_changes_requested",
            "message": str(reviewer.get("summary") or "reviewer requested changes"),
        }
    ]


def _required_changes_from_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required: list[dict[str, Any]] = []
    for blocker in blockers:
        kind = str(blocker.get("kind") or "").strip()
        state = str(blocker.get("state") or "").strip().upper()
        if kind == "review_not_approved" and state == "CHANGES_REQUESTED":
            required.append(_blocker_item(blocker=blocker, source="github_review"))
            continue
        if kind in _REQUIRED_BLOCKER_KINDS:
            required.append(_blocker_item(blocker=blocker, source="github_pr"))
    return required


def _pending_review_items(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for blocker in blockers:
        kind = str(blocker.get("kind") or "").strip()
        state = str(blocker.get("state") or "").strip().upper()
        if kind == "review_not_approved" and state == "REVIEW_REQUIRED":
            pending.append(_blocker_item(blocker=blocker, source="github_review"))
            continue
        if kind in _PENDING_BLOCKER_KINDS:
            pending.append(_blocker_item(blocker=blocker, source="github_pr"))
    return pending


def _approval_items(*, reviewer: dict[str, Any], readiness: dict[str, Any]) -> list[dict[str, Any]]:
    approvals: list[dict[str, Any]] = []
    if str(reviewer.get("status") or "").strip().lower() == "approved":
        approvals.append(
            {
                "source": "reviewer",
                "message": str(reviewer.get("summary") or "reviewer approved"),
            }
        )
    pull_request = readiness.get("pull_request")
    pr = pull_request if isinstance(pull_request, dict) else {}
    if str(pr.get("review_decision") or "").strip().upper() == "APPROVED":
        approvals.append({"source": "github_review", "message": "GitHub review approved"})
    return approvals


def _blocker_item(*, blocker: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "source": source,
            "kind": blocker.get("kind"),
            "message": blocker.get("message"),
            "path": blocker.get("path"),
            "line": blocker.get("line"),
            "name": blocker.get("name"),
            "state": blocker.get("state"),
            "status": blocker.get("status"),
            "thread_id": blocker.get("thread_id"),
        }.items()
        if value not in (None, "", [], {})
    }


def _required_fix_message(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("change") or item.get("issue") or item.get("reason") or item)
    return str(item)


def _reviewer_output(lane: dict[str, Any]) -> dict[str, Any]:
    outputs = lane_mapping(lane, "actor_outputs")
    review = outputs.get("reviewer")
    return review if isinstance(review, dict) else {}


def _compact_reviewer_output(reviewer: dict[str, Any]) -> dict[str, Any]:
    return {
        key: reviewer.get(key)
        for key in ("status", "summary", "required_fixes", "findings", "verification_gaps")
        if reviewer.get(key) not in (None, "", [], {})
    }


def _compact_merge_readiness(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        key: readiness.get(key)
        for key in ("ready", "status", "already_merged", "merged")
        if readiness.get(key) not in (None, "", [], {})
    }


def _refresh_pull_request_from_readiness(*, lane: dict[str, Any], readiness: dict[str, Any]) -> None:
    pull_request = readiness.get("pull_request")
    if not isinstance(pull_request, dict):
        return
    existing = lane.get("pull_request") if isinstance(lane.get("pull_request"), dict) else {}
    lane["pull_request"] = normalize_pull_request({**existing, **pull_request})


def _lane_board_state(*, config: WorkflowConfig, lane: dict[str, Any]) -> str:
    tracker = lane.get("tracker") if isinstance(lane.get("tracker"), dict) else {}
    board_state = str(tracker.get("board_state") or lane.get("board_state") or "").strip()
    if board_state:
        return board_state
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    return str(state_from_labels(issue.get("labels") or [], config) or "")


def _merge_signal_state(config: WorkflowConfig) -> str:
    raw = config.raw.get("review")
    review_cfg = raw if isinstance(raw, dict) else {}
    signal_cfg = review_cfg.get("merge-signal") or review_cfg.get("merge_signal")
    cfg = signal_cfg if isinstance(signal_cfg, dict) else {}
    return str(cfg.get("state") or BoardState.MERGING.value).strip() or BoardState.MERGING.value


def _check_items(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _blocker_item(blocker=blocker, source="github_check")
        for blocker in blockers
        if str(blocker.get("kind") or "").startswith("check_")
    ]


def _pull_request_number(lane: dict[str, Any]) -> str:
    pull_request = lane.get("pull_request")
    if not isinstance(pull_request, dict):
        return ""
    for key in ("number", "pr_number", "id"):
        value = pull_request.get(key)
        if value not in (None, ""):
            text = str(value).strip()
            if text:
                return text.lstrip("#")
    url = str(pull_request.get("url") or "").strip()
    match = re.search(r"/pull/(\d+)(?:\b|$)", url)
    return match.group(1) if match else ""
