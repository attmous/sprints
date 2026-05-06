"""Actor-driven route selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.workflows.surface_board_state import BoardState, state_from_labels
from sprints.workflows.lane_completion import done_release_verified
from sprints.workflows.lane_state import (
    active_lanes,
    completion_cleanup_retry_pending,
    lane_is_terminal,
)
from sprints.workflows.state_retries import lane_retry_is_due
from sprints.workflows.surface_review_state import (
    review_actor_enabled,
    review_has_required_changes,
    review_required_changes,
    reviewer_actor_running,
)
from sprints.workflows.runtime_sessions import active_actor_dispatch
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
    rule = _select_route_rule(config=config, lane=lane, board_state=board_state)
    if rule is not None:
        return _route_from_rule(
            rule=rule,
            lane_id=lane_id,
            board_state=board_state,
            lane=lane,
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


def _select_route_rule(
    *, config: WorkflowConfig, lane: dict[str, Any], board_state: str
) -> dict[str, Any] | None:
    context = _route_context(config=config, lane=lane, board_state=board_state)
    for rule in _route_rules(config):
        if _rule_matches(rule, context):
            return rule
    return None


def _route_rules(config: WorkflowConfig) -> list[dict[str, Any]]:
    routing = config.raw.get("routing") if isinstance(config.raw, dict) else {}
    actor_driven = (
        routing.get("actor-driven")
        if isinstance(routing, dict)
        else None
    )
    rules = actor_driven.get("rules") if isinstance(actor_driven, dict) else []
    return [rule for rule in rules or [] if isinstance(rule, dict)]


def _route_context(
    *, config: WorkflowConfig, lane: dict[str, Any], board_state: str
) -> dict[str, Any]:
    return {
        "board_state": board_state,
        "lane_status": str(lane.get("status") or "").strip().lower(),
        "last_actor_mode": _last_actor_mode(lane),
        "completion_verified": done_release_verified(lane),
        "review_required_changes": review_has_required_changes(lane),
        "reviewer_running": reviewer_actor_running(lane),
        "review_actor_available": (
            "reviewer" in config.actors and review_actor_enabled(config)
        ),
    }


def _rule_matches(rule: dict[str, Any], context: dict[str, Any]) -> bool:
    when = rule.get("when") if isinstance(rule.get("when"), dict) else {}
    if not when:
        return False
    for key, expected in when.items():
        if not _condition_matches(context.get(str(key)), expected):
            return False
    return True


def _condition_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_condition_matches(actual, item) for item in expected)
    if isinstance(expected, bool):
        return bool(actual) is expected
    return str(actual or "").strip().lower() == str(expected or "").strip().lower()


def _route_from_rule(
    *,
    rule: dict[str, Any],
    lane_id: str,
    board_state: str,
    lane: dict[str, Any],
) -> ActorRoute:
    raw_route = rule.get("route") if isinstance(rule.get("route"), dict) else {}
    action = str(raw_route.get("action") or "hold").strip() or "hold"
    mode = _optional_text(raw_route.get("mode"))
    inputs = _resolve_route_inputs(raw_route.get("inputs"), lane=lane)
    if mode:
        inputs.setdefault("mode", mode)
    return ActorRoute(
        lane_id=lane_id,
        board_state=board_state,
        action=action,
        stage=_optional_text(raw_route.get("stage")),
        actor=_optional_text(raw_route.get("actor")),
        mode=mode,
        target_board_state=_optional_text(raw_route.get("target_board_state")),
        reason=str(raw_route.get("reason") or rule.get("name") or "").strip(),
        inputs=inputs or None,
    )


def _resolve_route_inputs(value: Any, *, lane: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): _resolve_route_input_value(raw, lane=lane)
        for key, raw in value.items()
    }


def _resolve_route_input_value(value: Any, *, lane: dict[str, Any]) -> Any:
    if value == "$review.required_changes":
        return review_required_changes(lane)
    return value


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


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
