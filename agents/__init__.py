"""Repo-root shared agents wrapper for official Hermes plugin installs."""

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_ROOT_STR = str(_PLUGIN_ROOT)
if _PLUGIN_ROOT_STR not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT_STR)

_REAL_DIR = _PLUGIN_ROOT / "daedalus" / "agents"
_real_dir_str = str(_REAL_DIR)
if _real_dir_str not in __path__:
    __path__.append(_real_dir_str)

from daedalus.agents import *  # noqa: F401,F403

