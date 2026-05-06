"""Pull request review signals for step-based lanes."""

from __future__ import annotations

from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.trackers import build_code_host_client
from sprints.workflows.lane_state import (
    append_engine_event,
    code_host_config,
    normalize_pull_request,
    now_iso,
    repository_path,
)
from sprints.workflows.surface_pull_request import pull_request_number

_MAX_REVIEW_CONTEXT_ITEMS = 8
_MAX_COMMENT_TEXT = 600
_SPRINTS_COMMENT_MARKERS = ("sprints-workpad", "sprints:idempotency-key")
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
    pr_lanes = [lane for lane in lanes if pull_request_number(lane)]
    if not pr_lanes:
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
    for lane in pr_lanes:
        number = pull_request_number(lane)
        try:
            readiness = client.pull_request_merge_status(number)
        except Exception as exc:
            errors.append(
                {
                    "lane_id": lane.get("lane_id"),
                    "pull_request": number,
                    "error": str(exc),
                }
            )
            continue
        if not isinstance(readiness, dict):
            errors.append(
                {
                    "lane_id": lane.get("lane_id"),
                    "pull_request": number,
                    "error": "code host returned invalid review signal payload",
                }
            )
            continue
        context = _collect_review_context(client=client, pr_number=number)
        signals = _build_review_signals(
            lane=lane,
            readiness=readiness,
            context=context,
        )
        previous = lane.get("review_signals")
        lane["review_signals"] = signals
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


def _build_review_signals(
    *,
    lane: dict[str, Any],
    readiness: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    blockers = [
        blocker for blocker in readiness.get("blockers") or [] if isinstance(blocker, dict)
    ]
    required_changes = _required_changes_from_blockers(blockers)
    pending = _pending_review_items(blockers)
    approvals = _approval_items(readiness=readiness)
    pull_request = readiness.get("pull_request")
    return {
        key: value
        for key, value in {
            "required_changes": required_changes,
            "approvals": approvals,
            "pending": pending,
            "blockers": blockers,
            "checks": _check_items(blockers),
            **_compact_review_context(context),
            "merge_readiness": _compact_merge_readiness(readiness),
            "pull_request": pull_request if isinstance(pull_request, dict) else None,
            "updated_at": now_iso(),
        }.items()
        if value not in (None, "", [], {})
    }


def _collect_review_context(*, client: Any, pr_number: str) -> dict[str, Any]:
    context: dict[str, Any] = {
        "reviews": [],
        "pull_request_comments": [],
        "review_threads": {},
        "errors": [],
    }
    for key, method_name in (
        ("reviews", "fetch_pull_request_reviews"),
        ("pull_request_comments", "fetch_pull_request_comments"),
        ("review_threads", "fetch_pull_request_review_threads"),
    ):
        method = getattr(client, method_name, None)
        if not callable(method):
            continue
        try:
            context[key] = method(pr_number)
        except Exception as exc:
            context["errors"].append(
                {
                    "source": method_name,
                    "pull_request": pr_number,
                    "error": str(exc),
                }
            )
    if not context["errors"]:
        context.pop("errors", None)
    return context


def _compact_review_context(context: dict[str, Any]) -> dict[str, Any]:
    comments = [
        *_compact_comments(context.get("pull_request_comments"), source="pull_request"),
        *_compact_comments(
            _review_thread_comments(context.get("review_threads")),
            source="review_thread",
        ),
    ][-_MAX_REVIEW_CONTEXT_ITEMS:]
    return {
        key: value
        for key, value in {
            "reviews": _compact_reviews(context.get("reviews")),
            "comments": comments,
            "context_errors": context.get("errors"),
        }.items()
        if value not in (None, "", [], {})
    }


def _compact_reviews(value: Any) -> list[dict[str, Any]]:
    reviews = [item for item in value or [] if isinstance(item, dict)]
    compacted: list[dict[str, Any]] = []
    for review in reviews[-_MAX_REVIEW_CONTEXT_ITEMS:]:
        user = review.get("user") if isinstance(review.get("user"), dict) else {}
        compacted.append(
            {
                key: field
                for key, field in {
                    "id": review.get("id"),
                    "state": review.get("state"),
                    "author": user.get("login"),
                    "body": _compact_text(review.get("body")),
                    "url": review.get("html_url") or review.get("url"),
                    "submitted_at": review.get("submitted_at"),
                }.items()
                if field not in (None, "", [], {})
            }
        )
    return compacted


def _compact_comments(value: Any, *, source: str) -> list[dict[str, Any]]:
    comments = [item for item in value or [] if isinstance(item, dict)]
    compacted: list[dict[str, Any]] = []
    for comment in comments:
        body = str(comment.get("body") or "").strip()
        if not body or _is_sprints_comment(body):
            continue
        user = (
            comment.get("user")
            if isinstance(comment.get("user"), dict)
            else comment.get("author")
            if isinstance(comment.get("author"), dict)
            else {}
        )
        compacted.append(
            {
                key: field
                for key, field in {
                    "source": source,
                    "id": comment.get("id"),
                    "author": user.get("login"),
                    "body": _compact_text(body),
                    "url": comment.get("html_url") or comment.get("url"),
                    "created_at": comment.get("created_at") or comment.get("createdAt"),
                    "path": comment.get("path"),
                    "line": comment.get("line"),
                }.items()
                if field not in (None, "", [], {})
            }
        )
    return compacted[-_MAX_REVIEW_CONTEXT_ITEMS:]


def _review_thread_comments(threads: Any) -> list[dict[str, Any]]:
    review_threads = threads.get("reviewThreads") if isinstance(threads, dict) else {}
    nodes = review_threads.get("nodes") if isinstance(review_threads, dict) else []
    comments: list[dict[str, Any]] = []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        comment_block = (
            node.get("comments") if isinstance(node.get("comments"), dict) else {}
        )
        for comment in comment_block.get("nodes") or []:
            if not isinstance(comment, dict):
                continue
            comments.append(
                {
                    **comment,
                    "path": node.get("path"),
                    "line": node.get("line"),
                    "thread_id": node.get("id"),
                    "thread_resolved": node.get("isResolved"),
                    "thread_outdated": node.get("isOutdated"),
                }
            )
    return comments


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


def _approval_items(*, readiness: dict[str, Any]) -> list[dict[str, Any]]:
    approvals: list[dict[str, Any]] = []
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


def _check_items(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _blocker_item(blocker=blocker, source="github_check")
        for blocker in blockers
        if str(blocker.get("kind") or "").startswith("check_")
    ]


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


def _compact_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= _MAX_COMMENT_TEXT:
        return text
    return text[: _MAX_COMMENT_TEXT - 1].rstrip() + "."


def _is_sprints_comment(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _SPRINTS_COMMENT_MARKERS)
