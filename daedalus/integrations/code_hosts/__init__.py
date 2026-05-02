"""Code-host integration compatibility namespace."""

try:
    from code_hosts import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from daedalus.code_hosts import *  # type: ignore # noqa: F401,F403

