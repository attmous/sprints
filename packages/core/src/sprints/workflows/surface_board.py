"""Label-backed board state mechanics for workflow lanes."""

from __future__ import annotations

from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.trackers import build_tracker_client
from sprints.workflows.surface_board_state import BoardState, desired_state_mutation
from sprints.workflows.state_effects import (
    completed_side_effect,
    record_side_effect_failed,
    record_side_effect_skipped,
    record_side_effect_started,
    record_side_effect_succeeded,
    side_effect_key,
)
from sprints.workflows.lane_state import (
    append_engine_event,
    refresh_lane_board_metadata,
    repository_path,
    tracker_config,
)


def set_lane_board_state(
    *, config: WorkflowConfig, lane: dict[str, Any], target: BoardState
) -> dict[str, Any]:
    tracker_cfg = tracker_config(config)
    if not tracker_cfg:
        return {"status": "skipped", "reason": "no tracker config"}
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    issue_id = issue.get("id")
    try:
        mutation = desired_state_mutation(issue.get("labels") or [], target, config)
    except Exception as exc:
        return {"status": "failed", "error": str(exc), "target": target.value}
    if not mutation.add and not mutation.remove:
        refresh_lane_board_metadata(config=config, lane=lane, issue=issue)
        skipped = _record_board_state_side_effect_skipped(
            config=config,
            lane=lane,
            issue_id=issue_id,
            target=target,
            mutation=mutation,
            reason="state labels already match target",
        )
        return {
            "status": "ok",
            "changed": False,
            "target": target.value,
            "side_effect": skipped,
        }
    effect_key = _board_state_side_effect_key(
        config=config,
        lane=lane,
        issue_id=issue_id,
        target=target,
        mutation=mutation,
    )
    completed = completed_side_effect(config=config, lane=lane, key=effect_key)
    if completed:
        _apply_label_mutation(issue=issue, add=mutation.add, remove=mutation.remove)
        refresh_lane_board_metadata(config=config, lane=lane, issue=issue)
        return {
            "status": "ok",
            "changed": False,
            "target": target.value,
            "idempotency_key": effect_key,
            "side_effect": completed,
            "reason": "board state side effect already completed",
        }
    payload = {
        "target": target.value,
        "add": mutation.add,
        "remove": mutation.remove,
    }
    target_key = _board_state_side_effect_target(issue_id=issue_id, target=target)
    record_side_effect_started(
        config=config,
        lane=lane,
        key=effect_key,
        operation="tracker.set_issue_state_label",
        target=target_key,
        payload=payload,
    )
    try:
        client = build_tracker_client(
            workflow_root=config.workflow_root,
            tracker_cfg=tracker_cfg,
            repo_path=repository_path(config),
        )
        changed = client.set_issue_state_label(
            issue_id, add=mutation.add, remove=mutation.remove
        )
    except Exception as exc:
        record_side_effect_failed(
            config=config,
            lane=lane,
            key=effect_key,
            operation="tracker.set_issue_state_label",
            target=target_key,
            payload=payload,
            error=str(exc),
        )
        append_engine_event(
            config=config,
            lane=lane,
            event_type=f"{config.workflow_name}.lane.board_state_update_failed",
            payload={
                "target": target.value,
                "add": mutation.add,
                "remove": mutation.remove,
                "error": str(exc),
            },
            severity="warning",
        )
        return {"status": "failed", "error": str(exc), "target": target.value}
    if not changed:
        record_side_effect_failed(
            config=config,
            lane=lane,
            key=effect_key,
            operation="tracker.set_issue_state_label",
            target=target_key,
            payload=payload,
            error="tracker did not apply requested state label mutation",
        )
        return {
            "status": "failed",
            "error": "tracker did not apply requested state label mutation",
            "target": target.value,
            "add": mutation.add,
            "remove": mutation.remove,
        }
    _apply_label_mutation(issue=issue, add=mutation.add, remove=mutation.remove)
    refresh_lane_board_metadata(config=config, lane=lane, issue=issue)
    side_effect = record_side_effect_succeeded(
        config=config,
        lane=lane,
        key=effect_key,
        operation="tracker.set_issue_state_label",
        target=target_key,
        payload=payload,
        result={"changed": changed},
    )
    append_engine_event(
        config=config,
        lane=lane,
        event_type=f"{config.workflow_name}.lane.board_state_updated",
        payload={
            "target": target.value,
            "changed": changed,
            "add": mutation.add,
            "remove": mutation.remove,
        },
    )
    return {
        "status": "ok",
        "changed": changed,
        "target": target.value,
        "add": mutation.add,
        "remove": mutation.remove,
        "idempotency_key": effect_key,
        "side_effect": side_effect,
    }


def _apply_label_mutation(
    *, issue: dict[str, Any], add: list[str], remove: list[str]
) -> None:
    current = [label for label in issue.get("labels") or [] if str(label).strip()]
    remove_lower = {label.lower() for label in remove}
    labels = [
        label
        for label in current
        if str(label.get("name") if isinstance(label, dict) else label).strip().lower()
        not in remove_lower
    ]
    existing_lower = {
        str(label.get("name") if isinstance(label, dict) else label).strip().lower()
        for label in labels
    }
    for label in add:
        if label.lower() not in existing_lower:
            labels.append(label)
    issue["labels"] = labels


def _board_state_side_effect_key(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    issue_id: Any,
    target: BoardState,
    mutation: Any,
) -> str:
    return side_effect_key(
        config=config,
        lane=lane,
        operation="tracker.set_issue_state_label",
        target=_board_state_side_effect_target(issue_id=issue_id, target=target),
        payload={
            "target": target.value,
            "add": list(mutation.add or []),
            "remove": list(mutation.remove or []),
        },
    )


def _record_board_state_side_effect_skipped(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    issue_id: Any,
    target: BoardState,
    mutation: Any,
    reason: str,
) -> dict[str, Any]:
    key = _board_state_side_effect_key(
        config=config,
        lane=lane,
        issue_id=issue_id,
        target=target,
        mutation=mutation,
    )
    return record_side_effect_skipped(
        config=config,
        lane=lane,
        key=key,
        operation="tracker.set_issue_state_label",
        target=_board_state_side_effect_target(issue_id=issue_id, target=target),
        payload={
            "target": target.value,
            "add": list(mutation.add or []),
            "remove": list(mutation.remove or []),
        },
        reason=reason,
    )


def _board_state_side_effect_target(*, issue_id: Any, target: BoardState) -> str:
    return f"issue:{issue_id or 'missing'}:state:{target.value}"
