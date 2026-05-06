"""Actor output recording and contract interpretation."""

from __future__ import annotations

from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.workflows.lane_state import (
    append_engine_event,
    blocker_reason,
    clear_engine_retry,
    first_text,
    lane_list,
    lane_mapping,
    lane_stage,
    normalize_pull_request,
    now_iso,
    release_lane_lease,
    set_lane_operator_attention,
    set_lane_status,
)
from sprints.workflows.surface_notifications import notify_review_changes_requested
from sprints.workflows.surface_pull_request import pull_request_url
from sprints.workflows.state_retries import RetryRequest, queue_lane_retry


def record_actor_output(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    actor_name: str,
    output: dict[str, Any],
) -> None:
    actor_outputs = lane_mapping(lane, "actor_outputs")
    if actor_name == "implementer":
        _clear_superseded_reviewer_changes(lane=lane, output=output)
    actor_outputs[actor_name] = output
    lane["last_actor_output"] = output
    lane["last_progress_at"] = now_iso()
    lane["pending_retry"] = None
    clear_engine_retry(config=config, lane=lane)
    stage_outputs = lane_mapping(lane, "stage_outputs")
    stage_outputs[lane_stage(lane)] = {
        **dict(stage_outputs.get(lane_stage(lane)) or {}),
        "last_actor": actor_name,
    }
    branch = first_text(output, "branch", "branch_name", "branch-name")
    if branch:
        lane["branch"] = branch
    pull_request = output.get("pull_request") or output.get("pr")
    if isinstance(pull_request, dict):
        lane["pull_request"] = normalize_pull_request(pull_request)
    elif pull_request:
        lane["pull_request"] = {"url": str(pull_request)}
    thread_id = first_text(output, "thread_id", "thread-id")
    if thread_id:
        lane["thread_id"] = thread_id
    turn_id = first_text(output, "turn_id", "turn-id")
    if turn_id:
        lane["turn_id"] = turn_id
    append_engine_event(
        config=config,
        lane=lane,
        event_type=f"{config.workflow_name}.lane.actor_output",
        payload={"actor": actor_name, "output": output},
    )


def apply_actor_output_status(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    actor_name: str,
    output: dict[str, Any],
) -> None:
    status = str(output.get("status") or "").strip().lower()
    blockers = (
        output.get("blockers") if isinstance(output.get("blockers"), list) else []
    )
    if not status:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_output_contract_failed",
            message=f"{actor_name} output is missing status",
            artifacts={"actor": actor_name, "output": output},
        )
        return
    if actor_name == "implementer":
        mode = _actor_output_mode(output)
        if mode == "land" or status in {"merged", "waiting"}:
            _apply_land_output_status(
                config=config,
                lane=lane,
                actor_name=actor_name,
                output=output,
                status=status,
                blockers=blockers,
            )
            return
        if status not in {"done", "blocked", "failed"}:
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message=f"implementer returned unsupported status {status!r}",
                artifacts={"actor": actor_name, "output": output},
            )
            return
        if status == "done":
            failure = delivery_contract_failure(lane)
            if failure:
                set_lane_operator_attention(
                    config=config,
                    lane=lane,
                    reason="actor_output_contract_failed",
                    message=failure,
                    artifacts=contract_artifacts(lane),
                )
                return
    if actor_name == "reviewer" and status not in {
        "approved",
        "blocked",
        "failed",
        "changes_requested",
        "needs_changes",
    }:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_output_contract_failed",
            message=f"reviewer returned unsupported status {status!r}",
            artifacts={"actor": actor_name, "output": output},
        )
        return
    if actor_name == "reviewer" and status in {"changes_requested", "needs_changes"}:
        required_fixes = output.get("required_fixes")
        if not isinstance(required_fixes, list) or not required_fixes:
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message="review changes require non-empty required_fixes",
                artifacts={"actor": actor_name, "output": output},
            )
            return
        notify_review_changes_requested(config=config, lane=lane, output=output)
    if actor_name not in {"implementer", "reviewer"} and status in {
        "merged",
        "done",
        "complete",
        "completed",
    }:
        release_lane_lease(
            config=config,
            lane=lane,
            reason=str(output.get("summary") or f"{actor_name} completed lane"),
        )
        set_lane_status(
            config=config,
            lane=lane,
            status="complete",
            actor=None,
            reason=f"{actor_name} completed lane",
        )
        return
    if status in {"blocked", "failed"} or blockers:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason=blocker_reason(output) or status or "actor_blocked",
            message=str(
                output.get("summary") or f"{actor_name} returned {status or 'blockers'}"
            ),
            artifacts={
                "actor": actor_name,
                "blockers": blockers,
                "branch": lane.get("branch"),
                "pull_request": lane.get("pull_request"),
                "artifacts": output.get("artifacts")
                if isinstance(output.get("artifacts"), dict)
                else {},
            },
        )
        return
    set_lane_status(
        config=config,
        lane=lane,
        status="waiting",
        actor=None,
        reason=f"{actor_name} returned output",
    )


