from pathlib import Path

from workflows.issue_runner.config import (
    DEFAULT_MAX_RETRY_BACKOFF_MS,
    IssueRunnerConfig,
    max_retry_backoff_ms_from_config,
    poll_interval_seconds_from_config,
    scheduler_state_from_config,
    terminal_states_from_config,
)


def test_issue_runner_config_normalizes_polling_aliases_and_scheduler_state(tmp_path):
    cfg = {
        "polling": {"interval-seconds": "7"},
        "agent": {
            "max_concurrent_agents": "3",
            "max_concurrent_agents_by_state": {
                "Todo": "2",
                "": 5,
                "Blocked": 0,
            },
        },
    }

    typed = IssueRunnerConfig.from_raw(cfg, workflow_root=tmp_path)

    assert typed.polling.interval_ms == 7000
    assert typed.polling.interval_seconds == 7
    assert typed.agent.max_concurrent_agents == 3
    assert typed.agent.max_concurrent_agents_by_state == {"todo": 2}
    assert scheduler_state_from_config(cfg) == {
        "poll_interval_ms": 7000,
        "max_concurrent_agents": 3,
        "max_concurrent_agents_by_state": {"todo": 2},
    }


def test_issue_runner_config_prefers_interval_ms_and_clamps_poll_seconds(tmp_path):
    cfg = {
        "polling": {"interval_ms": 500},
        "agent": {},
    }

    typed = IssueRunnerConfig.from_raw(cfg, workflow_root=tmp_path)

    assert typed.polling.interval_ms == 500
    assert typed.polling.interval_seconds == 1
    assert poll_interval_seconds_from_config(cfg) == 1


def test_issue_runner_config_resolves_workspace_and_storage_paths(tmp_path):
    cfg = {
        "workspace": {"root": "workspace/custom"},
        "storage": {
            "status": "state/status.json",
            "health": "state/health.json",
            "audit_log": "state/audit.jsonl",
            "scheduler": "state/scheduler.json",
        },
        "agent": {},
    }

    typed = IssueRunnerConfig.from_raw(cfg, workflow_root=tmp_path)

    assert typed.workspace.root == (tmp_path / "workspace/custom").resolve()
    assert typed.storage.status == (tmp_path / "state/status.json").resolve()
    assert typed.storage.health == (tmp_path / "state/health.json").resolve()
    assert typed.storage.audit_log == (tmp_path / "state/audit.jsonl").resolve()
    assert typed.storage.scheduler == (tmp_path / "state/scheduler.json").resolve()


def test_issue_runner_config_applies_path_and_retry_defaults(tmp_path):
    typed = IssueRunnerConfig.from_raw({"agent": {}}, workflow_root=tmp_path)

    assert typed.workspace.root == (tmp_path / "workspace/issues").resolve()
    assert typed.storage.status == (tmp_path / "memory/workflow-status.json").resolve()
    assert typed.storage.health == (tmp_path / "memory/workflow-health.json").resolve()
    assert typed.storage.audit_log == (tmp_path / "memory/workflow-audit.jsonl").resolve()
    assert typed.storage.scheduler == (tmp_path / "memory/workflow-scheduler.json").resolve()
    assert typed.agent.max_retry_backoff_ms == DEFAULT_MAX_RETRY_BACKOFF_MS
    assert max_retry_backoff_ms_from_config({"agent": {"max_retry_backoff_ms": 0}}) == DEFAULT_MAX_RETRY_BACKOFF_MS


def test_issue_runner_config_normalizes_tracker_state_and_label_aliases(tmp_path):
    cfg = {
        "tracker": {
            "kind": "local-json",
            "active-states": ["Todo", "Ready"],
            "terminal_states": ["Done", "Closed"],
            "required-labels": ["Backend"],
            "exclude_labels": ["Blocked"],
        },
        "agent": {},
    }

    typed = IssueRunnerConfig.from_raw(cfg, workflow_root=tmp_path)

    assert typed.tracker.kind == "local-json"
    assert typed.tracker.active_states == ("todo", "ready")
    assert typed.tracker.terminal_states == ("done", "closed")
    assert typed.tracker.required_labels == ("backend",)
    assert typed.tracker.exclude_labels == ("blocked",)
    assert terminal_states_from_config(cfg) == {"done", "closed"}


def test_issue_runner_config_keeps_raw_config_available_without_mutating_input(tmp_path):
    cfg = {
        "workspace": {"root": "workspace/issues"},
        "agent": {"max_concurrent_agents_by_state": {"Todo": 1}},
    }

    typed = IssueRunnerConfig.from_raw(cfg, workflow_root=tmp_path)
    typed.raw["workspace"]["root"] = "changed"

    assert cfg["workspace"]["root"] == "workspace/issues"
    assert cfg["agent"]["max_concurrent_agents_by_state"] == {"Todo": 1}
