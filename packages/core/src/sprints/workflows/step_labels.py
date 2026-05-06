"""Canonical step labels for the code workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.trackers import build_tracker_client
from sprints.workflows.lane_state import (
    append_engine_event,
    issue_labels,
    repository_path,
    tracker_config,
)
from sprints.workflows.state_effects import (
    completed_side_effect,
    record_side_effect_failed,
    record_side_effect_skipped,
    record_side_effect_started,
    record_side_effect_succeeded,
    side_effect_key,
)

TODO = "todo"
CODE = "code"
REVIEW = "review"
MERGE = "merge"
DONE = "done"
BLOCKED = "blocked"

ACTIVE_STEPS = (CODE, REVIEW, MERGE, BLOCKED)
ALL_STEP_LABELS = (TODO, CODE, REVIEW, MERGE, DONE, BLOCKED)


@dataclass(frozen=True)
class StepLabelPlan:
    remove_labels: tuple[str, ...]
    add_labels: tuple[str, ...]

    def changed(self) -> bool:
        return bool(self.remove_labels or self.add_labels)


def lane_step(*, config: WorkflowConfig, lane: dict[str, Any]) -> str:
    del config
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    issue_step = step_from_labels(issue.get("labels") or [])
    if issue_step:
        return issue_step
    tracker = lane.get("tracker") if isinstance(lane.get("tracker"), dict) else {}
    step = str(tracker.get("step") or lane.get("step") or "").strip().lower()
    return step


def step_from_labels(labels: Any) -> str:
    normalized = issue_labels({"labels": labels})
    for step in (DONE, BLOCKED, MERGE, REVIEW, CODE, TODO):
        if step in normalized:
            return step
    return ""


def active_step_labels(labels: Any) -> set[str]:
    normalized = issue_labels({"labels": labels})
    return {label for label in ALL_STEP_LABELS if label in normalized}


def label_plan_for_step(*, current_labels: Any, target_step: str) -> StepLabelPlan:
    target = _normalize_step(target_step)
    existing = active_step_labels(current_labels)
    remove = tuple(
        label for label in ALL_STEP_LABELS if label in existing and label != target
    )
    add = () if target in existing else (target,)
    return StepLabelPlan(remove_labels=remove, add_labels=add)


def set_lane_step_label(
    *, config: WorkflowConfig, lane: dict[str, Any], target_step: str
) -> dict[str, Any]:
    target = _normalize_step(target_step)
    tracker_cfg = tracker_config(config)
    if not tracker_cfg:
        return {"status": "skipped", "reason": "no tracker config"}
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    issue_id = issue.get("id")
    plan = label_plan_for_step(
        current_labels=issue.get("labels") or [], target_step=target
    )
    payload = {
        "target_step": target,
        "add": list(plan.add_labels),
        "remove": list(plan.remove_labels),
    }
    key = side_effect_key(
        config=config,
        lane=lane,
        operation="tracker.set_issue_step_label",
        target=f"issue:{issue_id or 'missing'}:step:{target}",
        payload=payload,
    )
    if not plan.changed():
        skipped = record_side_effect_skipped(
            config=config,
            lane=lane,
            key=key,
            operation="tracker.set_issue_step_label",
            target=f"issue:{issue_id or 'missing'}:step:{target}",
            payload=payload,
            reason="step labels already match target",
        )
        _record_lane_step(config=config, lane=lane, step=target)
        return {
            "status": "ok",
            "changed": False,
            "target_step": target,
            "side_effect": skipped,
        }
    completed = completed_side_effect(config=config, lane=lane, key=key)
    if completed:
        _apply_label_mutation(
            issue=issue, add=list(plan.add_labels), remove=list(plan.remove_labels)
        )
        _record_lane_step(config=config, lane=lane, step=target)
        return {
            "status": "ok",
            "changed": False,
            "target_step": target,
            "idempotency_key": key,
            "side_effect": completed,
            "reason": "step label side effect already completed",
        }
    record_side_effect_started(
        config=config,
        lane=lane,
        key=key,
        operation="tracker.set_issue_step_label",
        target=f"issue:{issue_id or 'missing'}:step:{target}",
        payload=payload,
    )
    try:
        client = build_tracker_client(
            workflow_root=config.workflow_root,
            tracker_cfg=tracker_cfg,
            repo_path=repository_path(config),
        )
        changed = client.set_issue_state_label(
            issue_id,
            add=plan.add_labels,
            remove=plan.remove_labels,
        )
    except Exception as exc:
        record_side_effect_failed(
            config=config,
            lane=lane,
            key=key,
            operation="tracker.set_issue_step_label",
            target=f"issue:{issue_id or 'missing'}:step:{target}",
            payload=payload,
            error=str(exc),
        )
        append_engine_event(
            config=config,
            lane=lane,
            event_type=f"{config.workflow_name}.lane.step_label_failed",
            payload={**payload, "error": str(exc)},
            severity="warning",
        )
        return {"status": "failed", "target_step": target, "error": str(exc)}
    if not changed:
        record_side_effect_failed(
            config=config,
            lane=lane,
            key=key,
            operation="tracker.set_issue_step_label",
            target=f"issue:{issue_id or 'missing'}:step:{target}",
            payload=payload,
            error="tracker did not apply requested step label mutation",
        )
        return {
            "status": "failed",
            "target_step": target,
            "error": "tracker did not apply requested step label mutation",
        }
    _apply_label_mutation(
        issue=issue, add=list(plan.add_labels), remove=list(plan.remove_labels)
    )
    _record_lane_step(config=config, lane=lane, step=target)
    side_effect = record_side_effect_succeeded(
        config=config,
        lane=lane,
        key=key,
        operation="tracker.set_issue_step_label",
        target=f"issue:{issue_id or 'missing'}:step:{target}",
        payload=payload,
        result={"changed": changed},
    )
    append_engine_event(
        config=config,
        lane=lane,
        event_type=f"{config.workflow_name}.lane.step_label_updated",
        payload={**payload, "changed": changed},
    )
    return {
        "status": "ok",
        "changed": changed,
        "target_step": target,
        "add": list(plan.add_labels),
        "remove": list(plan.remove_labels),
        "idempotency_key": key,
        "side_effect": side_effect,
    }


def _normalize_step(value: str) -> str:
    step = str(value or "").strip().lower()
    if step not in ALL_STEP_LABELS:
        raise ValueError(f"unknown code workflow step: {value!r}")
    return step


def _record_lane_step(*, config: WorkflowConfig, lane: dict[str, Any], step: str) -> None:
    del config
    lane["step"] = step
    tracker = lane.setdefault("tracker", {})
    if isinstance(tracker, dict):
        tracker["step"] = step


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
