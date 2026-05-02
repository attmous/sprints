"""Workflow registry and CLI dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import jsonschema
import yaml

from workflows.config import AgenticConfig
from workflows.contracts import WorkflowContractError, load_workflow_contract

NAME = "agentic"
SUPPORTED_SCHEMA_VERSIONS = (1,)
CONFIG_SCHEMA_PATH = Path(__file__).with_name("schema.yaml")


@runtime_checkable
class Workflow(Protocol):
    name: str
    schema_versions: tuple[int, ...]
    schema_path: Path

    def load_config(self, *, workflow_root: Path, raw: dict[str, Any]) -> object: ...

    def make_workspace(self, *, workflow_root: Path, config: object) -> object: ...

    def run_cli(self, *, workspace: object, argv: list[str]) -> int: ...


@dataclass(frozen=True)
class AgenticWorkflow:
    name: str = NAME
    schema_versions: tuple[int, ...] = SUPPORTED_SCHEMA_VERSIONS
    schema_path: Path = CONFIG_SCHEMA_PATH

    def load_config(self, *, workflow_root: Path, raw: dict[str, Any]) -> object:
        return load_config(workflow_root=workflow_root, raw=raw)

    def make_workspace(self, *, workflow_root: Path, config: object) -> object:
        return make_workspace(workflow_root=workflow_root, config=config)

    def run_cli(self, *, workspace: object, argv: list[str]) -> int:
        from workflows.runner import main

        return main(workspace, argv)


def load_config(*, workflow_root: Path, raw: dict[str, Any]) -> AgenticConfig:
    return AgenticConfig.from_raw(raw=raw, workflow_root=workflow_root)


def make_workspace(*, workflow_root: Path, config: object) -> AgenticConfig:
    if isinstance(config, AgenticConfig):
        return config
    if isinstance(config, dict):
        return AgenticConfig.from_raw(raw=config, workflow_root=workflow_root)
    raise TypeError(f"unsupported agentic config object: {type(config).__name__}")


def load_workflow_object(name: str) -> Workflow:
    if name == NAME:
        return WORKFLOW
    raise WorkflowContractError(
        f"unknown workflow {name!r}; supported workflows: {list_workflows()}"
    )


def run_cli(
    workflow_root: Path, argv: list[str], *, require_workflow: str | None = None
) -> int:
    contract = load_workflow_contract(workflow_root)
    raw_config = contract.config
    workflow_name = raw_config.get("workflow")
    if not workflow_name:
        raise WorkflowContractError(
            f"{contract.source_path} is missing top-level `workflow:` field"
        )
    if require_workflow and workflow_name != require_workflow:
        raise WorkflowContractError(
            f"{contract.source_path} declares workflow={workflow_name!r}, "
            f"but invocation pins require_workflow={require_workflow!r}"
        )
    workflow = load_workflow_object(str(workflow_name))
    schema = yaml.safe_load(workflow.schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(raw_config, schema)
    schema_version = int(raw_config.get("schema-version", 1))
    if schema_version not in workflow.schema_versions:
        raise WorkflowContractError(
            f"workflow {workflow_name!r} does not support schema-version={schema_version}; "
            f"supported: {list(workflow.schema_versions)}"
        )
    config = workflow.load_config(workflow_root=workflow_root, raw=raw_config)
    workspace = workflow.make_workspace(workflow_root=workflow_root, config=config)
    return workflow.run_cli(workspace=workspace, argv=argv)


def list_workflows() -> list[str]:
    return [NAME]


WORKFLOW = AgenticWorkflow()
