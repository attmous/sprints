"""Repo-root workflow wrapper package for official Hermes plugin installs."""

from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_REAL_WORKFLOWS_DIR = _PLUGIN_ROOT / "daedalus" / "workflows"
_real_dir_str = str(_REAL_WORKFLOWS_DIR)
if _real_dir_str in __path__:
    __path__.remove(_real_dir_str)
__path__.insert(0, _real_dir_str)

_INIT = _REAL_WORKFLOWS_DIR / "__init__.py"
__file__ = str(_INIT)
exec(compile(_INIT.read_text(encoding="utf-8"), str(_INIT), "exec"), globals())
