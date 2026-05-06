"""Label-backed board state helpers for actor-driven workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from sprints.core.config import WorkflowConfig


class BoardState(str, Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in-progress"
    REVIEW = "review"
    REWORK = "rework"
    MERGING = "merging"
    DONE = "done"


@dataclass(frozen=True)
class LabelMutation:
    add: list[str]
    remove: list[str]


def state_source_config(config: WorkflowConfig) -> dict[str, Any]:
    tracker = config.raw.get("tracker")
    tracker_cfg = tracker if isinstance(tracker, dict) else {}
    raw = tracker_cfg.get("state-source", tracker_cfg.get("state_source"))
    return raw if isinstance(raw, dict) else {}


def uses_label_state_source(config: WorkflowConfig) -> bool:
    source = state_source_config(config)
    return str(source.get("kind") or "").strip().lower() == "labels"


def state_labels(config: WorkflowConfig) -> dict[str, str]:
    source = state_source_config(config)
    if str(source.get("kind") or "").strip().lower() != "labels":
        return {}
    raw_labels = source.get("labels")
    labels = raw_labels if isinstance(raw_labels, Mapping) else {}
    out: dict[str, str] = {}
    seen: dict[str, str] = {}
    for state in BoardState:
        configured = str(labels.get(state.value) or state.value).strip()
        if configured:
            normalized = configured.lower()
            existing = seen.get(normalized)
            if existing is not None:
                raise ValueError(
                    "tracker state-source label mapping is ambiguous: "
                    f"{existing!r} and {state.value!r} both use label "
                    f"{configured!r}"
                )
            seen[normalized] = state.value
            out[state.value] = configured
    return out


def state_from_labels(labels: Iterable[Any], config: WorkflowConfig) -> str | None:
    configured = state_labels(config)
    if not configured:
        return None
    present_states = _present_states(labels, configured)
    if BoardState.DONE.value in present_states:
        return BoardState.DONE.value
    if BoardState.BACKLOG.value in present_states:
        return BoardState.BACKLOG.value
    for state in (
        BoardState.TODO,
        BoardState.IN_PROGRESS,
        BoardState.REVIEW,
        BoardState.REWORK,
        BoardState.MERGING,
    ):
        if state.value in present_states:
            return state.value
    return None


def state_label_names(labels: Iterable[Any], config: WorkflowConfig) -> list[str]:
    configured = {label.lower() for label in state_labels(config).values()}
    if not configured:
        return []
    return [label for label in _label_names(labels) if label.lower() in configured]


def non_state_labels(labels: Iterable[Any], config: WorkflowConfig) -> list[str]:
    configured = {label.lower() for label in state_labels(config).values()}
    return [label for label in _label_names(labels) if label.lower() not in configured]


def desired_state_mutation(
    current_labels: Iterable[Any],
    target_state: BoardState | str,
    config: WorkflowConfig,
) -> LabelMutation:
    target = _coerce_state(target_state)
    configured = state_labels(config)
    target_label = configured.get(target.value)
    if not target_label:
        raise ValueError(f"board state {target.value!r} is not configured")

    current = _label_names(current_labels)
    current_lower = {label.lower() for label in current}
    remove = [
        label
        for state, label in configured.items()
        if state != target.value and label.lower() in current_lower
    ]
    add = [] if target_label.lower() in current_lower else [target_label]
    return LabelMutation(add=add, remove=remove)


def board_metadata(issue: Mapping[str, Any], config: WorkflowConfig) -> dict[str, Any]:
    labels = issue.get("labels") or []
    return {
        "board_state": state_from_labels(labels, config),
        "board_state_source": "labels",
        "state_labels": state_label_names(labels, config),
    }


ACTIVE_BOARD_STATES = {
    BoardState.TODO.value,
    BoardState.IN_PROGRESS.value,
    BoardState.REVIEW.value,
    BoardState.REWORK.value,
    BoardState.MERGING.value,
}


def _label_names(labels: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for label in labels:
        value = str(label.get("name") if isinstance(label, dict) else label).strip()
        if value:
            out.append(value)
    return out


def _present_states(
    labels: Iterable[Any], configured: Mapping[str, str]
) -> set[str]:
    by_label = {label.lower(): state for state, label in configured.items()}
    return {
        state
        for label in _label_names(labels)
        for state in [by_label.get(label.lower())]
        if state
    }


def _coerce_state(value: BoardState | str) -> BoardState:
    if isinstance(value, BoardState):
        return value
    text = str(value or "").strip().lower().replace("_", "-")
    for state in BoardState:
        if state.value == text:
            return state
    raise ValueError(f"unknown board state: {value!r}")
