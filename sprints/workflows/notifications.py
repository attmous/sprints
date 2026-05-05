"""Workflow notifications for review feedback handoff."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from trackers import build_code_host_client
from workflows.config import WorkflowConfig
from workflows.lane_state import (
    _append_engine_event,
    _code_host_config,
    _now_iso,
    _repository_path,
    _review_notification_config,
    lane_list,
)


def _notify_review_changes_requested(
    *, config: WorkflowConfig, lane: dict[str, Any], output: dict[str, Any]
) -> dict[str, Any]:
    notification_cfg = _review_notification_config(config)
    fingerprint = _review_changes_requested_fingerprint(lane=lane, output=output)
    existing = _existing_review_notification(lane=lane, fingerprint=fingerprint)
    if existing:
        return existing
    if not any(notification_cfg.values()):
        return _record_lane_notification(
            config=config,
            lane=lane,
            payload={
                "event": "review_changes_requested",
                "status": "skipped",
                "fingerprint": fingerprint,
                "reason": "notifications disabled",
            },
        )
    code_host_cfg = _code_host_config(config)
    if not code_host_cfg:
        return _record_lane_notification(
            config=config,
            lane=lane,
            payload={
                "event": "review_changes_requested",
                "status": "skipped",
                "fingerprint": fingerprint,
                "reason": "no code-host config",
            },
        )
    body = _review_changes_requested_body(lane=lane, output=output)
    result: dict[str, Any] = {
        "event": "review_changes_requested",
        "status": "ok",
        "fingerprint": fingerprint,
        "targets": {},
    }
    try:
        client = build_code_host_client(
            workflow_root=config.workflow_root,
            code_host_cfg=code_host_cfg,
            repo_path=_repository_path(config),
        )
        if notification_cfg["pull_request_comment"]:
            pr_number = _pull_request_number(lane)
            result["targets"]["pull_request"] = (
                client.comment_on_pull_request(pr_number, body=body)
                if pr_number
                else {"ok": False, "error": "pull request number missing"}
            )
        if notification_cfg["pull_request_review"]:
            pr_number = _pull_request_number(lane)
            result["targets"]["pull_request_review"] = (
                client.request_changes_on_pull_request(pr_number, body=body)
                if pr_number
                else {"ok": False, "error": "pull request number missing"}
            )
        if notification_cfg["issue_comment"]:
            issue_number = _issue_number(lane)
            result["targets"]["issue"] = (
                client.comment_on_issue(issue_number, body=body)
                if issue_number
                else {"ok": False, "error": "issue number missing"}
            )
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    if (
        any(
            isinstance(target, dict) and target.get("ok") is False
            for target in dict(result.get("targets") or {}).values()
        )
        and result.get("status") == "ok"
    ):
        result["status"] = "partial"
    return _record_lane_notification(config=config, lane=lane, payload=result)


def _existing_review_notification(
    *, lane: dict[str, Any], fingerprint: str
) -> dict[str, Any] | None:
    for record in reversed(lane_list(lane, "notifications")):
        if not isinstance(record, dict):
            continue
        if record.get("event") != "review_changes_requested":
            continue
        if record.get("fingerprint") != fingerprint:
            continue
        if record.get("status") in {"ok", "partial"}:
            return record
    return None


def _review_changes_requested_fingerprint(
    *, lane: dict[str, Any], output: dict[str, Any]
) -> str:
    payload = {
        "lane_id": lane.get("lane_id"),
        "pull_request": _pull_request_number(lane),
        "issue": _issue_number(lane),
        "status": output.get("status"),
        "summary": output.get("summary"),
        "required_fixes": output.get("required_fixes"),
        "findings": output.get("findings"),
        "verification_gaps": output.get("verification_gaps"),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_lane_notification(
    *, config: WorkflowConfig, lane: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    record = {"created_at": _now_iso(), **payload}
    lane_list(lane, "notifications").append(record)
    _append_engine_event(
        config=config,
        lane=lane,
        event_type=f"{config.workflow_name}.lane.notification",
        payload=record,
        severity="warning" if record.get("status") in {"error", "partial"} else "info",
    )
    return record


def _review_changes_requested_body(
    *, lane: dict[str, Any], output: dict[str, Any]
) -> str:
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    lines = [
        "### Sprints review requested changes",
        "",
        f"Lane: {lane.get('lane_id')}",
    ]
    issue_label = " ".join(
        part
        for part in [
            str(issue.get("identifier") or issue.get("id") or "").strip(),
            str(issue.get("title") or "").strip(),
        ]
        if part
    )
    if issue_label:
        lines.append(f"Issue: {issue_label}")
    summary = str(output.get("summary") or "").strip()
    if summary:
        lines.extend(["", "Summary:", summary])
    _append_markdown_items(lines, "Required fixes", output.get("required_fixes"))
    _append_markdown_items(lines, "Findings", output.get("findings"))
    _append_markdown_items(lines, "Verification gaps", output.get("verification_gaps"))
    lines.extend(["", "Generated by Sprints."])
    return "\n".join(lines).strip()


def _append_markdown_items(lines: list[str], title: str, value: Any) -> None:
    if not isinstance(value, list) or not value:
        return
    lines.extend(["", f"{title}:"])
    for index, item in enumerate(value, start=1):
        lines.append(f"{index}. {_markdown_item_text(item)}")


def _markdown_item_text(item: Any) -> str:
    if isinstance(item, dict):
        parts = [
            f"{key}: {item[key]}"
            for key in sorted(item)
            if item.get(key) not in (None, "", [], {})
        ]
        return "; ".join(parts) or "{}"
    return str(item)


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


def _issue_number(lane: dict[str, Any]) -> str:
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    for key in ("number", "id", "identifier"):
        value = issue.get(key)
        if value not in (None, ""):
            number = _trailing_number(value)
            if number:
                return number
    return ""


def _trailing_number(value: Any) -> str:
    text = str(value or "").strip().lstrip("#")
    match = re.search(r"([0-9]+)$", text)
    return match.group(1) if match else ""
