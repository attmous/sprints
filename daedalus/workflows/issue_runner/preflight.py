from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflows.issue_runner.tracker import TrackerConfigError, build_tracker_client, resolve_tracker_path


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    error_code: str | None = None
    error_detail: str | None = None


def run_preflight(config: dict[str, Any]) -> PreflightResult:
    try:
        _validate_config(config)
    except RuntimeError as exc:
        return PreflightResult(ok=False, error_code="invalid-config", error_detail=str(exc))
    return PreflightResult(ok=True)


def _validate_config(config: dict[str, Any]) -> None:
    daedalus_cfg = config.get("daedalus") or {}
    runtimes = config.get("runtimes") or (daedalus_cfg.get("runtimes") if isinstance(daedalus_cfg, dict) else {}) or {}
    agent = config.get("agent") or {}
    codex_cfg = config.get("codex") or {}
    runtime_name = str(agent.get("runtime") or "").strip()
    if runtime_name:
        if runtime_name not in runtimes:
            raise RuntimeError(f"agent.runtime={runtime_name!r} does not reference a declared runtime profile")
        runtime_cfg = runtimes.get(runtime_name) or {}
        runtime_kind = str(runtime_cfg.get("kind") or "").strip()
        if runtime_kind == "hermes-agent":
            if not (agent.get("command") or runtime_cfg.get("command")):
                raise RuntimeError(
                    "hermes-agent runtime requires command on the runtime profile or agent block"
                )
        if runtime_kind == "codex-app-server":
            if not (runtime_cfg.get("command") or codex_cfg.get("command")):
                raise RuntimeError(
                    "codex-app-server runtime requires command on the runtime profile or codex block"
                )
    elif not (agent.get("command") or codex_cfg.get("command")):
        raise RuntimeError("issue-runner requires agent.runtime, agent.command, or codex.command")

    workflow_root = Path(".")
    tracker_cfg = config.get("tracker") or {}
    repository_cfg = config.get("repository") or {}
    repo_raw = str(
        repository_cfg.get("local-path")
        or repository_cfg.get("local_path")
        or ""
    ).strip()
    repo_path = None
    if repo_raw:
        repo_path = Path(repo_raw).expanduser()
        if not repo_path.is_absolute():
            repo_path = (workflow_root / repo_path).resolve()
    try:
        if str(tracker_cfg.get("kind") or "").strip() == "local-json":
            resolve_tracker_path(workflow_root=workflow_root, tracker_cfg=tracker_cfg)
        build_tracker_client(
            workflow_root=workflow_root,
            tracker_cfg=tracker_cfg,
            repo_path=repo_path,
        )
    except TrackerConfigError as exc:
        raise RuntimeError(str(exc)) from exc
