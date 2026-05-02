"""Tracker type exports for the integrations namespace."""

try:
    from trackers import (
        DEFAULT_ACTIVE_STATES,
        DEFAULT_TERMINAL_STATES,
        TrackerClient,
        TrackerConfigError,
    )
except ModuleNotFoundError:
    from daedalus.trackers import (
        DEFAULT_ACTIVE_STATES,
        DEFAULT_TERMINAL_STATES,
        TrackerClient,
        TrackerConfigError,
    )

__all__ = [
    "DEFAULT_ACTIVE_STATES",
    "DEFAULT_TERMINAL_STATES",
    "TrackerClient",
    "TrackerConfigError",
]
