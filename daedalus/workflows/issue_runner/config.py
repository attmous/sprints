"""Typed config normalization for the issue-runner workflow."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflows.core.config import ConfigView, get_int, get_mapping, get_value, resolve_path


DEFAULT_ACTIVE_STATES = ("todo", "open", "ready")
DEFAULT_TERMINAL_STATES = ("done", "closed", "canceled", "cancelled", "resolved")
DEFAULT_MAX_RETRY_BACKOFF_MS = 300000


def _clean_str_list(values: list[Any] | None, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw_values = values if values is not None else list(default)
    return tuple(str(value).strip() for value in raw_values if str(value).strip())


def _normalized_state_limit_map(raw: dict[str, Any] | None) -> dict[str, int]:
    limits: dict[str, int] = {}
    for state, limit in (raw or {}).items():
        state_name = str(state).strip().lower()
        if not state_name:
            continue
        numeric_limit = int(limit)
        if numeric_limit > 0:
            limits[state_name] = numeric_limit
    return limits


@dataclass(frozen=True)
class PollingConfig:
    interval_ms: int
    interval_seconds: int

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "PollingConfig":
        polling = ConfigView(get_mapping(config, "polling", default={}) or {})
        interval_ms = polling.int("interval_ms")
        if interval_ms in (None, ""):
            interval_seconds = polling.int("interval_seconds", "interval-seconds", default=30) or 30
            interval_ms = int(interval_seconds) * 1000
        interval_ms = max(int(interval_ms or 30000), 1)
        return cls(
            interval_ms=interval_ms,
            interval_seconds=max(interval_ms // 1000, 1),
        )


@dataclass(frozen=True)
class WorkspaceConfig:
    root: Path


@dataclass(frozen=True)
class StorageConfig:
    status: Path
    health: Path
    audit_log: Path
    scheduler: Path


@dataclass(frozen=True)
class AgentConfig:
    max_concurrent_agents: int
    max_concurrent_agents_by_state: dict[str, int]
    max_retry_backoff_ms: int

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "AgentConfig":
        agent = ConfigView(get_mapping(config, "agent", default={}) or {})
        max_retry_backoff_ms = agent.int("max_retry_backoff_ms", default=DEFAULT_MAX_RETRY_BACKOFF_MS)
        if max_retry_backoff_ms in (None, 0):
            max_retry_backoff_ms = DEFAULT_MAX_RETRY_BACKOFF_MS
        return cls(
            max_concurrent_agents=max(agent.int("max_concurrent_agents", default=10) or 10, 1),
            max_concurrent_agents_by_state=_normalized_state_limit_map(
                agent.mapping("max_concurrent_agents_by_state", default={}) or {}
            ),
            max_retry_backoff_ms=int(max_retry_backoff_ms),
        )


@dataclass(frozen=True)
class TrackerRuntimeConfig:
    kind: str | None
    active_states: tuple[str, ...]
    terminal_states: tuple[str, ...]
    required_labels: tuple[str, ...]
    exclude_labels: tuple[str, ...]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "TrackerRuntimeConfig":
        tracker = ConfigView(get_mapping(config, "tracker", default={}) or {})
        return cls(
            kind=tracker.str("kind"),
            active_states=tuple(value.lower() for value in _clean_str_list(
                tracker.list("active_states", "active-states"),
                default=DEFAULT_ACTIVE_STATES,
            )),
            terminal_states=tuple(value.lower() for value in _clean_str_list(
                tracker.list("terminal_states", "terminal-states"),
                default=DEFAULT_TERMINAL_STATES,
            )),
            required_labels=tuple(value.lower() for value in _clean_str_list(
                tracker.list("required_labels", "required-labels"),
            )),
            exclude_labels=tuple(value.lower() for value in _clean_str_list(
                tracker.list("exclude_labels", "exclude-labels"),
            )),
        )


@dataclass(frozen=True)
class IssueRunnerConfig:
    raw: dict[str, Any]
    workflow_root: Path
    polling: PollingConfig
    workspace: WorkspaceConfig
    storage: StorageConfig
    agent: AgentConfig
    tracker: TrackerRuntimeConfig

    @classmethod
    def from_raw(
        cls,
        config: dict[str, Any],
        *,
        workflow_root: Path | None = None,
    ) -> "IssueRunnerConfig":
        root = (workflow_root or Path(".")).expanduser().resolve()
        workspace_cfg = ConfigView(get_mapping(config, "workspace", default={}) or {}, workflow_root=root)
        storage_cfg = ConfigView(get_mapping(config, "storage", default={}) or {}, workflow_root=root)
        return cls(
            raw=deepcopy(config),
            workflow_root=root,
            polling=PollingConfig.from_config(config),
            workspace=WorkspaceConfig(
                root=resolve_path(
                    workspace_cfg.value("root"),
                    workflow_root=root,
                    default="workspace/issues",
                )
            ),
            storage=StorageConfig(
                status=resolve_path(
                    storage_cfg.value("status"),
                    workflow_root=root,
                    default="memory/workflow-status.json",
                ),
                health=resolve_path(
                    storage_cfg.value("health"),
                    workflow_root=root,
                    default="memory/workflow-health.json",
                ),
                audit_log=resolve_path(
                    get_value(storage_cfg.raw, "audit-log", "audit_log"),
                    workflow_root=root,
                    default="memory/workflow-audit.jsonl",
                ),
                scheduler=resolve_path(
                    storage_cfg.value("scheduler"),
                    workflow_root=root,
                    default="memory/workflow-scheduler.json",
                ),
            ),
            agent=AgentConfig.from_config(config),
            tracker=TrackerRuntimeConfig.from_config(config),
        )


def scheduler_state_from_config(config: dict[str, Any]) -> dict[str, Any]:
    polling = PollingConfig.from_config(config)
    agent = AgentConfig.from_config(config)
    return {
        "poll_interval_ms": polling.interval_ms,
        "max_concurrent_agents": agent.max_concurrent_agents,
        "max_concurrent_agents_by_state": dict(agent.max_concurrent_agents_by_state),
    }


def poll_interval_seconds_from_config(config: dict[str, Any]) -> int:
    return PollingConfig.from_config(config).interval_seconds


def max_retry_backoff_ms_from_config(config: dict[str, Any]) -> int:
    return AgentConfig.from_config(config).max_retry_backoff_ms


def terminal_states_from_config(config: dict[str, Any]) -> set[str]:
    return set(TrackerRuntimeConfig.from_config(config).terminal_states)
