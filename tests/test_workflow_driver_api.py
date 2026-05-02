import json
from pathlib import Path

from workflows.contract import render_workflow_markdown
from workflows.core.types import WorkflowDriver


def test_issue_runner_workspace_conforms_to_workflow_driver_protocol(tmp_path):
    from workflows.issue_runner.workspace import load_workspace_from_config

    workflow_root = tmp_path / "issue-runner"
    workflow_root.mkdir()
    (workflow_root / "config").mkdir()
    (workflow_root / "config" / "issues.json").write_text(json.dumps({"issues": []}), encoding="utf-8")
    cfg = {
        "workflow": "issue-runner",
        "schema-version": 1,
        "repository": {"local-path": str(tmp_path / "repo")},
        "tracker": {"kind": "local-json", "path": "config/issues.json"},
        "agent": {"name": "runner", "model": "gpt-5", "runtime": "default"},
        "runtimes": {"default": {"kind": "hermes-agent", "command": ["true"]}},
        "storage": {},
    }
    (workflow_root / "WORKFLOW.md").write_text(
        render_workflow_markdown(config=cfg, prompt_template="Issue: {{ issue.identifier }}"),
        encoding="utf-8",
    )

    workspace = load_workspace_from_config(
        workspace_root=workflow_root,
        run=lambda *args, **kwargs: None,
        run_json=lambda *args, **kwargs: {},
    )

    assert isinstance(workspace, WorkflowDriver)


def test_change_delivery_workspace_conforms_to_workflow_driver_protocol(tmp_path):
    from workflows.change_delivery.workspace import make_workspace

    repo = tmp_path / "repo"
    repo.mkdir()
    workspace = make_workspace(
        workspace_root=tmp_path / "change-delivery",
        config={
            "repoPath": str(repo),
            "cronJobsPath": str(tmp_path / "jobs.json"),
            "ledgerPath": str(tmp_path / "memory" / "workflow-status.json"),
            "healthPath": str(tmp_path / "memory" / "workflow-health.json"),
            "auditLogPath": str(tmp_path / "memory" / "workflow-audit.jsonl"),
            "schedulerPath": str(tmp_path / "memory" / "workflow-scheduler.json"),
        },
    )

    assert isinstance(workspace, WorkflowDriver)
