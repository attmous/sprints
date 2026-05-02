"""Engine schema initialization compatibility exports."""

try:
    from daedalus.engine.sqlite import connect_daedalus_db
    from daedalus.engine.state import engine_state_tables_exist, init_engine_state
except ModuleNotFoundError:
    from .sqlite import connect_daedalus_db
    from .state import engine_state_tables_exist, init_engine_state

__all__ = [
    "connect_daedalus_db",
    "engine_state_tables_exist",
    "init_engine_state",
]
