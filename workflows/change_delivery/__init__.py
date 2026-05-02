"""Repo-root change-delivery workflow wrapper for official Hermes plugin installs."""

from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
_REAL_WORKFLOW_DIR = _PLUGIN_ROOT / "daedalus" / "workflows" / "change_delivery"
_real_dir_str = str(_REAL_WORKFLOW_DIR)
if _real_dir_str in __path__:
    __path__.remove(_real_dir_str)
__path__.insert(0, _real_dir_str)

_INIT = _REAL_WORKFLOW_DIR / "__init__.py"
__file__ = str(_INIT)
exec(compile(_INIT.read_text(encoding="utf-8"), str(_INIT), "exec"), globals())
