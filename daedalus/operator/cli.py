"""Operator CLI compatibility exports."""

try:
    from daedalus.daedalus_cli import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from daedalus_cli import *  # type: ignore # noqa: F401,F403

