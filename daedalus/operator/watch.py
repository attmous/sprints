"""Operator watch renderer compatibility exports."""

try:
    from daedalus.watch import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from watch import *  # type: ignore # noqa: F401,F403

