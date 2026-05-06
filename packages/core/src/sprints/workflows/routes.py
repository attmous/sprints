"""Actor-driven route selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.workflows.board_state import BoardState, state_from_labels
from sprints.workflows.completion import done_release_verified
from sprints.workflows.lane_state import (
    active_lanes,
    completion_cleanup_retry_pending,
    lane_is_terminal,
)
from sprints.workflows.retries import lane_retry_is_due
from sprints.workflows.review_state import (
    review_actor_enabled,
    review_has_required_changes,
    review_required_changes,
    reviewer_actor_running,
)
from sprints.workflows.sessions import active_actor_dispatch
from sprints.workflows.state_io import WorkflowState


@dataclass(frozen=True)
class ActorRoute:
    lane_id: str
    board_state: str
    action: str
    stage: str | None = None
    actor: str | None = None
    mode: str | None = None
    target_board_state: str | None = None
    reason: str = ""
    inputs: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def actor_driven_ready_lanes(
    *, config: WorkflowConfig, state: WorkflowState
) -> list[dict[str, Any]]:
    return [
        lane
        for lane in active_lanes(state)
        if lane_needs_actor_driven_route(config=config, lane=lane)
    ]


def lane_needs_actor_driven_route(
    *, config: WorkflowConfig, lane: dict[str, Any]
) -> bool:
    route = route_lane(config=config, lane=lane)
    return route.action in {"dispatch", "release", "wait_review", "move_board"}


def route_lane(*, config: WorkflowConfig, lane: dict[str, Any]) -> ActorRoute:
    lane_id = str(lane.get("lane_id") or "")
    board_state = lane_board_state(config=config, lane=lane) or ""
    if lane_is_terminal(lane):
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="lane is terminal",
        )
    if active_actor_dispatch(lane):
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="actor dispatch already active",
        )
    lane_status = str(lane.get("status") or "").strip().lower()
    if lane_status == "running":
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="actor runtime is running",
        )
    if lane_status == "operator_attention":
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="operator attention required",
        )
    if lane_status == "workpad_failed":
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="workpad repair must succeed first",
        )
    if lane_status == "retry_queued" and not lane_retry_is_due(lane):
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="hold",
            reason="retry is not due yet",
        )
    if lane_status == "retry_queued":
        if completion_cleanup_retry_pending(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                reason="completion cleanup retry is runner-owned",
            )
        retry_route = _due_retry_route(lane=lane, board_state=board_state)
        if retry_route is not None:
            return retry_route
    if board_state == BoardState.BACKLOG.value:
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="release",
            reason="board state is backlog",
        )
    if board_state == BoardState.DONE.value:
        if not done_release_verified(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                reason="done label is present but completion is not verified",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="release",
            reason="board state is done",
        )
    if board_state == BoardState.TODO.value:
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="deliver",
            actor="implementer",
            mode="implement",
            reason="todo lane enters implementation",
            inputs={"mode": "implement"},
        )
    if board_state == BoardState.IN_PROGRESS.value:
        if _last_actor_mode(lane) == "implement" and lane_status in {
            "waiting",
            "review_waiting",
        }:
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="move_board",
                stage="review",
                target_board_state=BoardState.REVIEW.value,
                reason="implementation output is ready for review",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="deliver",
            actor="implementer",
            mode="implement",
            reason="in-progress lane needs implementation",
            inputs={"mode": "implement"},
        )
    if board_state == BoardState.REVIEW.value:
        if review_has_required_changes(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="move_board",
                stage="deliver",
                target_board_state=BoardState.REWORK.value,
                reason="review signals require rework",
                inputs={"required_fixes": review_required_changes(lane)},
            )
        if reviewer_actor_running(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                stage="review",
                reason="reviewer actor is still running",
            )
        if _last_actor_mode(lane) == "review" and lane_status in {
            "waiting",
            "review_waiting",
        }:
            if lane_status == "review_waiting":
                return ActorRoute(
                    lane_id=lane_id,
                    board_state=board_state,
                    action="hold",
                    stage="review",
                    reason="waiting for human merge signal",
                )
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="wait_review",
                stage="review",
                reason="review actor result is waiting for human merge signal",
            )
        if "reviewer" not in config.actors or not review_actor_enabled(config):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold" if lane_status == "review_waiting" else "wait_review",
                stage="review",
                reason="no reviewer actor configured; waiting for human review",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="review",
            actor="reviewer",
            mode="review",
            reason="review lane needs shared AI review",
            inputs={"mode": "review"},
        )
    if board_state == BoardState.REWORK.value:
        if _last_actor_mode(lane) == "rework" and lane_status in {
            "waiting",
            "review_waiting",
        }:
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="move_board",
                stage="review",
                target_board_state=BoardState.REVIEW.value,
                reason="rework output is ready for review",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="deliver",
            actor="implementer",
            mode="rework",
            reason="rework lane needs implementer fixes",
            inputs={"mode": "rework"},
        )
    if board_state == BoardState.MERGING.value:
        if review_has_required_changes(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="move_board",
                stage="deliver",
                target_board_state=BoardState.REWORK.value,
                reason="required changes take priority over merge signal",
                inputs={"required_fixes": review_required_changes(lane)},
            )
        if reviewer_actor_running(lane):
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                stage="review",
                reason="merge signal is waiting for reviewer actor to finish",
            )
        if _last_actor_mode(lane) == "land" and lane_status in {
            "waiting",
            "review_waiting",
        }:
            return ActorRoute(
                lane_id=lane_id,
                board_state=board_state,
                action="hold",
                reason="land output is waiting for merge reconciliation",
            )
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="dispatch",
            stage="deliver",
            actor="implementer",
            mode="land",
            reason="merge authority seen; implementer should run land skill",
            inputs={"mode": "land"},
        )
    return ActorRoute(
        lane_id=lane_id,
        board_state=board_state,
        action="hold",
        reason="lane has no routable board state",
    )


def lane_board_state(*, config: WorkflowConfig, lane: dict[str, Any]) -> str | None:
    tracker = lane.get("tracker") if isinstance(lane.get("tracker"), dict) else {}
    board_state = str(
        tracker.get("board_state") or lane.get("board_state") or ""
    ).strip()
    if board_state:
        return board_state
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    return state_from_labels(issue.get("labels") or [], config)


def _due_retry_route(*, lane: dict[str, Any], board_state: str) -> ActorRoute | None:
    pending = (
        lane.get("pending_retry") if isinstance(lane.get("pending_retry"), dict) else {}
    )
    inputs = pending.get("inputs") if isinstance(pending.get("inputs"), dict) else {}
    lane_id = str(lane.get("lane_id") or "")
    board_target = str(inputs.get("board_state_target") or "").strip()
    if board_target:
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="move_board",
            stage=str(pending.get("stage") or lane.get("stage") or "") or None,
            actor=str(pending.get("target") or "") or None,
            mode=str(inputs.get("mode") or "") or None,
            target_board_state=board_target,
            reason=str(pending.get("reason") or "retry board state update"),
            inputs=dict(inputs),
        )
    stage = str(pending.get("stage") or lane.get("stage") or "").strip()
    target = str(pending.get("target") or "").strip()
    if not stage or not target:
        return ActorRoute(
            lane_id=lane_id,
            board_state=board_state,
            action="operator_attention",
            reason="due retry is missing stage or target",
            inputs=dict(inputs),
        )
    return ActorRoute(
        lane_id=lane_id,
        board_state=board_state,
        action="dispatch",
        stage=stage,
        actor=target,
        mode=_retry_actor_mode(
            actor=target,
            board_state=board_state,
            lane=lane,
            inputs=inputs,
        ),
        reason=str(pending.get("reason") or "dispatch due retry"),
        inputs=dict(inputs),
    )


def _retry_actor_mode(
    *, actor: str, board_state: str, lane: dict[str, Any], inputs: dict[str, Any]
) -> str | None:
    mode = str(inputs.get("mode") or "").strip().lower()
    if mode:
        return mode
    actor_name = str(actor or "").strip().lower()
    if actor_name == "reviewer":
        return "review"
    if actor_name == "implementer":
        if board_state == BoardState.REWORK.value:
            return "rework"
        if board_state == BoardState.MERGING.value:
            return "land"
        last_mode = _last_actor_mode(lane)
        if last_mode in {"implement", "rework", "land"}:
            return last_mode
        return "implement"
    return None


def _last_actor_mode(lane: dict[str, Any]) -> str:
    dispatch = (
        lane.get("actor_dispatch")
        if isinstance(lane.get("actor_dispatch"), dict)
        else {}
    )
    runtime = (
        dispatch.get("runtime") if isinstance(dispatch.get("runtime"), dict) else {}
    )
    return str(runtime.get("actor_mode") or runtime.get("mode") or "").strip().lower()
