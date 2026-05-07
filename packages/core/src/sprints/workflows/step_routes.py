"""Deterministic step routes for the code workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.workflows.lane_state import issue_labels, lane_is_terminal
from sprints.workflows.runtime_sessions import active_actor_dispatch
from sprints.workflows.state_retries import lane_retry_is_due
from sprints.workflows.step_labels import (
    BLOCKED,
    CODE,
    DONE,
    MERGE,
    REVIEW,
    lane_step,
    step_from_labels,
)
from sprints.workflows.surface_pull_request import pull_request_url


@dataclass(frozen=True)
class StepRoute:
    action: str
    step: str
    target_step: str | None = None
    actor: str | None = None
    reason: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in asdict(self).items()
            if value not in (None, {}, [])
        }


def route_code_lane(*, config: WorkflowConfig, lane: dict[str, Any]) -> StepRoute:
    step = lane_step(config=config, lane=lane)
    lane_id = str(lane.get("lane_id") or "")
    if lane_is_terminal(lane):
        return StepRoute(action="hold", step=step, reason=f"{lane_id} is terminal")
    if active_actor_dispatch(lane):
        return StepRoute(
            action="hold", step=step, reason="actor dispatch already active"
        )
    status = str(lane.get("status") or "").strip().lower()
    if status == "running":
        return StepRoute(action="hold", step=step, reason="actor runtime is running")
    if status == "operator_attention":
        return StepRoute(
            action="hold", step=step, reason="operator attention required"
        )
    if status == "workpad_failed":
        return StepRoute(
            action="hold", step=step, reason="workpad repair must succeed first"
        )
    if status == "retry_queued" and not lane_retry_is_due(lane):
        return StepRoute(action="hold", step=step, reason="retry is not due yet")

    if step == CODE:
        return StepRoute(
            action="dispatch",
            step=CODE,
            actor="coder",
            reason="code step dispatch",
            inputs={"step": CODE},
        )
    if step == REVIEW:
        if review_has_required_changes(lane):
            return StepRoute(
                action="move_step",
                step=REVIEW,
                target_step=CODE,
                reason="review feedback requires code changes",
                inputs={"step": CODE},
            )
        return StepRoute(action="hold", step=REVIEW, reason="waiting for review signal")
    if step == MERGE:
        return StepRoute(
            action="dispatch",
            step=MERGE,
            actor="coder",
            reason="merge step dispatch",
            inputs={"step": MERGE},
        )
    if step == DONE:
        if done_release_verified(lane):
            return StepRoute(action="release", step=DONE, reason="done verified")
        if done_label_with_merged_pr(lane):
            return StepRoute(
                action="move_step",
                step=DONE,
                target_step=MERGE,
                reason="done label present but source issue is still open",
                inputs={"step": MERGE},
            )
        return StepRoute(
            action="hold",
            step=DONE,
            reason="done label present but completion is not verified",
        )
    if step == BLOCKED:
        return StepRoute(action="hold", step=BLOCKED, reason="blocked step")
    if pull_request_url(lane):
        return StepRoute(
            action="move_step",
            step=step,
            target_step=REVIEW,
            reason="pull request exists",
        )
    return StepRoute(action="hold", step=step, reason="lane has no code workflow step")


def next_step_after_actor_output(
    *, lane: dict[str, Any], output: dict[str, Any]
) -> str | None:
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    current_step = (
        str(lane.get("step") or "").strip().lower()
        or step_from_labels(issue.get("labels") or [])
    )
    step = str(output.get("step") or current_step).strip().lower()
    status = str(output.get("status") or "").strip().lower()
    if step == CODE and status == "done":
        return REVIEW
    if step == MERGE and status == "done":
        return DONE
    return None


def review_has_required_changes(lane: dict[str, Any]) -> bool:
    signals = lane.get("review_signals")
    if isinstance(signals, dict) and signals.get("required_changes"):
        return True
    output = lane.get("last_actor_output")
    if not isinstance(output, dict):
        return False
    feedback = output.get("review_feedback")
    if isinstance(feedback, list) and feedback:
        return True
    if isinstance(feedback, dict) and feedback.get("required_fixes"):
        return True
    return False


def done_release_verified(lane: dict[str, Any]) -> bool:
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    if DONE not in issue_labels(issue):
        return False
    if not issue_is_closed(lane):
        return False
    return pull_request_is_merged(lane)


def done_label_with_merged_pr(lane: dict[str, Any]) -> bool:
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    return DONE in issue_labels(issue) and pull_request_is_merged(lane)


def issue_is_closed(lane: dict[str, Any]) -> bool:
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    output = lane.get("last_actor_output")
    output_issue_state = (
        _issue_state_from_actor_output(output) if isinstance(output, dict) else ""
    )
    issue_state = str(issue.get("state") or "").strip().lower()
    return issue_state in {"closed", "done"} or output_issue_state in {"closed", "done"}


def pull_request_is_merged(lane: dict[str, Any]) -> bool:
    pull_request = (
        lane.get("pull_request") if isinstance(lane.get("pull_request"), dict) else {}
    )
    state = str(pull_request.get("state") or "").strip().lower()
    return bool(pull_request.get("merged")) or state == "merged"


def _issue_state_from_actor_output(output: dict[str, Any]) -> str:
    cleanup = output.get("cleanup") if isinstance(output.get("cleanup"), dict) else {}
    artifacts = output.get("artifacts") if isinstance(output.get("artifacts"), dict) else {}
    issue = output.get("issue") if isinstance(output.get("issue"), dict) else {}
    return str(
        cleanup.get("issue_state")
        or cleanup.get("issue-state")
        or artifacts.get("issue_state")
        or artifacts.get("issue-state")
        or issue.get("state")
        or ""
    ).strip().lower()

