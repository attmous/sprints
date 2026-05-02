import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_ROOT = REPO_ROOT / "daedalus" / "workflows"


def test_workflows_support_layer_is_flat():
    unexpected = [
        WORKFLOWS_ROOT / "core",
        WORKFLOWS_ROOT / "shared",
        WORKFLOWS_ROOT / "change_delivery" / "runtimes",
        WORKFLOWS_ROOT / "change_delivery" / "config_snapshot.py",
        WORKFLOWS_ROOT / "change_delivery" / "stall.py",
    ]

    assert [path.relative_to(REPO_ROOT).as_posix() for path in unexpected if path.exists()] == []


def test_only_bundled_workflow_subpackages_remain():
    allowed = {"change_delivery", "issue_runner", "__pycache__"}
    dirs = {
        path.name
        for path in WORKFLOWS_ROOT.iterdir()
        if path.is_dir()
    }

    assert dirs <= allowed


def test_flat_workflow_modules_import():
    for module_name in (
        "workflows.config",
        "workflows.hooks",
        "workflows.prompts",
        "workflows.workflow",
        "workflows.registry",
        "workflows.config_snapshot",
        "workflows.config_watcher",
        "workflows.paths",
        "workflows.stall",
    ):
        module = importlib.import_module(module_name)
        assert module.__file__ is not None
        assert "/daedalus/workflows/" in module.__file__.replace("\\", "/")


def test_bundled_workflows_expose_standard_workflow_object():
    for module_name, workflow_name in (
        ("workflows.issue_runner", "issue-runner"),
        ("workflows.change_delivery", "change-delivery"),
    ):
        module = importlib.import_module(module_name)
        workflow = module.WORKFLOW

        assert workflow.name == workflow_name
        assert module.NAME == workflow.name
        assert module.SUPPORTED_SCHEMA_VERSIONS == workflow.schema_versions
        assert module.CONFIG_SCHEMA_PATH == workflow.schema_path
        assert callable(workflow.load_config)
        assert callable(workflow.make_workspace)
        assert callable(workflow.run_cli)
