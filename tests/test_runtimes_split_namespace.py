import importlib


def test_runtime_types_and_registry_modules_reexport_existing_runtime_api():
    runtimes = importlib.import_module("runtimes")
    types = importlib.import_module("runtimes.types")
    registry = importlib.import_module("runtimes.registry")

    assert types.PromptRunResult is runtimes.PromptRunResult
    assert types.SessionHandle is runtimes.SessionHandle
    assert types.SessionHealth is runtimes.SessionHealth
    assert types.Runtime is runtimes.Runtime
    assert registry.build_runtimes is runtimes.build_runtimes
    assert registry.register is runtimes.register


def test_runtime_command_module_reexports_stage_command_helpers():
    stages = importlib.import_module("runtimes.stages")
    command = importlib.import_module("runtimes.command")

    assert command.resolve_stage_command is stages.resolve_stage_command
    assert command.substitute_command_placeholders is stages.substitute_command_placeholders
    assert command.materialize_prompt is stages.materialize_prompt
    assert command.runtime_result_path is stages.runtime_result_path
