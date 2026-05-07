"""Actor output recording and contract interpretation."""

from __future__ import annotations

from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.workflows.lane_state import (
    append_engine_event,
    blocker_reason,
    clear_engine_retry,
    first_text,
    lane_mapping,
    lane_stage,
    normalize_pull_request,
    now_iso,
    set_lane_operator_attention,
    set_lane_status,
)
from sprints.workflows.surface_pull_request import pull_request_url


def record_actor_output(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    actor_name: str,
    output: dict[str, Any],
) -> None:
    actor_outputs = lane_mapping(lane, "actor_outputs")
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
    if actor_name == "coder":
        _apply_coder_output_status(
            config=config,
            lane=lane,
            actor_name=actor_name,
            output=output,
            status=status,
            blockers=blockers,
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


def contract_artifacts(lane: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": lane.get("stage"),
        "actor_outputs": lane.get("actor_outputs"),
        "pull_request": lane.get("pull_request"),
        "branch": lane.get("branch"),
        "completion_auto_merge": lane.get("completion_auto_merge"),
    }


def _apply_coder_output_status(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    actor_name: str,
    output: dict[str, Any],
    status: str,
    blockers: list[Any],
) -> None:
    step = str(output.get("step") or lane.get("step") or "").strip().lower()
    if status not in {"done", "waiting", "blocked", "failed"}:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason="actor_output_contract_failed",
            message=f"coder returned unsupported status {status!r}",
            artifacts={"actor": actor_name, "output": output},
        )
        return
    if status in {"blocked", "failed"} or blockers:
        set_lane_operator_attention(
            config=config,
            lane=lane,
            reason=blocker_reason(output) or status or "actor_blocked",
            message=str(output.get("summary") or f"{actor_name} returned {status}"),
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
    if step == "code" and status == "done":
        if not pull_request_url(lane):
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message="code step requires pull_request.url before review",
                artifacts=contract_artifacts(lane),
            )
            return
        verification = output.get("verification")
        if not isinstance(verification, list) or not verification:
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message="code step requires non-empty verification evidence",
                artifacts=contract_artifacts(lane),
            )
            return
    if step == "merge" and status == "done":
        pull_request = output.get("pull_request")
        if not isinstance(pull_request, dict) or not pull_request.get("merged"):
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message="merge step requires merged pull request evidence",
                artifacts=contract_artifacts(lane),
            )
            return
        if _issue_state_from_output(output) != "closed":
            set_lane_operator_attention(
                config=config,
                lane=lane,
                reason="actor_output_contract_failed",
                message="merge step requires explicit closed issue evidence",
                artifacts={
                    **contract_artifacts(lane),
                    "actor_output": output,
                    "issue_state": _issue_state_from_output(output) or "missing",
                },
            )
            return
    set_lane_status(
        config=config,
        lane=lane,
        status="waiting",
        actor=None,
        reason=f"{actor_name} returned {status} for step {step}",
    )


def _issue_state_from_output(output: dict[str, Any]) -> str:
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
