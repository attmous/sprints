"""Repo-root engine wrapper package for local development."""

from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_REAL_ENGINE_DIR = _PLUGIN_ROOT / "daedalus" / "engine"
_real_dir_str = str(_REAL_ENGINE_DIR)
if _real_dir_str in __path__:
    __path__.remove(_real_dir_str)
__path__.insert(0, _real_dir_str)

_INIT = _REAL_ENGINE_DIR / "__init__.py"
__file__ = str(_INIT)
exec(compile(_INIT.read_text(encoding="utf-8"), str(_INIT), "exec"), globals())
