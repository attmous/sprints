import importlib


def test_engine_cleanup_modules_reexport_existing_schema_run_event_and_retry_api():
    engine = importlib.import_module("engine")
    schema = importlib.import_module("engine.schema")
    runs = importlib.import_module("engine.runs")
    events = importlib.import_module("engine.events")
    retries = importlib.import_module("engine.retries")

    assert callable(schema.init_engine_state)
    assert callable(schema.engine_state_tables_exist)
    assert callable(runs.start_engine_run_to_connection)
    assert callable(runs.read_engine_runs)
    assert callable(events.append_engine_event_to_connection)
    assert callable(events.read_engine_events)
    assert callable(retries.schedule_retry_entry)
    assert callable(retries.retry_due_at)
    assert schema.init_engine_state.__name__ == engine.init_engine_state.__name__
    assert retries.retry_due_at.__name__ == engine.retry_due_at.__name__
