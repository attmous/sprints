"""Repo-root workflow dispatcher wrapper for official Hermes plugin installs."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_ROOT_STR = str(_PLUGIN_ROOT)
if _PLUGIN_ROOT_STR not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT_STR)

from workflows import run_cli


def _resolve_workflow_root(argv: list[str]) -> tuple[Path, list[str]]:
    out: list[str] = []
    workflow_root: Path | None = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--workflow-root":
            if index + 1 >= len(argv):
                raise SystemExit("--workflow-root requires a path argument")
            workflow_root = Path(argv[index + 1]).expanduser().resolve()
            index += 2
            continue
        if arg.startswith("--workflow-root="):
            workflow_root = Path(arg.split("=", 1)[1]).expanduser().resolve()
            index += 1
            continue
        out.append(arg)
        index += 1

    if workflow_root is None:
        from workflows.shared.paths import resolve_default_workflow_root

        workflow_root = resolve_default_workflow_root(plugin_dir=_PLUGIN_ROOT)
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
    raise SystemExit(main())
