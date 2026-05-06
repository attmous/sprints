"""Typed config for Sprints workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from sprints.core.contracts import WORKFLOW_POLICY_KEY, parse_workflow_policy


class WorkflowConfigError(RuntimeError):
    """Raised when workflow config is structurally invalid."""


@dataclass(frozen=True)
class RuntimeConfig:
    name: str
    kind: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActorConfig:
    name: str
    runtime: str
    model: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageConfig:
    name: str
    actors: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    next_stage: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GateConfig:
    name: str
    type: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionConfig:
    name: str
    type: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StorageConfig:
    state_path: Path
    audit_log_path: Path


@dataclass(frozen=True)
class OrchestrationConfig:
    mode: Literal["orchestrator", "actor-driven"] = "orchestrator"
    actor: str | None = None


@dataclass(frozen=True)
class WorkflowConfig:
    workflow_root: Path
    workflow_name: str
    raw: dict[str, Any]
    orchestration: OrchestrationConfig
    orchestrator_actor: str
    runtimes: dict[str, RuntimeConfig]
    actors: dict[str, ActorConfig]
    stages: dict[str, StageConfig]
    gates: dict[str, GateConfig]
    actions: dict[str, ActionConfig]
    storage: StorageConfig

    @classmethod
    def from_raw(cls, *, raw: dict[str, Any], workflow_root: Path) -> "WorkflowConfig":
        root = workflow_root.resolve()
        workflow_name = str(raw.get("workflow") or "").strip()
        if not workflow_name:
            raise WorkflowConfigError("workflow config requires top-level workflow")
        runtime_profiles = _runtime_profiles(raw)
        actor_profiles = _actor_profiles(raw, runtime_profiles=runtime_profiles)
        stage_profiles = _stage_profiles(raw, actor_names=tuple(actor_profiles))
        runtimes = {
            name: RuntimeConfig(
                name=name,
                kind=str(value.get("kind") or name),
                raw=dict(value),
            )
            for name, value in runtime_profiles.items()
        }
        actors = {
            name: ActorConfig(
                name=name,
                runtime=str(value["runtime"]),
                model=value.get("model"),
                raw=dict(value),
            )
            for name, value in actor_profiles.items()
        }
        stages = {
            name: StageConfig(
                name=name,
                actors=tuple(str(item) for item in value.get("actors") or ()),
                actions=tuple(str(item) for item in value.get("actions") or ()),
                gates=tuple(str(item) for item in value.get("gates") or ()),
                next_stage=value.get("next"),
                raw=dict(value),
            )
            for name, value in stage_profiles.items()
        }
        gates = {
            name: GateConfig(name=name, type=str(value["type"]), raw=dict(value))
            for name, value in dict(raw.get("gates") or {}).items()
        }
        actions = {
            name: ActionConfig(name=name, type=str(value["type"]), raw=dict(value))
            for name, value in dict(raw.get("actions") or {}).items()
        }
        storage_raw = dict(raw.get("storage") or {})
        state_path = _resolve(
            root, str(storage_raw.get("state", f".sprints/{workflow_name}-state.json"))
        )
        audit_log_path = _resolve(
            root,
            str(storage_raw.get("audit-log", f".sprints/{workflow_name}-audit.jsonl")),
        )
        orchestration = _orchestration_config(raw)
        orchestrator_actor = orchestration.actor or ""
        normalized_raw = _normalized_raw(
            raw=raw,
            runtime_profiles=runtime_profiles,
            actor_profiles=actor_profiles,
            stage_profiles=stage_profiles,
            orchestration=orchestration,
        )
        config = cls(
            workflow_root=root,
            workflow_name=workflow_name,
            raw=normalized_raw,
            orchestration=orchestration,
            orchestrator_actor=orchestrator_actor,
            runtimes=runtimes,
            actors=actors,
            stages=stages,
            gates=gates,
            actions=actions,
            storage=StorageConfig(state_path=state_path, audit_log_path=audit_log_path),
        )
        config.validate_references()
        return config

    @property
    def first_stage(self) -> str:
        try:
            return next(iter(self.stages))
        except StopIteration as exc:
            raise WorkflowConfigError("workflow requires at least one stage") from exc

    def is_actor_driven(self) -> bool:
        return self.orchestration.mode == "actor-driven"

    def requires_orchestrator_actor(self) -> bool:
        return self.orchestration.mode == "orchestrator"

    def validate_references(self) -> None:
        if (
            self.requires_orchestrator_actor()
            and self.orchestrator_actor not in self.actors
        ):
            raise WorkflowConfigError(
                f"unknown orchestrator actor: {self.orchestrator_actor}"
            )
        for actor in self.actors.values():
            if actor.runtime not in self.runtimes:
                raise WorkflowConfigError(
                    f"actor {actor.name} references unknown runtime {actor.runtime}"
                )
        for stage in self.stages.values():
            for actor in stage.actors:
                if actor not in self.actors:
                    raise WorkflowConfigError(
                        f"stage {stage.name} references unknown actor {actor}"
                    )
            for gate in stage.gates:
                if gate not in self.gates:
                    raise WorkflowConfigError(
                        f"stage {stage.name} references unknown gate {gate}"
                    )
            for action in stage.actions:
                if action not in self.actions:
                    raise WorkflowConfigError(
                        f"stage {stage.name} references unknown action {action}"
                    )
            if (
                stage.next_stage
                and stage.next_stage != "done"
                and stage.next_stage not in self.stages
            ):
                raise WorkflowConfigError(
                    f"stage {stage.name} references unknown next stage {stage.next_stage}"
                )


def _normalized_raw(
    *,
    raw: dict[str, Any],
    runtime_profiles: dict[str, dict[str, Any]],
    actor_profiles: dict[str, dict[str, Any]],
    stage_profiles: dict[str, dict[str, Any]],
    orchestration: OrchestrationConfig,
) -> dict[str, Any]:
    normalized_raw = dict(raw)
    normalized_raw["tracker"] = _normalized_tracker(raw)
    normalized_raw["runtimes"] = {
        name: dict(value) for name, value in runtime_profiles.items()
    }
    normalized_raw["actors"] = {
        name: dict(value) for name, value in actor_profiles.items()
    }
    normalized_raw["stages"] = {
        name: dict(value) for name, value in stage_profiles.items()
    }
    normalized_raw["gates"] = dict(raw.get("gates") or {})
    normalized_raw["actions"] = dict(raw.get("actions") or {})
    normalized_raw["orchestration"] = {
        key: value
        for key, value in {
            "mode": orchestration.mode,
            "actor": orchestration.actor,
        }.items()
        if value is not None
    }
    return normalized_raw


def _normalized_tracker(raw: dict[str, Any]) -> dict[str, Any]:
    tracker = dict(raw.get("tracker") or {})
    intake = raw.get("intake") if isinstance(raw.get("intake"), dict) else {}
    entry = intake.get("entry") if isinstance(intake.get("entry"), dict) else {}
    states = entry.get("states")
    if states is not None and "active_states" not in tracker:
        tracker["active_states"] = states
    include = entry.get("include_labels") or entry.get("include-labels")
    if include is not None and "required_labels" not in tracker:
        tracker["required_labels"] = include
    exclude = entry.get("exclude_labels") or entry.get("exclude-labels")
    if exclude is not None and "exclude_labels" not in tracker:
        tracker["exclude_labels"] = exclude
    return tracker


def _resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def _orchestration_config(raw: dict[str, Any]) -> OrchestrationConfig:
    legacy_orchestrator = dict(raw.get("orchestrator") or {})
    orchestration_raw = dict(raw.get("orchestration") or {})
    default_mode = (
        "orchestrator"
        if legacy_orchestrator or orchestration_raw.get("actor")
        else "actor-driven"
    )
    mode = str(orchestration_raw.get("mode") or default_mode).strip()
    if mode not in {"orchestrator", "actor-driven"}:
        raise WorkflowConfigError(
            "orchestration.mode must be 'orchestrator' or 'actor-driven'"
        )
    if mode == "actor-driven":
        return OrchestrationConfig(mode="actor-driven")
    actor = str(
        orchestration_raw.get("actor") or legacy_orchestrator.get("actor") or ""
    ).strip()
    return OrchestrationConfig(mode="orchestrator", actor=actor or None)


def _runtime_profiles(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    runtimes = raw.get("runtimes")
    if isinstance(runtimes, dict) and runtimes:
        return {
            str(name): dict(value)
            for name, value in runtimes.items()
            if isinstance(value, dict)
        }
    runtime = raw.get("runtime")
    if isinstance(runtime, dict) and runtime:
        return {"default": dict(runtime)}
    return {}


def _actor_profiles(
    raw: dict[str, Any], *, runtime_profiles: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    actors = raw.get("actors")
    if isinstance(actors, dict) and actors:
        return {
            str(name): dict(value)
            for name, value in actors.items()
            if isinstance(value, dict)
        }
    names = _policy_actor_names(raw)
    if not names:
        return {}
    if len(names) != 1:
        raise WorkflowConfigError(
            "single-runtime workflow config can infer only one actor"
        )
    runtime_name = next(iter(runtime_profiles), "")
    if not runtime_name:
        raise WorkflowConfigError("workflow actor requires a runtime profile")
    runtime_cfg = runtime_profiles[runtime_name]
    actor_name = names[0]
    return {
        actor_name: {
            "runtime": runtime_name,
            "model": runtime_cfg.get("model"),
            "skills": _policy_actor_skills(raw, actor_name),
        }
    }


def _stage_profiles(
    raw: dict[str, Any], *, actor_names: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    stages = raw.get("stages")
    if isinstance(stages, dict) and stages:
        return {
            str(name): dict(value)
            for name, value in stages.items()
            if isinstance(value, dict)
        }
    if len(actor_names) == 1:
        return {"work": {"actors": [actor_names[0]], "next": "done"}}
    return {}


def _policy_actor_names(raw: dict[str, Any]) -> tuple[str, ...]:
    policy = _policy(raw)
    if policy is None:
        return ()
    return tuple(policy.actors)


def _policy_actor_skills(raw: dict[str, Any], actor_name: str) -> list[str]:
    policy = _policy(raw)
    actor = policy.actors.get(actor_name) if policy else None
    if actor is None:
        return []
    lines = actor.body.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() != "## skills":
            continue
        for skill_line in lines[index + 1 :]:
            stripped = skill_line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                return []
            stripped = stripped.removeprefix("-").strip()
            return [item.strip() for item in stripped.split(",") if item.strip()]
    return []


def _policy(raw: dict[str, Any]) -> Any:
    text = raw.get(WORKFLOW_POLICY_KEY)
    if not isinstance(text, str) or not text.strip():
        return None
    return parse_workflow_policy(text)
