import importlib
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from workflows.contract import (
    WORKFLOW_POLICY_KEY,
    load_workflow_contract,
    load_workflow_contract_file,
    write_workflow_contract_pointer,
)


PUBLIC_PACKAGE_IMPORTS = (
    "engine",
    "workflows",
    "runtimes",
    "trackers",
    "daedalus.engine",
    "daedalus.workflows",
    "daedalus.runtimes",
    "daedalus.trackers",
)

BUNDLED_WORKFLOWS = ("change-delivery", "issue-runner")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_contract(path: Path, *, workflow: str, body: str) -> None:
    config = {
        "workflow": workflow,
        "schema-version": 1,
    }
    path.write_text(
        "---\n" + yaml.safe_dump(config, sort_keys=False) + "---\n\n" + body + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("module_name", PUBLIC_PACKAGE_IMPORTS)
def test_public_package_imports_remain_available(module_name):
    module = importlib.import_module(module_name)

    assert module.__name__ == module_name


def test_repo_root_workflow_wrapper_imports_in_clean_interpreter():
    script = """
import workflows
import workflows.contract as contract
import workflows.__main__ as workflow_main
import workflows.issue_runner as issue_runner

assert callable(workflows.run_cli)
assert callable(workflow_main.main)
assert contract.WORKFLOW_POLICY_KEY == "workflow-policy"
assert issue_runner.NAME == "issue-runner"
assert "/daedalus/workflows/__init__.py" in workflows.__file__.replace("\\\\", "/")
assert "/daedalus/workflows/contract.py" in contract.__file__.replace("\\\\", "/")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout


@pytest.mark.parametrize("package_name", ("workflows", "daedalus.workflows"))
def test_bundled_workflows_remain_discoverable(package_name):
    package = importlib.import_module(package_name)

    assert set(BUNDLED_WORKFLOWS).issubset(package.list_workflows())


@pytest.mark.parametrize("workflow_name", BUNDLED_WORKFLOWS)
def test_workflow_cli_dispatch_resolves_bundled_workflow_names(tmp_path, monkeypatch, workflow_name):
    workflows = importlib.import_module("workflows")
    module = workflows.load_workflow(workflow_name)
    schema_path = tmp_path / f"{workflow_name}.schema.yaml"
    schema_path.write_text(
        yaml.safe_dump(
            {
                "type": "object",
                "required": ["workflow", "schema-version"],
                "properties": {
                    "workflow": {"type": "string"},
                    "schema-version": {"type": "integer"},
                    WORKFLOW_POLICY_KEY: {"type": "string"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    def fake_make_workspace(*, workflow_root, config):
        seen["workflow_root"] = workflow_root
        seen["config"] = config
        return {"workflow": config["workflow"]}

    def fake_cli_main(workspace, argv):
        seen["workspace"] = workspace
        seen["argv"] = argv
        return 17

    monkeypatch.setattr(module, "CONFIG_SCHEMA_PATH", schema_path)
    monkeypatch.setattr(module, "PREFLIGHT_GATED_COMMANDS", frozenset())
    monkeypatch.setattr(module, "make_workspace", fake_make_workspace)
    monkeypatch.setattr(module, "cli_main", fake_cli_main)

    workflow_root = tmp_path / "workflow-root"
    workflow_root.mkdir()
    _write_contract(
        workflow_root / "WORKFLOW.md",
        workflow=workflow_name,
        body=f"Prompt body for {workflow_name}.",
    )

    exit_code = workflows.run_cli(workflow_root, ["status", "--json"])

    assert exit_code == 17
    assert seen["workflow_root"] == workflow_root
    assert seen["config"]["workflow"] == workflow_name
    assert seen["config"][WORKFLOW_POLICY_KEY] == f"Prompt body for {workflow_name}."
    assert seen["workspace"] == {"workflow": workflow_name}
    assert seen["argv"] == ["status", "--json"]


def test_contract_loader_supports_default_markdown_named_markdown_and_pointer(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    default_contract = repo_root / "WORKFLOW.md"
    _write_contract(
        default_contract,
        workflow="change-delivery",
        body="Change delivery prompt body.",
    )

    named_repo_root = tmp_path / "named-repo"
    named_repo_root.mkdir()
    named_contract = named_repo_root / "WORKFLOW-issue-runner.md"
    _write_contract(
        named_contract,
        workflow="issue-runner",
        body="Issue runner prompt body.\n\nKeep Markdown paragraphs intact.",
    )

    default_loaded = load_workflow_contract(default_contract.parent)
    named_loaded = load_workflow_contract(named_repo_root)
    named_file_loaded = load_workflow_contract_file(named_contract)
    pointer_root = tmp_path / "workflow-root"
    write_workflow_contract_pointer(pointer_root, named_contract)
    pointer_loaded = load_workflow_contract(pointer_root)

    assert default_loaded.source_path == default_contract.resolve()
    assert default_loaded.prompt_template == "Change delivery prompt body."
    assert default_loaded.config[WORKFLOW_POLICY_KEY] == "Change delivery prompt body."
    assert named_loaded.source_path == named_contract.resolve()
    assert named_loaded.prompt_template == "Issue runner prompt body.\n\nKeep Markdown paragraphs intact."
    assert named_loaded.config[WORKFLOW_POLICY_KEY] == named_loaded.prompt_template
    assert named_file_loaded.source_path == named_contract.resolve()
    assert named_file_loaded.prompt_template == named_loaded.prompt_template
    assert pointer_loaded.source_path == named_contract.resolve()
    assert pointer_loaded.config["workflow"] == "issue-runner"
