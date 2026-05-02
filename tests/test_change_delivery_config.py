from pathlib import Path

from workflows.change_delivery.config import ChangeDeliveryConfig, change_delivery_storage_paths_from_config


def _config() -> dict:
    return {
        "workflow": "change-delivery",
        "repository": {
            "local-path": "repo",
            "slug": "owner/repo",
            "active-lane-label": "active-lane",
        },
        "tracker": {"kind": "github", "github_slug": "owner/repo"},
        "code-host": {"kind": "github", "github_slug": "owner/repo"},
        "runtimes": {
            "coder-runtime": {"kind": "codex-app-server"},
            "reviewer-runtime": {"kind": "claude-cli"},
        },
        "actors": {
            "implementer": {"name": "impl", "model": "gpt-5", "runtime": "coder-runtime"},
            "reviewer": {"name": "review", "model": "claude", "runtime": "reviewer-runtime"},
        },
        "stages": {
            "implement": {"actor": "implementer"},
        },
        "gates": {
            "pre-publish-review": {"type": "agent-review", "actor": "reviewer"},
        },
        "storage": {
            "ledger": "state/ledger.json",
            "health": "state/health.json",
            "audit_log": "state/audit.jsonl",
            "scheduler": "state/scheduler.json",
        },
        "server": {"port": "9090", "bind": "0.0.0.0"},
        "webhooks": [{"name": "events", "kind": "http-json", "url": "https://example.test/hook"}],
    }


def test_change_delivery_config_normalizes_paths_and_sections(tmp_path):
    cfg = _config()
    typed = ChangeDeliveryConfig.from_raw(cfg, workflow_root=tmp_path)

    assert typed.repository.local_path == (tmp_path / "repo").resolve()
    assert typed.repository.slug == "owner/repo"
    assert typed.repository.active_lane_label == "active-lane"
    assert typed.tracker.kind == "github"
    assert typed.code_host.kind == "github"
    assert typed.code_host.github_slug == "owner/repo"
    assert typed.storage.ledger == (tmp_path / "state/ledger.json").resolve()
    assert typed.storage.health == (tmp_path / "state/health.json").resolve()
    assert typed.storage.audit_log == (tmp_path / "state/audit.jsonl").resolve()
    assert typed.storage.scheduler == (tmp_path / "state/scheduler.json").resolve()
    assert typed.server.port == 9090
    assert typed.server.bind == "0.0.0.0"
    assert typed.webhooks.subscriptions == cfg["webhooks"]


def test_change_delivery_config_exposes_actor_and_runtime_lookup_without_mutating_input(tmp_path):
    cfg = _config()
    typed = ChangeDeliveryConfig.from_raw(cfg, workflow_root=tmp_path)
    typed.raw["actors"]["implementer"]["runtime"] = "changed"

    assert typed.actor("implementer").runtime == "coder-runtime"
    assert typed.runtime_for_actor("implementer") == {"kind": "codex-app-server"}
    assert typed.runtimes.kind("reviewer-runtime") == "claude-cli"
    assert cfg["actors"]["implementer"]["runtime"] == "coder-runtime"


def test_change_delivery_storage_paths_helper_matches_typed_config(tmp_path):
    cfg = _config()

    paths = change_delivery_storage_paths_from_config(tmp_path, cfg)

    assert paths == ChangeDeliveryConfig.from_raw(cfg, workflow_root=tmp_path).storage.as_dict()


def test_change_delivery_config_applies_defaults(tmp_path):
    typed = ChangeDeliveryConfig.from_raw({}, workflow_root=tmp_path)

    assert typed.repository.local_path is None
    assert typed.repository.active_lane_label == "active-lane"
    assert typed.storage.ledger == (tmp_path / "memory/workflow-status.json").resolve()
    assert typed.storage.health == (tmp_path / "memory/workflow-health.json").resolve()
    assert typed.storage.audit_log == (tmp_path / "memory/workflow-audit.jsonl").resolve()
    assert typed.storage.scheduler == (tmp_path / "memory/workflow-scheduler.json").resolve()
    assert typed.server.port == 8080
    assert typed.server.bind == "127.0.0.1"
