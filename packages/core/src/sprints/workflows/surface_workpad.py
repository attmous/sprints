"""Persistent compact issue workpad comments for tracker-backed lanes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sprints.workflows.lane_state import now_iso

WORKPAD_MARKER = "<!-- sprints-workpad -->"


@dataclass(frozen=True)
class WorkpadResult:
    action: str
    comment: dict[str, Any]
    body: str


def render_workpad(lane: Mapping[str, Any]) -> str:
    """Render a compact, durable status note for humans and actors."""
    tracker = _mapping(lane.get("tracker"))
    issue = _mapping(lane.get("issue"))
    pull_request = _mapping(lane.get("pull_request"))
    last_output = _mapping(lane.get("last_actor_output"))
    retry = _mapping(lane.get("pending_retry"))
    operator_attention = _mapping(lane.get("operator_attention"))

    step = tracker.get("step") or lane.get("step")
    step_labels = tracker.get("step_labels")
    branch = lane.get("branch") or issue.get("branch_name")
    pr = _pull_request_text(pull_request)
    last_actor = lane.get("actor") or last_output.get("actor")
    last_result = _first_present(
        last_output.get("status"),
        last_output.get("result"),
        last_output.get("decision"),
        last_output.get("outcome"),
    )
    next_state = _first_present(
        lane.get("next_expected_state"),
        lane.get("next_state"),
        lane.get("stage"),
        step,
    )

    lines = [
        WORKPAD_MARKER,
        scoped_workpad_marker(lane),
        "### Sprints workpad",
        "",
        f"- Lane: `{_text(lane.get('lane_id'), 'unknown')}`",
        f"- Attempt: `{_text(lane.get('attempt'), '1')}`",
    ]
    if step:
        labels = (
            f" ({', '.join(str(label) for label in step_labels)})"
            if step_labels
            else ""
        )
        lines.append(f"- Step: `{step}`{labels}")
    elif issue.get("state"):
        lines.append(f"- Tracker state: `{issue.get('state')}`")
    if branch:
        lines.append(f"- Branch: `{branch}`")
    if pr:
        lines.append(f"- PR: {pr}")
    if last_actor or last_result:
        lines.append(
            "- Last actor/result: "
            f"`{_text(last_actor, 'unknown')}` / `{_text(last_result, 'unknown')}`"
        )
    if next_state:
        lines.append(f"- Next/current: `{next_state}`")

    retry_summary = _retry_summary(retry)
    if retry_summary:
        lines.append(f"- Retry: {retry_summary}")
    blocker_summary = _blocker_summary(issue, operator_attention)
    if blocker_summary:
        lines.append(f"- Blocker: {blocker_summary}")

    return "\n".join(lines).rstrip() + "\n"


def find_workpad_comment(
    comments: Sequence[Mapping[str, Any]], lane_id: str | None = None
) -> dict[str, Any] | None:
    scoped_marker = scoped_workpad_marker({"lane_id": lane_id}) if lane_id else None
    if scoped_marker:
        for comment in comments:
            body = str(comment.get("body") or "")
            if scoped_marker in body:
                return dict(comment)
    for comment in comments:
        body = str(comment.get("body") or "")
        if WORKPAD_MARKER in body and (
            not lane_id or f"- Lane: `{lane_id}`" in body
        ):
            return dict(comment)
    return None


def scoped_workpad_marker(lane: Mapping[str, Any]) -> str:
    lane_id = _text(lane.get("lane_id"), "unknown")
    return f"<!-- sprints-workpad:{lane_id} -->"


def ensure_workpad(tracker: Any, lane: dict[str, Any], state: Any = None) -> WorkpadResult:
    del state
    issue = _mapping(lane.get("issue"))
    issue_id = issue.get("id")
    if issue_id in (None, ""):
        raise ValueError("lane issue is missing id")

    body = render_workpad(lane)
    comments = tracker.list_issue_comments(issue_id)
    existing = find_workpad_comment(comments, str(lane.get("lane_id") or ""))
    if existing:
        comment_id = existing.get("id")
        if comment_id in (None, ""):
            raise ValueError("workpad marker comment is missing id")
        comment = tracker.update_issue_comment(str(comment_id), body)
        action = "updated"
    else:
        comment = tracker.create_issue_comment(issue_id, body)
        action = "created"

    lane["workpad"] = _workpad_metadata(comment)
    return WorkpadResult(action=action, comment=comment, body=body)


def record_workpad_failure(
    lane: dict[str, Any],
    error: str,
    *,
    retryable: bool = True,
    blocked_status: str | None = None,
) -> dict[str, Any]:
    metadata = {
        "status": "failed",
        "error": str(error or "workpad ensure failed"),
        "last_attempt_at": now_iso(),
        "retryable": retryable,
    }
    if blocked_status:
        metadata["blocked_status"] = blocked_status
    lane["workpad"] = metadata
    return metadata


def record_workpad_skipped(lane: dict[str, Any], reason: str) -> dict[str, Any]:
    metadata = {
        "status": "skipped",
        "reason": str(reason or "workpad comments unsupported"),
        "unsupported": True,
        "last_attempt_at": now_iso(),
    }
    lane["workpad"] = metadata
    return metadata


def _workpad_metadata(comment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "status": "ok",
            "comment_id": comment.get("id"),
            "url": comment.get("html_url") or comment.get("url"),
            "last_updated_at": comment.get("updated_at")
            or comment.get("updatedAt")
            or now_iso(),
        }.items()
        if value not in (None, "")
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _pull_request_text(pull_request: Mapping[str, Any]) -> str | None:
    if not pull_request:
        return None
    url = str(pull_request.get("url") or "").strip()
    number = str(pull_request.get("number") or "").strip()
    if url and number:
        return f"[#{number}]({url})"
    if url:
        return url
    if number:
        return f"`#{number}`"
    return None


def _retry_summary(retry: Mapping[str, Any]) -> str | None:
    if not retry:
        return None
    reason = _text(retry.get("reason") or retry.get("failure_reason"), "pending")
    attempt = retry.get("attempt") or retry.get("current_attempt")
    due_at = retry.get("due_at")
    parts = [f"`{reason}`"]
    if attempt not in (None, ""):
        parts.append(f"attempt `{attempt}`")
    if due_at:
        parts.append(f"due `{due_at}`")
    return ", ".join(parts)


def _blocker_summary(
    issue: Mapping[str, Any], operator_attention: Mapping[str, Any]
) -> str | None:
    blockers = issue.get("blocked_by") or []
    if isinstance(blockers, Sequence) and blockers:
        first = blockers[0]
        if isinstance(first, Mapping):
            ident = first.get("identifier") or first.get("id") or "unknown"
            state = first.get("state")
            suffix = f" (`{state}`)" if state else ""
            extra = "" if len(blockers) == 1 else f" +{len(blockers) - 1} more"
            return f"`{ident}`{suffix}{extra}"
        return f"{len(blockers)} blocker(s)"
    if operator_attention:
        return f"`{_text(operator_attention.get('reason'), 'operator attention')}`"
    return None
