from pathlib import Path

import pytest

from workflows.core.config import (
    ConfigError,
    ConfigView,
    first_present,
    get_bool,
    get_int,
    get_list,
    get_mapping,
    get_str,
    get_value,
    require,
    resolve_env_indirection,
    resolve_path,
)


def test_get_value_supports_nested_paths_and_dash_underscore_aliases():
    cfg = {
        "agent": {
            "max-concurrent-agents": 3,
        },
        "tracker": {
            "active_states": ["todo"],
        },
    }

    assert get_value(cfg, "agent.max_concurrent_agents") == 3
    assert get_value(cfg, "tracker.active-states") == ["todo"]
    assert first_present(cfg, "missing", "tracker.active-states") == ["todo"]
    assert get_value(cfg, "missing", default="fallback") == "fallback"


def test_require_rejects_missing_empty_and_none_values():
    cfg = {"empty": "", "none": None}

    with pytest.raises(ConfigError, match="missing required"):
        require(cfg, "missing")
    with pytest.raises(ConfigError, match="missing required"):
        require(cfg, "empty")
    with pytest.raises(ConfigError, match="missing required"):
        require(cfg, "none")


def test_typed_getters_apply_defaults_and_reject_wrong_types():
    cfg = {
        "name": "runner",
        "limit": "7",
        "enabled": "yes",
        "labels": ["ready"],
        "storage": {"status": "memory/status.json"},
    }

    assert get_str(cfg, "name") == "runner"
    assert get_str(cfg, "missing", default="default") == "default"
    assert get_int(cfg, "limit") == 7
    assert get_bool(cfg, "enabled") is True
    assert get_list(cfg, "labels") == ["ready"]
    assert get_mapping(cfg, "storage") == {"status": "memory/status.json"}

    with pytest.raises(ConfigError, match="must be int"):
        get_int({"limit": True}, "limit")
    with pytest.raises(ConfigError, match="must be bool"):
        get_bool({"enabled": 1}, "enabled")
    with pytest.raises(ConfigError, match="must be list"):
        get_list({"labels": "ready"}, "labels")
    with pytest.raises(ConfigError, match="must be Mapping"):
        get_mapping({"storage": []}, "storage")


def test_collection_getters_do_not_mutate_or_return_raw_collections():
    cfg = {
        "items": ["a"],
        "mapping": {"a": 1},
    }

    items = get_list(cfg, "items")
    mapping = get_mapping(cfg, "mapping")
    items.append("b")
    mapping["b"] = 2

    assert cfg == {"items": ["a"], "mapping": {"a": 1}}


def test_resolve_env_indirection_supports_env_tokens_and_literals():
    env = {"TOKEN": "resolved"}

    assert resolve_env_indirection("$TOKEN", env=env) == "resolved"
    assert resolve_env_indirection("literal", env=env) == "literal"
    assert resolve_env_indirection(7, env=env) == 7
    assert resolve_env_indirection("$MISSING", env=env) is None
    with pytest.raises(ConfigError, match="MISSING"):
        resolve_env_indirection("$MISSING", env=env, required=True)


def test_resolve_path_normalizes_relative_absolute_default_and_env_paths(tmp_path):
    env_path = tmp_path / "from-env"
    absolute = tmp_path / "absolute"

    assert resolve_path("relative/file.json", workflow_root=tmp_path) == (tmp_path / "relative/file.json").resolve()
    assert resolve_path(absolute, workflow_root=tmp_path) == absolute.resolve()
    assert resolve_path("", workflow_root=tmp_path, default="default.json") == (tmp_path / "default.json").resolve()
    assert resolve_path("$PATH_VALUE", workflow_root=tmp_path, env={"PATH_VALUE": str(env_path)}) == env_path.resolve()


def test_config_view_wraps_typed_helpers(tmp_path):
    cfg = {
        "polling": {"interval-seconds": "5"},
        "storage": {"status": "memory/status.json"},
    }
    view = ConfigView(cfg, workflow_root=tmp_path)

    assert view.section("polling").int("interval_seconds") == 5
    assert view.path("storage.status") == (tmp_path / "memory/status.json").resolve()
    assert view.section("missing").raw == {}
    with pytest.raises(ConfigError, match="workflow_root"):
        ConfigView(cfg).path("storage.status")


def test_resolve_path_requires_a_value(tmp_path):
    with pytest.raises(ConfigError, match="path value is required"):
        resolve_path(None, workflow_root=tmp_path)
