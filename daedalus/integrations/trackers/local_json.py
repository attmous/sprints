"""Local JSON tracker adapter compatibility exports."""

try:
    from trackers.local_json import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from daedalus.trackers.local_json import *  # type: ignore # noqa: F401,F403
