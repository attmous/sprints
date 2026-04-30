"""Repo-root shared runtimes wrapper for official Hermes plugin installs."""

from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_REAL_DIR = _PLUGIN_ROOT / "daedalus" / "runtimes"

_real_dir_str = str(_REAL_DIR)
if _real_dir_str not in __path__:
    __path__.append(_real_dir_str)

_INIT = _REAL_DIR / "__init__.py"
exec(compile(_INIT.read_text(encoding="utf-8"), str(_INIT), "exec"), globals())
