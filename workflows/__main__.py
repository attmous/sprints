"""Plugin-level CLI entrypoint for the workflow dispatcher.

Invocation:

    python3 -m workflows --workflow-root <path> <subcommand> [args ...]

If ``--workflow-root`` is omitted, the entrypoint honors these env vars
(first match wins): ``DAEDALUS_WORKFLOW_ROOT``, ``YOYOPOD_WORKFLOW_ROOT``.
If neither is set, ``~/.hermes/workflows/yoyopod`` is used as a last-resort
default (matches the historical layout).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from workflows import run_cli


_WORKFLOW_ROOT_ENV_VARS = ("DAEDALUS_WORKFLOW_ROOT", "YOYOPOD_WORKFLOW_ROOT")


def _resolve_workflow_root(argv: list[str]) -> tuple[Path, list[str]]:
    """Peel --workflow-root / --workflow-root=<path> out of argv; env fallback."""
    out: list[str] = []
    workflow_root: Path | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--workflow-root":
            if i + 1 >= len(argv):
                raise SystemExit("--workflow-root requires a path argument")
            workflow_root = Path(argv[i + 1]).expanduser().resolve()
            i += 2
            continue
        if arg.startswith("--workflow-root="):
            workflow_root = Path(arg.split("=", 1)[1]).expanduser().resolve()
            i += 1
            continue
        out.append(arg)
        i += 1

    if workflow_root is None:
        for env_var in _WORKFLOW_ROOT_ENV_VARS:
            value = os.environ.get(env_var)
            if value:
                workflow_root = Path(value).expanduser().resolve()
                break
    if workflow_root is None:
        workflow_root = (Path.home() / ".hermes" / "workflows" / "yoyopod").resolve()
    return workflow_root, out


def main(argv: list[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    workflow_root, command_argv = _resolve_workflow_root(raw)
    try:
        return run_cli(workflow_root, command_argv)
    except subprocess.CalledProcessError as exc:
        msg = f"Command failed with exit status {exc.returncode}"
        if exc.stderr:
            msg += f"\n{exc.stderr.strip()}"
        print(msg, file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    sys.exit(main())
