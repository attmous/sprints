"""Tracker integration compatibility namespace."""

try:
    from trackers import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from daedalus.trackers import *  # type: ignore # noqa: F401,F403
