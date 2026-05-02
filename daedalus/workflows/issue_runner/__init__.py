"""Generic tracker-driven issue runner workflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any

NAME = "issue-runner"
SUPPORTED_SCHEMA_VERSIONS = (1,)
CONFIG_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"
PREFLIGHT_GATED_COMMANDS = frozenset({"tick", "run"})
SERVICE_MODES = frozenset({"active"})

from workflows.issue_runner.cli import main as cli_main
from workflows.issue_runner.preflight import run_preflight
from workflows.issue_runner.workspace import make_workspace
from workflows.issue_runner.workspace import load_workspace_from_config


def service_prepare(
    *,
    workflow_root: Path,
    project_key: str | None,
    service_mode: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "workflow": NAME,
        "project_key": project_key,
        "service_mode": service_mode,
        "skipped": True,
        "reason": "issue-runner initializes engine state through EngineStore on first service tick",
    }


def service_loop(
    *,
    workflow_root: Path,
    project_key: str | None,
    instance_id: str | None,
    interval_seconds: int,
    max_iterations: int | None,
    service_mode: str,
) -> dict[str, Any]:
    workspace = load_workspace_from_config(workspace_root=workflow_root)
    payload = workspace.run_loop(
        interval_seconds=interval_seconds,
        max_iterations=max_iterations,
    )
    return {
        "workflow": NAME,
        "project_key": project_key,
        "instance_id": instance_id,
        "service_mode": service_mode,
        **payload,
    }

__all__ = [
    "NAME",
    "SUPPORTED_SCHEMA_VERSIONS",
    "CONFIG_SCHEMA_PATH",
    "PREFLIGHT_GATED_COMMANDS",
    "SERVICE_MODES",
    "make_workspace",
    "cli_main",
    "run_preflight",
    "service_prepare",
    "service_loop",
]
