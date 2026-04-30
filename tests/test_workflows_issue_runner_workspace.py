import json
import shlex
import sys
from pathlib import Path

from workflows.contract import render_workflow_markdown


def _config(tmp_path: Path) -> dict:
    return {
        "workflow": "issue-runner",
        "schema-version": 1,
        "instance": {"name": "attmous-daedalus-issue-runner", "engine-owner": "hermes"},
        "repository": {"local-path": str(tmp_path / "repo"), "github-slug": "attmous/daedalus"},
        "tracker": {
            "kind": "local-json",
            "path": "config/issues.json",
            "active_states": ["todo"],
            "terminal_states": ["done"],
        },
        "workspace": {"root": "workspace/issues"},
        "hooks": {
            "after_create": "echo created > created.txt",
            "before_run": "echo before > before.txt",
            "after_run": "echo after > after.txt",
            "before_remove": "echo removing > removing.txt",
            "timeout_ms": 10000,
        },
        "agent": {
            "name": "Issue_Runner_Agent",
            "model": "gpt-5.4",
            "runtime": "default",
            "max_concurrent_agents": 1,
        },
        "codex": {
            "command": "codex app-server",
            "approval_policy": "auto",
            "thread_sandbox": "workspace-write",
            "turn_sandbox_policy": "auto",
            "turn_timeout_ms": 3600000,
            "read_timeout_ms": 5000,
            "stall_timeout_ms": 300000,
        },
        "daedalus": {
            "runtimes": {
                "default": {
                    "kind": "hermes-agent",
                    "command": ["fake-agent", "--prompt", "{prompt_path}", "--issue", "{issue_identifier}"],
                }
            }
        },
        "storage": {
            "status": "memory/workflow-status.json",
            "health": "memory/workflow-health.json",
            "audit-log": "memory/workflow-audit.jsonl",
        },
    }