def delivery_contract_failure(lane: dict[str, Any]) -> str:
    implementation = lane_mapping(lane, "actor_outputs").get("implementer")
    if not isinstance(implementation, dict):
        return "delivery cannot advance before implementer output exists"
    if str(implementation.get("status") or "").strip().lower() != "done":
        return "delivery requires implementer status `done`"
    if not pull_request_url(lane):
        return "delivery requires pull_request.url"
    verification = implementation.get("verification")
    if not isinstance(verification, list) or not verification:
        return "delivery requires non-empty verification evidence"
    return ""


def contract_artifacts(lane: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": lane.get("stage"),
        "actor_outputs": lane.get("actor_outputs"),
        "pull_request": lane.get("pull_request"),
        "branch": lane.get("branch"),
        "completion_auto_merge": lane.get("completion_auto_merge"),
    }


def _apply_land_output_status(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    actor_name: str,
    output: dict[str, Any],
    status: str,
    blockers: list[Any],
) -> None:
    if status not in {"merged", "waiting", "blocked", "failed"}:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_output_contract_failed",
            message=f"land mode returned unsupported status {status!r}",
            artifacts={"actor": actor_name, "output": output},
        )
        return
    if status == "merged":
        failure = _land_contract_failure(output)
        if failure:
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message=failure,
                artifacts=contract_artifacts(lane),
            )
            return
    if status == "waiting":
        queue_lane_retry(
            config=config,
            lane=lane,
            request=RetryRequest(
                stage=lane_stage(lane),
                lane_id=str(lane.get("lane_id") or ""),
                target=actor_name,
                reason=str(output.get("summary") or "land mode waiting"),
                inputs={
                    "mode": "land",
                    "landing": output,
                },
            ),
        )
        return
    if status in {"blocked", "failed"} or blockers:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason=blocker_reason(output) or status or "actor_blocked",
            message=str(
                output.get("summary") or f"{actor_name} returned {status or 'blockers'}"
            ),
            artifacts={
                "actor": actor_name,
                "blockers": blockers,
                "branch": lane.get("branch"),
                "pull_request": lane.get("pull_request"),
                "artifacts": output.get("artifacts")
                if isinstance(output.get("artifacts"), dict)
                else {},
            },
        )
        return
    set_lane_status(
        config=config,
        lane=lane,
        status="waiting",
        actor=None,
        reason="land mode returned output",
    )


def _clear_superseded_reviewer_changes(
    *, lane: dict[str, Any], output: dict[str, Any]
) -> None:
    if str(output.get("status") or "").strip().lower() != "done":
        return
    actor_outputs = lane_mapping(lane, "actor_outputs")
    review = actor_outputs.get("reviewer")
    if not isinstance(review, dict):
        return
    if str(review.get("status") or "").strip().lower() not in {
        "changes_requested",
        "needs_changes",
    }:
        return
    superseded = lane_list(lane, "superseded_actor_outputs")
    superseded.append(
        {
            "actor": "reviewer",
            "stage": "review",
            "superseded_by": "implementer",
            "superseded_at": now_iso(),
            "output": review,
        }
    )
    actor_outputs.pop("reviewer", None)


def _actor_output_mode(output: dict[str, Any]) -> str:
    return str(output.get("mode") or "").strip().lower()


def _land_contract_failure(output: dict[str, Any]) -> str:
    pull_request = output.get("pull_request")
    if not isinstance(pull_request, dict):
        return "land output requires pull_request object"
    state = str(pull_request.get("state") or "").strip().lower()
    if not pull_request.get("merged") and state != "merged":
        return "land output requires merged pull request evidence"
    cleanup = output.get("cleanup")
    if not isinstance(cleanup, dict):
        return "land output requires cleanup evidence"
    added = {
        str(label).strip().lower()
        for label in cleanup.get("added_labels") or []
        if str(label).strip()
    }
    if "done" not in added:
        return "land output requires done label cleanup evidence"
    return ""
