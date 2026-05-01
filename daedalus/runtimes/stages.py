from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import PromptRunResult


@dataclass(frozen=True)
class RuntimeStageResult:
    output: str
    prompt_path: Path | None
    command_argv: list[str] | None
    runtime_result: Any
    session_handle: Any

    @property
    def used_command(self) -> bool:
        return self.command_argv is not None


def command_output_result(output: str) -> PromptRunResult:
    return PromptRunResult(
        output=output,
        tokens={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        rate_limits=None,
    )


def prompt_result_from_stage(result: RuntimeStageResult) -> PromptRunResult:
    runtime_result = result.runtime_result
    if isinstance(runtime_result, PromptRunResult):
        return runtime_result
    if all(hasattr(runtime_result, name) for name in ("output", "tokens", "rate_limits")):
        return runtime_result
    return command_output_result(result.output)


def raw_output_from_runtime_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    output = getattr(result, "output", None)
    if output is not None:
        return str(output)
    stdout = getattr(result, "stdout", None)
    if stdout is not None:
        return str(stdout)
    return str(result or "")


def resolve_stage_command(*, agent_cfg: dict[str, Any], runtime_cfg: dict[str, Any]) -> list[str] | None:
    command = agent_cfg.get("command")
    if command:
        return _ensure_argv(command)

    command = runtime_cfg.get("command")
    if not command:
        return None

    # For codex-app-server, runtime.command starts/connects the app-server
    # transport. It is not a per-stage agent command.
    if str(runtime_cfg.get("kind") or "") == "codex-app-server":
        return None
    return _ensure_argv(command)


def materialize_prompt(*, worktree: Path, stage_name: str, prompt: str, prompt_path: Path | None = None) -> Path:
    if prompt_path is None:
        out_dir = Path(worktree) / ".daedalus" / "dispatch"
        out_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        prompt_path = out_dir / f"{stage_name}-{digest}.txt"
    else:
        prompt_path = Path(prompt_path)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def substitute_command_placeholders(argv: list[str], values: dict[str, str]) -> list[str]:
    resolved = []
    for arg in argv:
        text = str(arg)
        for key, value in values.items():
            text = text.replace("{" + key + "}", value)
        resolved.append(text)
    return resolved


def run_runtime_stage(
    *,
    runtime: Any,
    runtime_cfg: dict[str, Any],
    agent_cfg: dict[str, Any],
    stage_name: str,
    worktree: Path,
    session_name: str,
    prompt: str,
    prompt_path: Path | None = None,
    env: dict[str, str] | None = None,
    placeholders: dict[str, str] | None = None,
    resume_session_id: str | None = None,
    cancel_event: Any | None = None,
    progress_callback: Callable[[Any], None] | None = None,
    on_session_ready: Callable[[Any], None] | None = None,
) -> RuntimeStageResult:
    """Run one workflow stage through a configured runtime profile.

    Workflows own policy, prompts, and state transitions. This helper owns the
    common runtime boundary: session setup, command overrides, prompt-file
    materialization, placeholder substitution, cancellation/progress hooks, and
    a normalized output/result shape.
    """
    worktree = Path(worktree)
    model = str(agent_cfg.get("model") or "")
    command = resolve_stage_command(agent_cfg=agent_cfg, runtime_cfg=runtime_cfg)
    set_cancel_event = getattr(runtime, "set_cancel_event", None)
    set_progress_callback = getattr(runtime, "set_progress_callback", None)
    if callable(set_cancel_event):
        set_cancel_event(cancel_event)
    if callable(set_progress_callback):
        set_progress_callback(progress_callback)

    session_handle = None
    try:
        ensure_session = getattr(runtime, "ensure_session", None)
        if callable(ensure_session):
            session_handle = ensure_session(
                worktree=worktree,
                session_name=session_name,
                model=model,
                resume_session_id=resume_session_id,
            )
        if on_session_ready is not None:
            on_session_ready(session_handle)

        if command is not None:
            resolved_prompt_path = materialize_prompt(
                worktree=worktree,
                stage_name=stage_name,
                prompt=prompt,
                prompt_path=prompt_path,
            )
            argv = substitute_command_placeholders(
                command,
                {
                    "model": model,
                    "prompt": prompt,
                    "prompt_path": str(resolved_prompt_path),
                    "worktree": str(worktree),
                    "session_name": session_name,
                    **(placeholders or {}),
                },
            )
            output = raw_output_from_runtime_result(
                runtime.run_command(worktree=worktree, command_argv=argv, env=env)
            )
            return RuntimeStageResult(
                output=output,
                prompt_path=resolved_prompt_path,
                command_argv=argv,
                runtime_result=command_output_result(output),
                session_handle=session_handle,
            )

        runner = getattr(runtime, "run_prompt_result", None)
        if callable(runner):
            runtime_result = runner(
                worktree=worktree,
                session_name=session_name,
                prompt=prompt,
                model=model,
            )
        else:
            runtime_result = runtime.run_prompt(
                worktree=worktree,
                session_name=session_name,
                prompt=prompt,
                model=model,
            )
        output = raw_output_from_runtime_result(runtime_result)
        return RuntimeStageResult(
            output=output,
            prompt_path=prompt_path,
            command_argv=None,
            runtime_result=runtime_result,
            session_handle=session_handle,
        )
    finally:
        if callable(set_progress_callback):
            set_progress_callback(None)
        if callable(set_cancel_event):
            set_cancel_event(None)


def _ensure_argv(command: Any) -> list[str]:
    if not isinstance(command, list) or not command:
        raise RuntimeError("agent.command and runtime command must be a non-empty argv list")
    return [str(part) for part in command]
