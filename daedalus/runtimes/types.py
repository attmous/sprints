"""Runtime protocol and result type exports."""

try:
    from runtimes import PromptRunResult, Runtime, SessionHandle, SessionHealth
except ModuleNotFoundError:
    from daedalus.runtimes import PromptRunResult, Runtime, SessionHandle, SessionHealth

__all__ = [
    "PromptRunResult",
    "Runtime",
    "SessionHandle",
    "SessionHealth",
]
