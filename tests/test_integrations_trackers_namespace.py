import importlib


def test_tracker_old_and_new_namespace_imports_resolve_same_public_objects():
    old = importlib.import_module("trackers")
    new = importlib.import_module("integrations.trackers")
    old_types = importlib.import_module("trackers")
    new_types = importlib.import_module("integrations.trackers.types")
    old_registry = importlib.import_module("trackers")
    new_registry = importlib.import_module("integrations.trackers.registry")

    assert new.TrackerConfigError is old.TrackerConfigError
    assert new_types.TrackerClient is old_types.TrackerClient
    assert new_registry.build_tracker_client is old_registry.build_tracker_client
    assert new_registry.register is old_registry.register


def test_tracker_adapter_modules_are_available_from_new_namespace():
    old_local_json = importlib.import_module("trackers.local_json")
    new_local_json = importlib.import_module("integrations.trackers.local_json")
    old_github = importlib.import_module("trackers.github")
    new_github = importlib.import_module("integrations.trackers.github")
    old_linear = importlib.import_module("trackers.linear")
    new_linear = importlib.import_module("integrations.trackers.linear")
    old_feedback = importlib.import_module("trackers.feedback")
    new_feedback = importlib.import_module("integrations.trackers.feedback")

    assert new_local_json.LocalJsonTrackerClient is old_local_json.LocalJsonTrackerClient
    assert new_github.GithubTrackerClient is old_github.GithubTrackerClient
    assert new_linear.LinearTrackerClient is old_linear.LinearTrackerClient
    assert new_feedback.publish_tracker_feedback is old_feedback.publish_tracker_feedback
