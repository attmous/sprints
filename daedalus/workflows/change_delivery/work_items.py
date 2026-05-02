from __future__ import annotations

from typing import Any

from engine.work_items import WorkItemRef


def lane_to_work_item_ref(lane: dict[str, Any]) -> WorkItemRef:
    """Expose a change-delivery lane through the shared engine work-item shape."""
    lane_id = str(lane.get("lane_id") or "").strip()
    issue_number = lane.get("issue_number")
    if not lane_id:
        if issue_number in (None, ""):
            raise ValueError("change-delivery lane is missing lane_id and issue_number")
        lane_id = f"lane:{issue_number}"
    identifier = f"#{issue_number}" if issue_number not in (None, "") else lane_id
    return WorkItemRef(
        id=lane_id,
        identifier=identifier,
        state=str(lane.get("workflow_state") or "").strip() or None,
        title=str(lane.get("issue_title") or "").strip() or None,
        url=str(lane.get("issue_url") or "").strip() or None,
        source="change-delivery",
        metadata={
            "issue_number": issue_number,
            "lane_status": lane.get("lane_status"),
            "active_actor_id": lane.get("active_actor_id"),
            "current_action_id": lane.get("current_action_id"),
        },
    )
