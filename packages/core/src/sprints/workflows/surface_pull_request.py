"""Shared pull request field parsing for workflow surfaces."""

from __future__ import annotations

import re
from typing import Any, Mapping


def lane_pull_request(lane: Mapping[str, Any]) -> Mapping[str, Any]:
    value = lane.get("pull_request")
    return value if isinstance(value, Mapping) else {}


def pull_request_url(lane: Mapping[str, Any]) -> str:
    return str(lane_pull_request(lane).get("url") or "").strip()


def pull_request_number(lane: Mapping[str, Any]) -> str:
    pull_request = lane_pull_request(lane)
    for key in ("number", "pr_number", "id"):
        value = pull_request.get(key)
        if value not in (None, ""):
            number = trailing_number(value)
            if number:
                return number
    match = re.search(r"/pull/([0-9]+)(?:$|[/?#])", pull_request_url(lane))
    return match.group(1) if match else ""


def trailing_number(value: Any) -> str:
    text = str(value or "").strip().lstrip("#")
    match = re.search(r"([0-9]+)$", text)
    return match.group(1) if match else ""
