from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from sprints.core.config import WorkflowConfig


class LaneWorktreeError(RuntimeError):
    pass


def ensure_lane_worktree(*, config: WorkflowConfig, lane: dict[str, Any]) -> Path:
    repo_path = repository_path(config)
    lane_id = str(lane.get("lane_id") or "").strip()
    if not lane_id:
        raise LaneWorktreeError("lane_id is required to create a lane worktree")
    branch = str(lane.get("branch") or "").strip() or _branch_name(config, lane)
    worktree = _worktree_path(config=config, lane_id=lane_id)
    base_ref = _base_ref(config)
    if worktree.exists():
        if not (worktree / ".git").exists():
            raise LaneWorktreeError(
                f"lane worktree path exists but is not a git worktree: {worktree}"
            )
    else:
        _git("fetch", "origin", cwd=repo_path)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        if _branch_exists(repo_path=repo_path, branch=branch):
            _git("worktree", "add", str(worktree), branch, cwd=repo_path)
        else:
            _git(
                "worktree",
                "add",
                "-b",
                branch,
                str(worktree),
                base_ref,
                cwd=repo_path,
            )
        _run_workspace_hook(config=config, hook_name="after_create", cwd=worktree)
    lane["branch"] = branch
    lane["worktree"] = str(worktree)
    lane["base_ref"] = base_ref
    return worktree


def repository_path(config: WorkflowConfig) -> Path:
    repository = config.raw.get("repository")
    if not isinstance(repository, dict):
        raise LaneWorktreeError("repository config must be a mapping")
    raw_path = str(repository.get("local-path") or repository.get("local_path") or "")
    if not raw_path.strip():
        raise LaneWorktreeError("repository.local-path is required")
    path = Path(raw_path).expanduser()
    resolved = path if path.is_absolute() else (config.workflow_root / path).resolve()
    if not resolved.is_dir():
        raise LaneWorktreeError(f"repository.local-path is not a directory: {resolved}")
    return resolved


def _base_ref(config: WorkflowConfig) -> str:
    workspace_cfg = config.raw.get("worktrees")
    if isinstance(workspace_cfg, dict):
        value = str(
            workspace_cfg.get("base-ref") or workspace_cfg.get("base_ref") or ""
        )
        if value.strip():
            return value.strip()
    return "origin/main"


def _worktree_path(*, config: WorkflowConfig, lane_id: str) -> Path:
    workspace_cfg = config.raw.get("workspace")
    if not isinstance(workspace_cfg, dict):
        workspace_cfg = config.raw.get("worktrees")
    root = None
    if isinstance(workspace_cfg, dict):
        root = workspace_cfg.get("root")
    root_text = _render_workspace_value(
        str(root or "worktrees"), workflow=config.workflow_name, lane_id=lane_id
    )
    root_path = Path(root_text).expanduser()
    if not root_path.is_absolute():
        root_path = config.workflow_root / root_path
    return root_path.resolve() / _safe_segment(lane_id)


def _branch_name(config: WorkflowConfig, lane: dict[str, Any]) -> str:
    issue = lane.get("issue") if isinstance(lane.get("issue"), dict) else {}
    intake = config.raw.get("intake") if isinstance(config.raw.get("intake"), dict) else {}
    claim = intake.get("claim") if isinstance(intake.get("claim"), dict) else {}
    raw_id = str(issue.get("id") or lane.get("lane_id") or "lane")
    number = str(issue.get("number") or raw_id).lstrip("#")
    title = str(issue.get("title") or "change")
    template = str(claim.get("branch") or "").strip()
    if template:
        return (
            template.replace("{number}", _safe_segment(number))
            .replace("{id}", _safe_segment(raw_id))
            .replace("{slug}", _safe_branch_slug(title))
        )
    return f"codex/issue-{_safe_segment(raw_id)}-{_safe_branch_slug(title)}"


def _safe_branch_slug(value: str) -> str:
    text = value.lower()
    text = re.sub(r"^smoke test:\s*", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60].strip("-") or "change"


def _safe_segment(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace("#", "")
    text = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-._")
    return text or "lane"


def _render_workspace_value(value: str, *, workflow: str, lane_id: str) -> str:
    return value.replace("{{ workflow }}", workflow).replace("{{ lane_id }}", lane_id)


def _run_workspace_hook(
    *, config: WorkflowConfig, hook_name: str, cwd: Path
) -> None:
    workspace_cfg = config.raw.get("workspace")
    if not isinstance(workspace_cfg, dict):
        return
    hooks = workspace_cfg.get("hooks")
    if not isinstance(hooks, dict):
        return
    command = str(hooks.get(hook_name) or "").strip()
    if not command:
        return
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or f"workspace hook {hook_name} failed"
        )
        raise LaneWorktreeError(detail)


def _branch_exists(*, repo_path: Path, branch: str) -> bool:
    completed = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git failed"
        raise LaneWorktreeError(f"`git {' '.join(args)}` failed in {cwd}: {detail}")
    return completed.stdout.strip()
