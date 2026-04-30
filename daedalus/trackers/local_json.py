from __future__ import annotations

import json
from pathlib import Path

from . import (
    DEFAULT_TERMINAL_STATES,
    TrackerConfigError,
    cfg_list,
    normalize_issue,
    register,
    resolve_tracker_path,
)


@register("local-json")
class LocalJsonTrackerClient:
    kind = "local-json"

    def __init__(self, *, workflow_root: Path, tracker_cfg: dict[str, object]):
        self._workflow_root = workflow_root
        self._tracker_cfg = tracker_cfg

    def list_all(self) -> list[dict[str, object]]:
        path = resolve_tracker_path(workflow_root=self._workflow_root, tracker_cfg=self._tracker_cfg)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            raw_issues = payload.get("issues")
        else:
            raw_issues = payload
        if not isinstance(raw_issues, list):
            raise TrackerConfigError(f"{path} must contain a top-level list or an object with an 'issues' list")
        return [normalize_issue(item) for item in raw_issues]

    def list_candidates(self) -> list[dict[str, object]]:
        from workflows.issue_runner.tracker import eligible_issues

        return eligible_issues(tracker_cfg=self._tracker_cfg, issues=self.list_all())

    def refresh(self, issue_ids: list[str]) -> dict[str, dict[str, object]]:
        ids = {str(issue_id).strip() for issue_id in issue_ids if str(issue_id).strip()}
        if not ids:
            return {}
        return {
            str(issue["id"]): issue
            for issue in self.list_all()
            if issue.get("id") in ids
        }

    def list_terminal(self) -> list[dict[str, object]]:
        terminal_states = {
            str(value).strip().lower()
            for value in (cfg_list(self._tracker_cfg, "terminal_states", "terminal-states") or DEFAULT_TERMINAL_STATES)
            if str(value).strip()
        }
        return [
            issue
            for issue in self.list_all()
            if str(issue.get("state") or "").strip().lower() in terminal_states
        ]
