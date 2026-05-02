from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_COMPATIBILITY_FILES = {
    "daedalus/integrations/trackers/__init__.py",
    "daedalus/integrations/trackers/types.py",
    "daedalus/integrations/trackers/registry.py",
    "daedalus/integrations/trackers/github.py",
    "daedalus/integrations/trackers/linear.py",
    "daedalus/integrations/trackers/local_json.py",
    "daedalus/integrations/trackers/feedback.py",
    "daedalus/integrations/code_hosts/__init__.py",
    "daedalus/integrations/code_hosts/types.py",
    "daedalus/integrations/code_hosts/registry.py",
    "daedalus/integrations/code_hosts/github.py",
    "daedalus/runtimes/types.py",
    "daedalus/runtimes/registry.py",
}


def test_internal_workflow_imports_use_new_restructure_namespaces():
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "daedalus").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED_COMPATIBILITY_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for old_import in (
            "from trackers",
            "from code_hosts",
            "from engine.driver",
            "from runtimes import",
            "from workflow_core",
            "from workflows.core",
            "from workflows.shared",
            "from workflows.change_delivery.runtimes",
            "from workflows.change_delivery.config_snapshot",
            "from workflows.change_delivery.stall",
        ):
            if old_import in text:
                offenders.append(f"{rel}: {old_import}")

    assert offenders == []

