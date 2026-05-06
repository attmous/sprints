"""Prompt variable builders for actors and deterministic actions."""

from __future__ import annotations

from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.workflows.state_io import WorkflowState
from sprints.workflows.entry_lanes import lane_mapping
from sprints.workflows.prompt_context import (
    compact_lane_for_prompt,
    compact_value,
    compact_workflow_state,
    orchestrator_prompt_budget,
)
from sprints.workflows.surface_workpad import render_workpad

_PROMPT_INPUT_EXCLUDE_KEYS = {
    "audit",
    "audit_log",
    "audit_history",
    "dispatch_journal",
    "events",
    "history",
    "runtime_session",
    "runtime_sessions",
    "session_history",
    "sessions",
    "side_effects",
}


def actor_variables(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    lane: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    actor_outputs = lane_mapping(lane, "actor_outputs")
    budget = orchestrator_prompt_budget(config)
    lane_id = str(lane.get("lane_id") or "").strip()
    context = actor_prompt_context(
        config=config,
        lane=lane,
        inputs=inputs,
        budget=budget,
    )
    return {
        **_compact_actor_inputs(inputs=inputs, budget=budget),
        **context,
        "workflow": compact_workflow_state(
            state=state,
            ready_lane_ids={lane_id} if lane_id else set(),
            budget=budget,
        ),
        "lane": compact_lane_for_prompt(
            lane=lane,
            lane_id=lane_id,
            budget=budget,
            detailed=True,
        ),
        "config": config.raw,
        "issue": lane.get("issue") or {},
        "implementation": _compact_actor_output_alias(
            actor_outputs.get("implementer"), budget=budget
        ),
        "review": _compact_actor_output_alias(
            actor_outputs.get("reviewer"), budget=budget
        ),
        "review_feedback": compact_value(
            _review_feedback(lane=lane, inputs=inputs), budget=budget
        ),
        "pull_request": lane.get("pull_request") or {},
        "retry": _retry_context(lane=lane, inputs=inputs, budget=budget),
    }


def actor_dispatch_inputs(
    *,
    lane: dict[str, Any],
    actor_name: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Build durable actor dispatch inputs with explicit mode/context fields."""
    inputs = dict(inputs or {})
    return {
        **inputs,
        "mode": actor_mode(lane=lane, actor_name=actor_name, inputs=inputs),
        "board_state": _input_or_lane_value(
            inputs=inputs,
            lane=lane,
            key="board_state",
            fallback_keys=("board_state", "tracker.board_state"),
        ),
        "review_signals": _input_or_lane_mapping(
            inputs=inputs,
            lane=lane,
            key="review_signals",
            fallback_keys=("review_signals",),
        ),
        "workpad": _input_or_lane_mapping(
            inputs=inputs,
            lane=lane,
            key="workpad",
            fallback_keys=("workpad",),
        ),
        "merge_signal": _input_or_lane_mapping(
            inputs=inputs,
            lane=lane,
            key="merge_signal",
            fallback_keys=("merge_signal",),
        ),
    }


def actor_prompt_context(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    inputs: dict[str, Any],
    budget: Any | None = None,
) -> dict[str, Any]:
    """Compact explicit context keys actors can rely on in prompts."""
    inputs = dict(inputs or {})
    budget = budget or orchestrator_prompt_budget(config)
    return {
        "mode": actor_mode(lane=lane, actor_name=None, inputs=inputs),
        "attempt": int(inputs.get("attempt") or lane.get("attempt") or 1),
        "board_state": _input_or_lane_value(
            inputs=inputs,
            lane=lane,
            key="board_state",
            fallback_keys=("board_state", "tracker.board_state"),
        ),
        "review_signals": compact_value(
            _input_or_lane_mapping(
                inputs=inputs,
                lane=lane,
                key="review_signals",
                fallback_keys=("review_signals",),
            ),
            budget=budget,
        ),
        "workpad": compact_value(
            _workpad_context(lane=lane, inputs=inputs), budget=budget
        ),
        "merge_signal": compact_value(
            _input_or_lane_mapping(
                inputs=inputs,
                lane=lane,
                key="merge_signal",
                fallback_keys=("merge_signal",),
            ),
            budget=budget,
        ),
    }


def actor_mode(
    *,
    lane: dict[str, Any],
    actor_name: str | None,
    inputs: dict[str, Any],
) -> str:
    """Resolve actor mode from explicit inputs, then lane metadata."""
    inputs = dict(inputs or {})
    for value in (
        inputs.get("mode"),
        inputs.get("actor_mode"),
        lane.get("mode"),
        lane.get("actor_mode"),
    ):
        text = str(value or "").strip().lower()
        if text:
            return text
    stored_mode = _runtime_actor_mode(lane, actor_name=actor_name)
    if stored_mode:
        return stored_mode
    actor = str(actor_name or lane.get("actor") or "").strip().lower()
    if actor == "reviewer":
        return "review"
    if actor == "implementer":
        return "implement"
    return ""


def action_variables(
    *,
    config: WorkflowConfig,
    state: WorkflowState,
    lane: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    actor_outputs = lane_mapping(lane, "actor_outputs")
    budget = orchestrator_prompt_budget(config)
    lane_id = str(lane.get("lane_id") or "").strip()
    context = actor_prompt_context(
        config=config,
        lane=lane,
        inputs=inputs,
        budget=budget,
    )
    return {
        **inputs,
        **{key: value for key, value in context.items() if key not in inputs},
        "workflow": compact_workflow_state(
            state=state,
            ready_lane_ids={lane_id} if lane_id else set(),
            budget=budget,
        ),
        "lane": compact_lane_for_prompt(
            lane=lane,
            lane_id=lane_id,
            budget=budget,
            detailed=True,
        ),
        "workflow_root": str(config.workflow_root),
        "config": config.raw,
        "issue": lane.get("issue") or {},
        "actor_outputs": compact_value(actor_outputs, budget=budget),
        "stage_outputs": compact_value(
            lane_mapping(lane, "stage_outputs"), budget=budget
        ),
        "action_results": compact_value(
            lane_mapping(lane, "action_results"), budget=budget
        ),
        "implementation": _compact_actor_output_alias(
            actor_outputs.get("implementer"), budget=budget
        ),
        "review": _compact_actor_output_alias(
            actor_outputs.get("reviewer"), budget=budget
        ),
        "review_feedback": compact_value(
            _review_feedback(lane=lane, inputs=inputs), budget=budget
        ),
        "pull_request": lane.get("pull_request") or {},
        "retry": _retry_context(lane=lane, inputs=inputs, budget=budget),
    }


def _review_feedback(*, lane: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    actor_outputs = lane_mapping(lane, "actor_outputs")
    review = inputs.get("review")
    if not isinstance(review, dict):
        stored_review = actor_outputs.get("reviewer")
        review = stored_review if isinstance(stored_review, dict) else {}
    retry = inputs.get("retry") if isinstance(inputs.get("retry"), dict) else {}
    feedback = {
        "review": review,
        "required_fixes": inputs.get("required_fixes")
        or review.get("required_fixes")
        or retry.get("required_fixes"),
        "findings": inputs.get("findings")
        or review.get("findings")
        or retry.get("findings"),
        "verification_gaps": inputs.get("verification_gaps")
        or review.get("verification_gaps")
        or retry.get("verification_gaps"),
        "feedback": inputs.get("feedback") or retry.get("reason"),
    }
    return {
        key: value for key, value in feedback.items() if value not in (None, "", [], {})
    }


def _compact_actor_inputs(*, inputs: dict[str, Any], budget: Any) -> dict[str, Any]:
    return {
        str(key): compact_value(value, budget=budget)
        for key, value in dict(inputs or {}).items()
        if str(key).lower() not in _PROMPT_INPUT_EXCLUDE_KEYS
    }


def _compact_actor_output_alias(value: Any, *, budget: Any) -> dict[str, Any]:
    output = value if isinstance(value, dict) else {}
    keep = (
        "status",
        "summary",
        "branch",
        "branch_name",
        "pull_request",
        "pr",
        "files_changed",
        "commits",
        "verification",
        "findings",
        "required_fixes",
        "verification_gaps",
        "risks",
        "blockers",
        "artifacts",
        "thread_id",
        "turn_id",
    )
    return {
        key: compact_value(output.get(key), budget=budget)
        for key in keep
        if output.get(key) not in (None, "", [], {})
    }


def _retry_context(
    *, lane: dict[str, Any], inputs: dict[str, Any], budget: Any
) -> dict[str, Any]:
    retry = lane.get("pending_retry")
    if not isinstance(retry, dict):
        retry = inputs.get("retry") if isinstance(inputs.get("retry"), dict) else {}
    keep = (
        "status",
        "source",
        "stage",
        "target",
        "reason",
        "feedback",
        "attempt",
        "current_attempt",
        "max_attempts",
        "delay_seconds",
        "due_at",
        "queued_at",
        "required_fixes",
        "findings",
        "verification_gaps",
        "recovery",
    )
    return {
        key: compact_value(retry.get(key), budget=budget)
        for key in keep
        if retry.get(key) not in (None, "", [], {})
    }


def _workpad_context(*, lane: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    workpad = _input_or_lane_mapping(
        inputs=inputs,
        lane=lane,
        key="workpad",
        fallback_keys=("workpad",),
    )
    context = dict(workpad)
    context["content"] = str(context.get("content") or render_workpad(lane)).strip()
    return {
        key: value for key, value in context.items() if value not in (None, "", [], {})
    }


def _input_or_lane_mapping(
    *,
    inputs: dict[str, Any],
    lane: dict[str, Any],
    key: str,
    fallback_keys: tuple[str, ...],
) -> dict[str, Any]:
    value = inputs.get(key)
    if isinstance(value, dict):
        return value
    for fallback_key in fallback_keys:
        fallback = _lane_value(lane, fallback_key)
        if isinstance(fallback, dict):
            return fallback
    return {}


def _input_or_lane_value(
    *,
    inputs: dict[str, Any],
    lane: dict[str, Any],
    key: str,
    fallback_keys: tuple[str, ...],
) -> Any:
    value = inputs.get(key)
    if value not in (None, "", [], {}):
        return value
    for fallback_key in fallback_keys:
        fallback = _lane_value(lane, fallback_key)
        if fallback not in (None, "", [], {}):
            return fallback
    return None


def _lane_value(lane: dict[str, Any], key: str) -> Any:
    value: Any = lane
    for part in str(key).split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _runtime_actor_mode(lane: dict[str, Any], *, actor_name: str | None = None) -> str:
    actor = str(actor_name or "").strip().lower()
    session = (
        lane.get("runtime_session")
        if isinstance(lane.get("runtime_session"), dict)
        else {}
    )
    runtime = session.get("runtime") if isinstance(session.get("runtime"), dict) else {}
    dispatch = (
        lane.get("actor_dispatch")
        if isinstance(lane.get("actor_dispatch"), dict)
        else {}
    )
    dispatch_runtime = (
        dispatch.get("runtime") if isinstance(dispatch.get("runtime"), dict) else {}
    )
    for candidate, runtime_meta in (
        (session, runtime),
        (dispatch, dispatch_runtime),
    ):
        if actor and str(candidate.get("actor") or "").strip().lower() not in {
            "",
            actor,
        }:
            continue
        mode = (
            str(
                candidate.get("actor_mode")
                or candidate.get("mode")
                or runtime_meta.get("actor_mode")
                or runtime_meta.get("mode")
                or ""
            )
            .strip()
            .lower()
        )
        if mode:
            return mode
    return ""
