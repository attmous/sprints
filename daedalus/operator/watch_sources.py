"""Operator watch-source compatibility exports."""

try:
    from daedalus.watch_sources import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from watch_sources import *  # type: ignore # noqa: F401,F403