def test_issue_runner_tick_runs_selected_issue_and_writes_artifacts(tmp_path):
    from workflows.issue_runner.workspace import load_workspace_from_config

    cfg = _config(tmp_path)
    workflow_root = tmp_path / "attmous-daedalus-issue-runner"
    workflow_root.mkdir()
    (workflow_root / "config").mkdir()
    (workflow_root / "config" / "issues.json").write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "id": "ISSUE-1",
                        "identifier": "ISSUE-1",
                        "title": "First issue",
                        "description": "Do the thing.",
                        "priority": 1,
                        "state": "todo",
                        "branch_name": "issue-1-first-issue",
                        "url": "https://tracker.example/issues/ISSUE-1",
                        "labels": ["sample"],
                        "blocked_by": [],
                    },
                    {
                        "id": "ISSUE-2",
                        "identifier": "ISSUE-2",
                        "title": "Done issue",
                        "description": "Already done.",
                        "priority": 2,
                        "state": "done",
                        "branch_name": "issue-2-done-issue",
                        "url": "https://tracker.example/issues/ISSUE-2",
                        "labels": [],
                        "blocked_by": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (workflow_root / "WORKFLOW.md").write_text(
        render_workflow_markdown(
            config=cfg,
            prompt_template=(
                "Issue: {{ issue.identifier }} - {{ issue.title }}\n"
                "URL: {{ issue.url }}\n"
                "Attempt: {{ attempt }}\n"
                "{{ issue.description }}"
            ),
        ),
        encoding="utf-8",
    )
    stale_terminal_workspace = workflow_root / "workspace" / "issues" / "issue-2"
    stale_terminal_workspace.mkdir(parents=True)
    (stale_terminal_workspace / "stale.txt").write_text("stale\n", encoding="utf-8")

    def fake_run(command, *, cwd=None, timeout=None, env=None):
        if command[:2] == ["bash", "-lc"] and cwd is not None:
            script = command[2]
            if "created.txt" in script:
                (cwd / "created.txt").write_text("created\n", encoding="utf-8")
            if "before.txt" in script:
                (cwd / "before.txt").write_text("before\n", encoding="utf-8")
            if "after.txt" in script:
                (cwd / "after.txt").write_text("after\n", encoding="utf-8")
            if "removing.txt" in script:
                (cwd / "removing.txt").write_text("removing\n", encoding="utf-8")

        class Result:
            stdout = "agent finished\n"
            stderr = ""
            returncode = 0

        return Result()

    workspace = load_workspace_from_config(
        workspace_root=workflow_root,
        run=fake_run,
        run_json=lambda *args, **kwargs: {},
    )

    result = workspace.tick()

    assert result["ok"] is True
    assert result["selectedIssue"]["id"] == "ISSUE-1"
    output_path = Path(result["outputPath"])
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == "agent finished\n"
    prompt_path = output_path.parent / "prompt.txt"
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "ISSUE-1 - First issue" in prompt
    assert "https://tracker.example/issues/ISSUE-1" in prompt
    issue_workspace = Path(result["workspace"])
    assert (issue_workspace / "created.txt").exists()
    assert (issue_workspace / "before.txt").exists()
    assert (issue_workspace / "after.txt").exists()
    assert not (workflow_root / "workspace" / "issues" / "issue-2").exists()
    status = workspace.build_status()
    assert status["selectedIssue"]["id"] == "ISSUE-1"
    assert status["tracker"]["eligibleCount"] == 1


def test_issue_runner_tick_uses_codex_app_server_and_persists_metrics(tmp_path):
    from workflows.issue_runner.workspace import load_workspace_from_config

    cfg = _config(tmp_path)
    cfg["agent"].pop("runtime", None)
    cfg.pop("daedalus", None)

    runtime_script = tmp_path / "fake_codex_app_server.py"
    runtime_script.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "prompt = sys.stdin.read()",
                'print(json.dumps({"event": "session_started", "session_id": "sess-1", "thread_id": "thread-1"}))',
                'print(json.dumps({"event": "turn_started", "turn_id": "turn-1"}))',
                'print(json.dumps({"text": "handled prompt", "message": "handled prompt"}))',
                'print(json.dumps({"event": "turn_completed", "turn_id": "turn-1", "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}, "rate_limits": {"requests_remaining": 99, "tokens_remaining": 9000}}))',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cfg["codex"]["command"] = f"{shlex.quote(sys.executable)} {shlex.quote(str(runtime_script))}"

    workflow_root = tmp_path / "attmous-daedalus-issue-runner"
    workflow_root.mkdir()
    (workflow_root / "config").mkdir()
    (workflow_root / "config" / "issues.json").write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "id": "ISSUE-1",
                        "identifier": "ISSUE-1",
                        "title": "First issue",
                        "description": "Do the thing.",
                        "priority": 1,
                        "state": "todo",
                        "branch_name": "issue-1-first-issue",
                        "url": "https://tracker.example/issues/ISSUE-1",
                        "labels": ["sample"],
                        "blocked_by": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (workflow_root / "WORKFLOW.md").write_text(
        render_workflow_markdown(
            config=cfg,
            prompt_template="Issue: {{ issue.identifier }}\nAttempt: {{ attempt }}",
        ),
        encoding="utf-8",
    )

    workspace = load_workspace_from_config(workspace_root=workflow_root)
    result = workspace.tick()

    assert result["ok"] is True
    assert result["metrics"]["session_id"] == "sess-1"
    assert result["metrics"]["thread_id"] == "thread-1"
    assert result["metrics"]["turn_id"] == "turn-1"
    assert result["metrics"]["tokens"] == {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
    }
    assert result["metrics"]["rate_limits"] == {
        "requests_remaining": 99,
        "tokens_remaining": 9000,
    }
    assert Path(result["outputPath"]).read_text(encoding="utf-8") == "handled prompt\n"

    status = workspace.build_status()
    assert status["metrics"]["tokens"]["total_tokens"] == 18
    assert status["metrics"]["rate_limits"]["requests_remaining"] == 99


def test_issue_runner_retry_queue_retries_failed_issue_on_next_due_tick(tmp_path):
    from workflows.issue_runner.workspace import load_workspace_from_config

    cfg = _config(tmp_path)
    workflow_root = tmp_path / "attmous-daedalus-issue-runner"
    workflow_root.mkdir()
    (workflow_root / "config").mkdir()
    (workflow_root / "config" / "issues.json").write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "id": "ISSUE-1",
                        "identifier": "ISSUE-1",
                        "title": "Retry me",
                        "description": "This issue should retry.",
                        "priority": 1,
                        "state": "todo",
                        "branch_name": "issue-1-retry-me",
                        "url": "https://tracker.example/issues/ISSUE-1",
                        "labels": [],
                        "blocked_by": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (workflow_root / "WORKFLOW.md").write_text(
        render_workflow_markdown(
            config=cfg,
            prompt_template="Issue: {{ issue.identifier }}",
        ),
        encoding="utf-8",
    )

    run_calls = {"agent": 0}

    def fake_run(command, *, cwd=None, timeout=None, env=None):
        if command[:2] == ["bash", "-lc"]:
            class HookResult:
                stdout = ""
                stderr = ""
                returncode = 0

            return HookResult()

        run_calls["agent"] += 1
        if run_calls["agent"] == 1:
            raise RuntimeError("temporary agent failure")

        class Result:
            stdout = "agent recovered\n"
            stderr = ""
            returncode = 0

        return Result()

    workspace = load_workspace_from_config(
        workspace_root=workflow_root,
        run=fake_run,
        run_json=lambda *args, **kwargs: {},
    )

    failed = workspace.tick()
    assert failed["ok"] is False
    assert failed["retry"]["retry_attempt"] == 1
    assert workspace.build_status()["scheduler"]["retry_queue"]

    workspace.retry_entries["ISSUE-1"]["due_at_monotonic"] = 0.0
    recovered = workspace.tick()
    assert recovered["ok"] is True
    assert recovered["selectedIssue"]["id"] == "ISSUE-1"
    assert workspace.build_status()["scheduler"]["retry_queue"] == []
    assert workspace.build_status()["scheduler"]["codex_totals"]["total_tokens"] == 0


def test_issue_runner_retry_queue_persists_across_workspace_reload(tmp_path):
    from workflows.issue_runner.workspace import load_workspace_from_config

    cfg = _config(tmp_path)
    workflow_root = tmp_path / "attmous-daedalus-issue-runner"
    workflow_root.mkdir()
    (workflow_root / "config").mkdir()
    (workflow_root / "config" / "issues.json").write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "id": "ISSUE-1",
                        "identifier": "ISSUE-1",
                        "title": "Retry me",
                        "description": "Persist the retry queue.",
                        "priority": 1,
                        "state": "todo",
                        "branch_name": "issue-1-retry-me",
                        "url": "https://tracker.example/issues/ISSUE-1",
                        "labels": [],
                        "blocked_by": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (workflow_root / "WORKFLOW.md").write_text(
        render_workflow_markdown(config=cfg, prompt_template="Issue: {{ issue.identifier }}"),
        encoding="utf-8",
    )

    def fail_run(command, *, cwd=None, timeout=None, env=None):
        if command[:2] == ["bash", "-lc"]:
            class HookResult:
                stdout = ""
                stderr = ""
                returncode = 0

            return HookResult()
        raise RuntimeError("temporary agent failure")

    workspace = load_workspace_from_config(
        workspace_root=workflow_root,
        run=fail_run,
        run_json=lambda *args, **kwargs: {},
    )
    failed = workspace.tick()
    assert failed["ok"] is False

    def success_run(command, *, cwd=None, timeout=None, env=None):
        if command[:2] == ["bash", "-lc"]:
            class HookResult:
                stdout = ""
                stderr = ""
                returncode = 0

            return HookResult()

        class Result:
            stdout = "agent recovered\n"
            stderr = ""
            returncode = 0

        return Result()

    reloaded = load_workspace_from_config(
        workspace_root=workflow_root,
        run=success_run,
        run_json=lambda *args, **kwargs: {},
    )
    assert reloaded.build_status()["scheduler"]["retry_queue"]
    reloaded.retry_entries["ISSUE-1"]["due_at_epoch"] = 0.0
    recovered = reloaded.tick()
    assert recovered["ok"] is True
    assert reloaded.build_status()["scheduler"]["retry_queue"] == []


def test_issue_runner_tick_dispatches_batch_up_to_max_concurrent_agents(tmp_path):
    from workflows.issue_runner.workspace import load_workspace_from_config

    cfg = _config(tmp_path)
    cfg["agent"]["max_concurrent_agents"] = 2
    workflow_root = tmp_path / "attmous-daedalus-issue-runner"
    workflow_root.mkdir()
    (workflow_root / "config").mkdir()
    (workflow_root / "config" / "issues.json").write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "id": "ISSUE-1",
                        "identifier": "ISSUE-1",
                        "title": "First issue",
                        "description": "Do the first thing.",
                        "priority": 1,
                        "state": "todo",
                        "branch_name": "issue-1-first-issue",
                        "url": "https://tracker.example/issues/ISSUE-1",
                        "labels": [],
                        "blocked_by": [],
                    },
                    {
                        "id": "ISSUE-2",
                        "identifier": "ISSUE-2",
                        "title": "Second issue",
                        "description": "Do the second thing.",
                        "priority": 2,
                        "state": "todo",
                        "branch_name": "issue-2-second-issue",
                        "url": "https://tracker.example/issues/ISSUE-2",
                        "labels": [],
                        "blocked_by": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (workflow_root / "WORKFLOW.md").write_text(
        render_workflow_markdown(config=cfg, prompt_template="Issue: {{ issue.identifier }}"),
        encoding="utf-8",
    )

    def fake_run(command, *, cwd=None, timeout=None, env=None):
        if command[:2] == ["bash", "-lc"]:
            class HookResult:
                stdout = ""
                stderr = ""
                returncode = 0

            return HookResult()

        class Result:
            stdout = f"handled {env['ISSUE_IDENTIFIER']}\n"
            stderr = ""
            returncode = 0

        return Result()

    workspace = load_workspace_from_config(
        workspace_root=workflow_root,
        run=fake_run,
        run_json=lambda *args, **kwargs: {},
    )

    result = workspace.tick()

    assert result["ok"] is True
    assert len(result["selectedIssues"]) == 2
    assert len(result["results"]) == 2
    identifiers = {item["issue"]["identifier"] for item in result["results"]}
    assert identifiers == {"ISSUE-1", "ISSUE-2"}
    assert workspace.build_status()["scheduler"]["running"] == []


def test_issue_runner_codex_failure_preserves_partial_metrics(tmp_path):
    from workflows.issue_runner.workspace import load_workspace_from_config

    cfg = _config(tmp_path)
    cfg["agent"].pop("runtime", None)
    cfg.pop("daedalus", None)

    runtime_script = tmp_path / "fake_codex_app_server_fail.py"
    runtime_script.write_text(
        "\n".join(
            [
                "import json",
                'print(json.dumps({"event": "session_started", "session_id": "sess-2", "thread_id": "thread-2"}))',
                'print(json.dumps({"event": "turn_started", "turn_id": "turn-2"}))',
                'print(json.dumps({"event": "turn_failed", "turn_id": "turn-2", "message": "tool call rejected", "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}, "rate_limits": {"requests_remaining": 88}}))',
                "raise SystemExit(1)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cfg["codex"]["command"] = f"{shlex.quote(sys.executable)} {shlex.quote(str(runtime_script))}"

    workflow_root = tmp_path / "attmous-daedalus-issue-runner"
    workflow_root.mkdir()
    (workflow_root / "config").mkdir()
    (workflow_root / "config" / "issues.json").write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "id": "ISSUE-1",
                        "identifier": "ISSUE-1",
                        "title": "Fail issue",
                        "description": "This should fail after emitting metrics.",
                        "priority": 1,
                        "state": "todo",
                        "branch_name": "issue-1-fail-issue",
                        "url": "https://tracker.example/issues/ISSUE-1",
                        "labels": [],
                        "blocked_by": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (workflow_root / "WORKFLOW.md").write_text(
        render_workflow_markdown(config=cfg, prompt_template="Issue: {{ issue.identifier }}"),
        encoding="utf-8",
    )

    workspace = load_workspace_from_config(workspace_root=workflow_root)
    result = workspace.tick()

    assert result["ok"] is False
    assert result["metrics"]["tokens"]["total_tokens"] == 7
    assert result["metrics"]["rate_limits"]["requests_remaining"] == 88
    assert workspace.build_status()["scheduler"]["codex_totals"]["total_tokens"] == 7
