"""Actor-driven completion verification helpers."""

from __future__ import annotations

from typing import Any

from sprints.workflows.runtime_sessions import active_actor_dispatch


def done_release_verified(lane: dict[str, Any]) -> bool:
    if active_actor_dispatch(lane):
        return False
    if str(lane.get("status") or "").strip().lower() == "running":
        return False
    tracker = lane.get("tracker") if isinstance(lane.get("tracker"), dict) else {}
    state_labels = {
        str(label).strip().lower() for label in tracker.get("state_labels") or []
    }
    if len(state_labels) > 1:
        return False
    pull_request = (
        lane.get("pull_request") if isinstance(lane.get("pull_request"), dict) else {}
    )
    pr_state = str(pull_request.get("state") or "").strip().lower()
    if bool(pull_request.get("merged")) or pr_state == "merged":
        return True
    actor_outputs = (
        lane.get("actor_outputs") if isinstance(lane.get("actor_outputs"), dict) else {}
    )
    implementation = (
        actor_outputs.get("implementer")
        if isinstance(actor_outputs.get("implementer"), dict)
        else {}
    )
    output_pr = (
        implementation.get("pull_request")
        if isinstance(implementation.get("pull_request"), dict)
        else {}
    )
    output_state = str(output_pr.get("state") or "").strip().lower()
    return bool(output_pr.get("merged")) or output_state == "merged"
