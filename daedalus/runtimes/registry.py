"""Runtime registry compatibility exports."""

try:
    from runtimes import build_runtimes, register
except ModuleNotFoundError:
    from daedalus.runtimes import build_runtimes, register

__all__ = ["build_runtimes", "register"]
