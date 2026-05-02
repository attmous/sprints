"""GitHub code-host adapter compatibility exports."""

try:
    from code_hosts.github import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from daedalus.code_hosts.github import *  # type: ignore # noqa: F401,F403

