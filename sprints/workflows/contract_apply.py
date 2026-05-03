from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from workflows.config import WorkflowConfig
from workflows.contracts import (
    DEFAULT_WORKFLOW_MARKDOWN_FILENAME,
    WorkflowContractError,
    load_workflow_contract,
    load_workflow_contract_file,
    snapshot_workflow_contract,
)


class WorkflowContractApplyError(RuntimeError):
    pass


def apply_workflow_contract(
    *,
    workflow_root: Path,
    source_ref: str = "origin/main",
    force: bool = False,
) -> dict[str, Any]:
    root = Path(workflow_root).expanduser().resolve()
    current = load_workflow_contract(root)
    config = WorkflowConfig.from_raw(raw=current.config, workflow_root=root)
    active_lanes = _active_lanes(config.storage.state_path)
    if active_lanes and not force:
        raise WorkflowContractApplyError(
            "cannot apply workflow contract while lanes are active: "
            + ", ".join(active_lanes)
            + " (pass --force to override)"
        )
    repo_path = _repo_path(config)
    _git("fetch", "origin", cwd=repo_path)
    source_commit = _git("rev-parse", source_ref, cwd=repo_path).strip()
    text = _git(
        "show", f"{source_ref}:{DEFAULT_WORKFLOW_MARKDOWN_FILENAME}", cwd=repo_path
    )
    incoming_path = root / "config" / "incoming-WORKFLOW.md"
    incoming_path.parent.mkdir(parents=True, exist_ok=True)
    incoming_path.write_text(text, encoding="utf-8")
    try:
        incoming = load_workflow_contract_file(incoming_path)
        WorkflowConfig.from_raw(raw=incoming.config, workflow_root=root)
    except (WorkflowContractError, OSError, ValueError) as exc:
        raise WorkflowContractApplyError(
            f"incoming workflow contract is invalid: {exc}"
        ) from exc
    meta = snapshot_workflow_contract(
        workflow_root=root,
        source_path=incoming_path,
        source_ref=source_ref,
        source_commit=source_commit,
    )
    return {
        "ok": True,
        "workflow_root": str(root),
        "source_ref": source_ref,
        "source_commit": source_commit,
        "active_lanes": active_lanes,
        **meta,
    }


def _repo_path(config: WorkflowConfig) -> Path:
    repository = config.raw.get("repository")
    if not isinstance(repository, dict):
        raise WorkflowContractApplyError("repository config must be a mapping")
    raw_path = str(repository.get("local-path") or repository.get("local_path") or "")
    if not raw_path.strip():
        raise WorkflowContractApplyError("repository.local-path is required")
    path = Path(raw_path).expanduser()
    resolved = path if path.is_absolute() else (config.workflow_root / path).resolve()
    if not resolved.is_dir():
        raise WorkflowContractApplyError(
            f"repository.local-path is not a directory: {resolved}"
        )
    return resolved


def _active_lanes(state_path: Path) -> list[str]:
    if not state_path.exists():
        return []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    lanes = state.get("lanes") if isinstance(state, dict) else {}
    if not isinstance(lanes, dict):
        return []
    active: list[str] = []
    for lane_id, lane in lanes.items():
        if not isinstance(lane, dict):
            continue
        status = str(lane.get("status") or "").strip()
        if status not in {"complete", "released"}:
            active.append(str(lane_id))
    return active


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
        raise WorkflowContractApplyError(
            f"`git {' '.join(args)}` failed in {cwd}: {detail}"
        )
    return completed.stdout
