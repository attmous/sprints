from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from . import PromptRunResult, SessionHandle, SessionHealth, register


class CodexAppServerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        result: PromptRunResult | None = None,
        stderr: str | None = None,
        returncode: int | None = None,
    ):
        super().__init__(message)
        self.result = result
        self.stderr = stderr
        self.returncode = returncode


@register("codex-app-server")
class CodexAppServerRuntime:
    def __init__(self, cfg: dict, *, run, run_json=None):
        del run, run_json
        self._cfg = cfg
        self._command = cfg.get("command") or "codex app-server"
        self._turn_timeout_ms = int(cfg.get("turn_timeout_ms") or 3600000)
        self._read_timeout_ms = int(cfg.get("read_timeout_ms") or 5000)
        self._stall_timeout_ms = int(cfg.get("stall_timeout_ms") or 300000)
        self._approval_policy = str(cfg.get("approval_policy") or "").strip() or None
        self._thread_sandbox = str(cfg.get("thread_sandbox") or "").strip() or None
        self._turn_sandbox_policy = str(cfg.get("turn_sandbox_policy") or "").strip() or None
        self._last_activity: float | None = None
        self._last_result: PromptRunResult | None = None

    def _record_activity(self) -> None:
        self._last_activity = time.monotonic()

    def last_activity_ts(self) -> float | None:
        return self._last_activity

    def last_result(self) -> PromptRunResult | None:
        return self._last_result

    def ensure_session(
        self,
        *,
        worktree: Path,
        session_name: str,
        model: str,
        resume_session_id: str | None = None,
    ) -> SessionHandle:
        del worktree, model, resume_session_id
        return SessionHandle(record_id=None, session_id=None, name=session_name)

    def run_prompt(
        self,
        *,
        worktree: Path,
        session_name: str,
        prompt: str,
        model: str,
    ) -> str:
        return self.run_prompt_result(
            worktree=worktree,
            session_name=session_name,
            prompt=prompt,
            model=model,
        ).output

    def run_prompt_result(
        self,
        *,
        worktree: Path,
        session_name: str,
        prompt: str,
        model: str,
    ) -> PromptRunResult:
        env = {
            "DAEDALUS_MODEL": model,
            "DAEDALUS_SESSION_NAME": session_name,
        }
        if self._approval_policy:
            env["DAEDALUS_APPROVAL_POLICY"] = self._approval_policy
        if self._thread_sandbox:
            env["DAEDALUS_THREAD_SANDBOX"] = self._thread_sandbox
        if self._turn_sandbox_policy:
            env["DAEDALUS_TURN_SANDBOX_POLICY"] = self._turn_sandbox_policy

        self._record_activity()
        argv = self._command_argv()
        proc = subprocess.Popen(
            argv,
            cwd=str(worktree),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, **env},
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        assert proc.stderr is not None
        try:
            stdout, stderr = proc.communicate(prompt, timeout=max(self._turn_timeout_ms / 1000, 1))
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            result = self._parse_event_stream(stdout, stderr=stderr)
            self._last_result = result
            raise CodexAppServerError(
                "codex-app-server turn timed out",
                result=result,
                stderr=stderr,
                returncode=None,
            )
        self._record_activity()
        result = self._parse_event_stream(stdout, stderr=stderr)
        self._last_result = result
        if proc.returncode != 0:
            raise CodexAppServerError(
                self._failure_detail(result=result, stderr=stderr, returncode=proc.returncode),
                result=result,
                stderr=stderr,
                returncode=proc.returncode,
            )
        return result

    def _command_argv(self) -> list[str]:
        if isinstance(self._command, list):
            argv = [str(part) for part in self._command if str(part).strip()]
        else:
            argv = shlex.split(str(self._command).strip())
        if not argv:
            raise RuntimeError("codex-app-server runtime requires a non-empty command")
        return argv

    def _parse_event_stream(self, stdout: str, *, stderr: str = "") -> PromptRunResult:
        session_id = None
        thread_id = None
        turn_id = None
        last_event = None
        last_message = None
        turn_count = 0
        rate_limits = None
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        output_parts: list[str] = []

        for source_name, stream_text in (("stdout", stdout), ("stderr", stderr)):
            for raw_line in stream_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    if source_name == "stdout":
                        output_parts.append(raw_line)
                    elif not last_message:
                        last_message = line
                    continue
                if not isinstance(payload, dict):
                    continue
                event_type = str(payload.get("event") or payload.get("type") or "").strip()
                if event_type:
                    last_event = event_type
                if event_type == "session_started":
                    session_id = str(payload.get("session_id") or payload.get("sessionId") or session_id or "") or session_id
                    thread_id = str(payload.get("thread_id") or payload.get("threadId") or thread_id or "") or thread_id
                elif event_type in {"turn_started", "turn_completed", "turn_failed", "turn_input_required"}:
                    turn_id = str(payload.get("turn_id") or payload.get("turnId") or turn_id or "") or turn_id
                    if event_type == "turn_started":
                        turn_count += 1
                if "message" in payload and isinstance(payload.get("message"), str):
                    last_message = payload["message"]
                elif "error" in payload and isinstance(payload.get("error"), str):
                    last_message = payload["error"]
                if "text" in payload and isinstance(payload.get("text"), str):
                    output_parts.append(payload["text"])
                if "output" in payload and isinstance(payload.get("output"), str):
                    output_parts.append(payload["output"])
                usage_payload = payload.get("usage") or payload.get("token_usage")
                if isinstance(usage_payload, dict):
                    usage = self._coerce_usage(usage_payload, current=usage)
                if isinstance(payload.get("rate_limits"), dict):
                    rate_limits = payload.get("rate_limits")
                elif isinstance(payload.get("rate_limits_snapshot"), dict):
                    rate_limits = payload.get("rate_limits_snapshot")
                elif isinstance(payload.get("rate_limit"), dict):
                    rate_limits = payload.get("rate_limit")

        return PromptRunResult(
            output="\n".join(part for part in output_parts if part).strip() + ("\n" if output_parts else ""),
            session_id=session_id,
            thread_id=thread_id,
            turn_id=turn_id,
            last_event=last_event,
            last_message=last_message,
            turn_count=turn_count,
            tokens=usage,
            rate_limits=rate_limits,
        )

    def _failure_detail(self, *, result: PromptRunResult, stderr: str, returncode: int) -> str:
        if result.last_message:
            return f"codex-app-server failed: {result.last_message}"
        stderr_text = stderr.strip()
        if stderr_text:
            return f"codex-app-server failed: {stderr_text}"
        if result.last_event:
            return f"codex-app-server failed during event {result.last_event!r}"
        return f"codex-app-server exited with code {returncode}"

    def _coerce_usage(self, payload: dict[str, Any], *, current: dict[str, int]) -> dict[str, int]:
        input_tokens = payload.get("input_tokens")
        if input_tokens is None:
            input_tokens = payload.get("inputTokens")
        if input_tokens is None:
            input_tokens = payload.get("prompt_tokens")
        if input_tokens is None:
            input_tokens = payload.get("promptTokens")

        output_tokens = payload.get("output_tokens")
        if output_tokens is None:
            output_tokens = payload.get("outputTokens")
        if output_tokens is None:
            output_tokens = payload.get("completion_tokens")
        if output_tokens is None:
            output_tokens = payload.get("completionTokens")

        total_tokens = payload.get("total_tokens")
        if total_tokens is None:
            total_tokens = payload.get("totalTokens")

        next_usage = dict(current)
        if input_tokens is not None:
            next_usage["input_tokens"] = int(input_tokens)
        if output_tokens is not None:
            next_usage["output_tokens"] = int(output_tokens)
        if total_tokens is not None:
            next_usage["total_tokens"] = int(total_tokens)
        else:
            next_usage["total_tokens"] = int(next_usage["input_tokens"]) + int(next_usage["output_tokens"])
        return next_usage

    def assess_health(
        self,
        session_meta: dict | None,
        *,
        worktree: Path | None,
        now_epoch: int | None = None,
    ) -> SessionHealth:
        del session_meta, worktree, now_epoch
        return SessionHealth(healthy=True, reason=None, last_used_at=None)

    def close_session(self, *, worktree: Path, session_name: str) -> None:
        del worktree, session_name
        return None

    def run_command(
        self,
        *,
        worktree: Path,
        command_argv: list[str],
        env: dict | None = None,
    ) -> str:
        completed = subprocess.run(
            command_argv,
            cwd=str(worktree),
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        self._record_activity()
        return completed.stdout or ""
