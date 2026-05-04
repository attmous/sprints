import os

from workflows.lanes import _runtime_process_is_missing


def test_runtime_process_is_missing_for_dead_process_id():
    assert _runtime_process_is_missing({"process_id": 999999999})


def test_runtime_process_is_not_missing_for_current_process():
    assert not _runtime_process_is_missing({"process_id": os.getpid()})
