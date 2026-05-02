"""Tracker registry exports for the integrations namespace."""

try:
    from trackers import (
        build_tracker_client,
        describe_tracker_source,
        load_issues,
        register,
        resolve_tracker_path,
        tracker_kind,
    )
except ModuleNotFoundError:
    from daedalus.trackers import (
        build_tracker_client,
        describe_tracker_source,
        load_issues,
        register,
        resolve_tracker_path,
        tracker_kind,
    )

__all__ = [
    "build_tracker_client",
    "describe_tracker_source",
    "load_issues",
    "register",
    "resolve_tracker_path",
    "tracker_kind",
]
