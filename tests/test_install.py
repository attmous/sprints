import importlib.util
from pathlib import Path


INSTALL_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install.py"


def load_install_module():
    spec = importlib.util.spec_from_file_location("hermes_relay_install", INSTALL_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_into_default_hermes_home_copies_plugin_tree(tmp_path):
    install = load_install_module()
    repo_root = Path(__file__).resolve().parents[1]
    hermes_home = tmp_path / ".hermes"

    result = install.install_plugin(repo_root=repo_root, hermes_home=hermes_home)

    plugin_dir = hermes_home / "plugins" / "hermes-relay"
    assert result == plugin_dir
    assert (plugin_dir / "plugin.yaml").exists()
    assert (plugin_dir / "runtime.py").exists()
    assert (plugin_dir / "alerts.py").exists()
    assert (plugin_dir / "workflows" / "code_review" / "status.py").exists()
    assert (plugin_dir / "projects" / "yoyopod_core" / "config" / "project.json").exists()
    assert (plugin_dir / "skills" / "operator" / "SKILL.md").exists()


def test_install_into_explicit_destination_uses_given_path(tmp_path):
    install = load_install_module()
    repo_root = Path(__file__).resolve().parents[1]
    target = tmp_path / "custom-plugins" / "hermes-relay"

    result = install.install_plugin(repo_root=repo_root, destination=target)

    assert result == target
    assert (target / "plugin.yaml").exists()
    assert (target / "tools.py").exists()
    assert (target / "workflows" / "code_review" / "workflow.py").exists()
    assert (target / "projects" / "yoyopod_core" / "workspace" / "README.md").exists()


def test_install_follows_symlink_destination_and_preserves_the_link(tmp_path):
    """Reinstall into a symlinked plugin path works and leaves the symlink intact.

    Matches the real-world setup where ``~/.hermes/plugins/hermes-relay`` is a
    symlink to ``~/.hermes/workflows/<project>/.hermes/plugins/hermes-relay``.
    Before this fix ``shutil.rmtree`` errored with ``OSError: Cannot call
    rmtree on a symbolic link``.
    """
    install = load_install_module()
    repo_root = Path(__file__).resolve().parents[1]
    real_plugin_dir = tmp_path / "workflow" / ".hermes" / "plugins" / "hermes-relay"
    real_plugin_dir.mkdir(parents=True)
    # Seed the real dir with a stale file that must be wiped by reinstall.
    (real_plugin_dir / "stale.txt").write_text("stale", encoding="utf-8")

    symlink_target = tmp_path / ".hermes" / "plugins" / "hermes-relay"
    symlink_target.parent.mkdir(parents=True)
    symlink_target.symlink_to(real_plugin_dir)

    result = install.install_plugin(repo_root=repo_root, destination=symlink_target)

    assert result == symlink_target
    assert symlink_target.is_symlink(), "reinstall must preserve the symlink"
    # The payload lives in the real directory, reachable via the symlink.
    assert (symlink_target / "plugin.yaml").exists()
    assert (real_plugin_dir / "plugin.yaml").exists()
    # Stale file is gone.
    assert not (real_plugin_dir / "stale.txt").exists()


def test_install_replaces_existing_regular_directory(tmp_path):
    """Reinstall over an existing (non-symlink) directory wipes and rebuilds it."""
    install = load_install_module()
    repo_root = Path(__file__).resolve().parents[1]
    target = tmp_path / "plugins" / "hermes-relay"
    target.mkdir(parents=True)
    (target / "stale.txt").write_text("stale", encoding="utf-8")

    install.install_plugin(repo_root=repo_root, destination=target)

    assert (target / "plugin.yaml").exists()
    assert not (target / "stale.txt").exists()
