from pathlib import Path
from types import SimpleNamespace

import pytest

from workflows.core.hooks import build_hook_env, run_shell_hook


def test_build_hook_env_stringifies_values():
    assert build_hook_env({"A": 1, "B": Path("/tmp/work")}) == {
        "A": "1",
        "B": "/tmp/work",
    }


def test_run_shell_hook_returns_not_ran_when_hook_is_missing(tmp_path):
    result = run_shell_hook(
        hooks_config={},
        hook_name="before_run",
        worktree=tmp_path,
        env={},
        run=lambda *args, **kwargs: None,
    )

    assert result == {"hook": "before_run", "ran": False}


def test_run_shell_hook_executes_configured_script_with_timeout_alias(tmp_path):
    calls = []

    def fake_run(command, *, cwd, timeout, env):
        calls.append({"command": command, "cwd": cwd, "timeout": timeout, "env": env})
        return SimpleNamespace(returncode=4)

    result = run_shell_hook(
        hooks_config={"before-run": "echo before", "timeout_ms": 2500},
        hook_name="before_run",
        worktree=tmp_path,
        env={"X": "1"},
        run=fake_run,
    )

    assert result == {"hook": "before_run", "ran": True, "returncode": 4}
    assert calls == [
        {
            "command": ["bash", "-lc", "echo before"],
            "cwd": tmp_path,
            "timeout": 2,
            "env": {"X": "1"},
        }
    ]


def test_run_shell_hook_raises_or_returns_ignored_failure(tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_shell_hook(
            hooks_config={"after_run": "false"},
            hook_name="after_run",
            worktree=tmp_path,
            env={},
            run=fail,
        )

    result = run_shell_hook(
        hooks_config={"after_run": "false"},
        hook_name="after_run",
        worktree=tmp_path,
        env={},
        run=fail,
        ignore_failure=True,
    )

    assert result == {
        "hook": "after_run",
        "ran": True,
        "returncode": None,
        "ignored_failure": True,
        "error": "boom",
    }
