"""Engine event compatibility exports."""

try:
    from daedalus.engine.state import (
        append_engine_event_to_connection,
        engine_event_stats_from_connection,
        engine_events_for_run_from_connection,
        engine_events_from_connection,
        prune_engine_events_to_connection,
        read_engine_event_stats,
        read_engine_events,
        read_engine_events_for_run,
    )
except ModuleNotFoundError:
    from .state import (
        append_engine_event_to_connection,
        engine_event_stats_from_connection,
        engine_events_for_run_from_connection,
        engine_events_from_connection,
        prune_engine_events_to_connection,
        read_engine_event_stats,
        read_engine_events,
        read_engine_events_for_run,
    )

__all__ = [
    "append_engine_event_to_connection",
    "engine_event_stats_from_connection",
    "engine_events_for_run_from_connection",
    "engine_events_from_connection",
    "prune_engine_events_to_connection",
    "read_engine_event_stats",
    "read_engine_events",
    "read_engine_events_for_run",
]
