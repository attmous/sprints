"""Hook execution helpers shared by workflows."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .config import get_value


def build_hook_env(values: dict[str, Any]) -> dict[str, str]:
    """Return a subprocess environment overlay with stringified values."""

    return {str(key): str(value) for key, value in values.items()}


def run_shell_hook(
    *,
    hooks_config: dict[str, Any],
    hook_name: str,
    worktree: Path,
    env: dict[str, str],
    run: Callable[..., Any],
    ignore_failure: bool = False,
) -> dict[str, Any]:
    script = str(get_value(hooks_config, hook_name, hook_name.replace("_", "-")) or "").strip()
    if not script:
        return {"hook": hook_name, "ran": False}
    timeout_ms = int(get_value(hooks_config, "timeout_ms", "timeout-seconds", default=60000) or 60000)
    timeout = max(timeout_ms // 1000, 1)
    try:
        completed = run(["bash", "-lc", script], cwd=worktree, timeout=timeout, env=env)
    except Exception as exc:
        if not ignore_failure:
            raise
        return {
            "hook": hook_name,
            "ran": True,
            "returncode": None,
            "ignored_failure": True,
            "error": str(exc),
        }
    return {
        "hook": hook_name,
        "ran": True,
        "returncode": getattr(completed, "returncode", 0),
    }
