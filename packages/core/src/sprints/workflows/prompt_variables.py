"""Prompt variable builders for actor turns."""

from __future__ import annotations

from typing import Any

from sprints.core.config import WorkflowConfig
from sprints.workflows.state_io import WorkflowState
from sprints.workflows.prompt_context import (
    compact_lane_for_prompt,
    compact_value,
    compact_workflow_state,
    prompt_budget,
)
from sprints.workflows.step_labels import lane_step
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
    budget = prompt_budget(config)
    lane_id = str(lane.get("lane_id") or "").strip()
    step_context = actor_step(config=config, lane=lane, inputs=inputs)
    context = actor_prompt_context(
        config=config,
        lane=lane,
        inputs=inputs,
        budget=budget,
    )
    return {
        **_compact_actor_inputs(inputs=inputs, budget=budget),
        **context,
        "step": step_context,
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
        "workspace": _workspace_context(config=config, lane=lane),
        "repository": config.raw.get("repository") or {},
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
    """Build durable actor dispatch inputs with explicit step/context fields."""
    inputs = dict(inputs or {})
    step = str(
        inputs.get("step") or inputs.get("mode") or lane.get("step") or ""
    ).strip()
    return {
        **inputs,
        "step": step,
        "mode": step,
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
    budget = budget or prompt_budget(config)
    step = actor_step(config=config, lane=lane, inputs=inputs)
    return {
        "step": step,
        "mode": step,
        "attempt": int(inputs.get("attempt") or lane.get("attempt") or 1),
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


def _workspace_context(*, config: WorkflowConfig, lane: dict[str, Any]) -> dict[str, Any]:
    return {
        "root": (config.raw.get("workspace") or {}).get("root")
        if isinstance(config.raw.get("workspace"), dict)
        else None,
        "worktree": lane.get("worktree"),
        "branch": lane.get("branch"),
        "base_ref": lane.get("base_ref"),
    }


def actor_step(
    *,
    config: WorkflowConfig,
    lane: dict[str, Any],
    inputs: dict[str, Any],
) -> str:
    for value in (inputs.get("step"), inputs.get("mode"), lane.get("step")):
        text = str(value or "").strip().lower()
        if text:
            return text
    return lane_step(config=config, lane=lane)


def _review_feedback(*, lane: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    review = lane.get("review_signals")
    review = review if isinstance(review, dict) else {}
    retry = inputs.get("retry") if isinstance(inputs.get("retry"), dict) else {}
    feedback = {
        "review": review,
        "required_fixes": inputs.get("required_fixes")
        or review.get("required_changes")
        or retry.get("required_fixes"),
        "findings": inputs.get("findings") or review.get("comments") or retry.get("findings"),
        "verification_gaps": inputs.get("verification_gaps")
        or review.get("checks")
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
