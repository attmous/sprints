"""GitHub tracker adapter compatibility exports."""

from __future__ import annotations

import importlib
import sys

try:
    _MODULE = importlib.import_module("trackers.github")
except ModuleNotFoundError:
    _MODULE = importlib.import_module("daedalus.trackers.github")
    sys.modules["trackers.github"] = _MODULE

sys.modules["daedalus.trackers.github"] = _MODULE
globals().update(
    {
        name: value
        for name, value in _MODULE.__dict__.items()
        if not (name.startswith("__") and name.endswith("__"))
    }
)
