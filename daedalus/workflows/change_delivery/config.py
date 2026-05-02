"""Typed config view for the change-delivery workflow."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflows.core.config import ConfigView, resolve_path


@dataclass(frozen=True)
class RepositoryConfig:
    local_path: Path | None
    slug: str | None
    active_lane_label: str


@dataclass(frozen=True)
class TrackerConfig:
    kind: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class CodeHostConfig:
    kind: str | None
    github_slug: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class RuntimeProfilesConfig:
    profiles: dict[str, dict[str, Any]]

    def kind(self, runtime_name: str) -> str | None:
        profile = self.profiles.get(runtime_name) or {}
        value = profile.get("kind")
        return str(value).strip() if value else None


@dataclass(frozen=True)
class ActorConfig:
    name: str
    model: str | None
    runtime: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class StageConfig:
    name: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class GateConfig:
    name: str
    type: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class StorageConfig:
    ledger: Path
    health: Path
    audit_log: Path
    scheduler: Path

    def as_dict(self) -> dict[str, Path]:
        return {
            "ledger": self.ledger,
            "health": self.health,
            "audit_log": self.audit_log,
            "scheduler": self.scheduler,
        }


@dataclass(frozen=True)
class WebhookConfig:
    subscriptions: list[dict[str, Any]]


@dataclass(frozen=True)
class ServerConfig:
    port: int
    bind: str


@dataclass(frozen=True)
class ChangeDeliveryConfig:
    raw: dict[str, Any]
    workflow_root: Path
    repository: RepositoryConfig
    tracker: TrackerConfig
    code_host: CodeHostConfig
    runtimes: RuntimeProfilesConfig
    actors: dict[str, ActorConfig]
    stages: dict[str, StageConfig]
    gates: dict[str, GateConfig]
    storage: StorageConfig
    webhooks: WebhookConfig
    server: ServerConfig

    @classmethod
    def from_raw(
        cls,
        config: dict[str, Any],
        *,
        workflow_root: Path | None = None,
    ) -> "ChangeDeliveryConfig":
        root = (workflow_root or Path(".")).expanduser().resolve()
        view = ConfigView(config, workflow_root=root)
        repository_raw = view.mapping("repository", default={}) or {}
        repository = ConfigView(repository_raw, workflow_root=root)
        tracker_raw = view.mapping("tracker", default={}) or {}
        code_host_raw = view.mapping("code-host", "code_host", default={}) or {}
        runtimes_raw = _mapping_of_mappings(view.mapping("runtimes", default={}) or {})
        actors_raw = _mapping_of_mappings(view.mapping("actors", default={}) or {})
        stages_raw = _mapping_of_mappings(view.mapping("stages", default={}) or {})
        gates_raw = _mapping_of_mappings(view.mapping("gates", default={}) or {})
        storage_raw = view.mapping("storage", default={}) or {}
        storage = ConfigView(storage_raw, workflow_root=root)
        server = ConfigView(view.mapping("server", default={}) or {})
        local_path_value = repository.value("local-path", "local_path")
        return cls(
            raw=deepcopy(config),
            workflow_root=root,
            repository=RepositoryConfig(
                local_path=(
                    resolve_path(local_path_value, workflow_root=root)
                    if local_path_value not in (None, "")
                    else None
                ),
                slug=repository.str("slug"),
                active_lane_label=repository.str("active-lane-label", "active_lane_label", default="active-lane") or "active-lane",
            ),
            tracker=TrackerConfig(
                kind=ConfigView(tracker_raw).str("kind"),
                raw=deepcopy(tracker_raw),
            ),
            code_host=CodeHostConfig(
                kind=ConfigView(code_host_raw).str("kind"),
                github_slug=ConfigView(code_host_raw).str("github_slug", "github-slug"),
                raw=deepcopy(code_host_raw),
            ),
            runtimes=RuntimeProfilesConfig(profiles=deepcopy(runtimes_raw)),
            actors={
                name: ActorConfig(
                    name=name,
                    model=ConfigView(actor).str("model"),
                    runtime=ConfigView(actor).str("runtime"),
                    raw=deepcopy(actor),
                )
                for name, actor in actors_raw.items()
            },
            stages={
                name: StageConfig(name=name, raw=deepcopy(stage))
                for name, stage in stages_raw.items()
            },
            gates={
                name: GateConfig(
                    name=name,
                    type=ConfigView(gate).str("type"),
                    raw=deepcopy(gate),
                )
                for name, gate in gates_raw.items()
            },
            storage=StorageConfig(
                ledger=resolve_path(storage.value("ledger"), workflow_root=root, default="memory/workflow-status.json"),
                health=resolve_path(storage.value("health"), workflow_root=root, default="memory/workflow-health.json"),
                audit_log=resolve_path(
                    storage.value("audit-log", "audit_log"),
                    workflow_root=root,
                    default="memory/workflow-audit.jsonl",
                ),
                scheduler=resolve_path(
                    storage.value("scheduler"),
                    workflow_root=root,
                    default="memory/workflow-scheduler.json",
                ),
            ),
            webhooks=WebhookConfig(
                subscriptions=list(view.list("webhooks", default=[]) or [])
            ),
            server=ServerConfig(
                port=server.int("port", default=8080) or 8080,
                bind=server.str("bind", default="127.0.0.1") or "127.0.0.1",
            ),
        )

    def actor(self, name: str) -> ActorConfig | None:
        return self.actors.get(name)

    def runtime_for_actor(self, name: str) -> dict[str, Any] | None:
        actor = self.actor(name)
        if actor is None or not actor.runtime:
            return None
        return self.runtimes.profiles.get(actor.runtime)


def _mapping_of_mappings(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(key): dict(item)
        for key, item in value.items()
        if isinstance(item, dict)
    }


def change_delivery_storage_paths_from_config(
    workflow_root: Path,
    config: dict[str, Any] | None,
) -> dict[str, Path]:
    return ChangeDeliveryConfig.from_raw(config or {}, workflow_root=workflow_root).storage.as_dict()
