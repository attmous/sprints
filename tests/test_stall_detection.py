"""S-5 tests: stall detection — Symphony §8.5."""
from __future__ import annotations

import time
from dataclasses import dataclass

import pytest


def test_runtime_protocol_has_last_activity_ts():
    """The Runtime Protocol declares last_activity_ts (optional method)."""
    from workflows.code_review.runtimes import Runtime

    assert "last_activity_ts" in Runtime.__dict__ or hasattr(Runtime, "last_activity_ts"), \
        "Runtime Protocol must declare last_activity_ts"
