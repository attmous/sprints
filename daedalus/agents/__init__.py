"""Shared execution adapters reused across workflows.

This package owns the agent backend protocol and the concrete implementations
that know how to talk to Codex, Claude, Hermes Agent, and similar executors.
Workflow packages compose these backends with workflow-specific prompts,
policies, and state machines.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SessionHandle:
    record_id: str | None
    session_id: str | None
    name: str


@dataclass(frozen=True)
class SessionHealth:
    healthy: bool
    reason: str | None
    last_used_at: str | None


@dataclass(frozen=True)
class PromptRunResult:
    output: str
    session_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    last_event: str | None = None
    last_message: str | None = None
    turn_count: int = 0
    tokens: dict[str, int] | None = None
    rate_limits: dict | None = None


@runtime_checkable
class AgentRuntime(Protocol):
    def ensure_session(
        self,
        *,
        worktree: Path,
        session_name: str,
        model: str,
        resume_session_id: str | None = None,
    ) -> SessionHandle: ...

    def run_prompt(
        self,
        *,
        worktree: Path,
        session_name: str,
        prompt: str,
        model: str,
    ) -> str: ...

    def assess_health(
        self,
        session_meta: dict | None,
        *,
        worktree: Path | None,
        now_epoch: int | None = None,
    ) -> SessionHealth: ...

    def close_session(
        self,
        *,
        worktree: Path,
        session_name: str,
    ) -> None: ...

    def run_command(
        self,
        *,
        worktree: Path,
        command_argv: list[str],
        env: dict[str, str] | None = None,
    ) -> str: ...

    def last_activity_ts(self) -> float | None: ...


# Public compatibility alias. The workflow config still uses a `runtimes:`
# block today, so the runtime vocabulary remains valid at the contract layer
# while the shared implementation package becomes `agents/`.
Runtime = AgentRuntime

_AGENT_KINDS: dict[str, type] = {}
_RUNTIME_KINDS = _AGENT_KINDS


def register(kind: str):
    def _register(cls):
        _AGENT_KINDS[kind] = cls
        return cls

    return _register


def build_agents(agent_cfg: dict, *, run=None, run_json=None) -> dict[str, AgentRuntime]:
    if not agent_cfg:
        return {}

    from . import acpx_codex  # noqa: F401
    from . import claude_cli  # noqa: F401
    from . import codex_app_server  # noqa: F401
    from . import hermes_agent  # noqa: F401

    out: dict[str, AgentRuntime] = {}
    for profile_name, profile_cfg in agent_cfg.items():
        kind = profile_cfg.get("kind")
        if kind not in _AGENT_KINDS:
            raise ValueError(
                f"runtime profile {profile_name!r} declares unknown kind={kind!r}; "
                f"registered kinds: {sorted(_AGENT_KINDS)}"
            )
        cls = _AGENT_KINDS[kind]
        out[profile_name] = cls(profile_cfg, run=run, run_json=run_json)
    return out


def build_runtimes(runtimes_cfg: dict, *, run=None, run_json=None) -> dict[str, AgentRuntime]:
    return build_agents(runtimes_cfg, run=run, run_json=run_json)
