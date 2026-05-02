"""Repo-root workflow-contract wrapper for official Hermes plugin installs."""

from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_REAL_MODULE = _PLUGIN_ROOT / "daedalus" / "workflows" / "contract.py"
__file__ = str(_REAL_MODULE)
exec(compile(_REAL_MODULE.read_text(encoding="utf-8"), str(_REAL_MODULE), "exec"), globals())
