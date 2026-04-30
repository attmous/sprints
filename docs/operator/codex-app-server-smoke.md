# Codex app-server Smoke Tests

Daedalus has two Codex app-server confidence layers.

## CI Fake Harness

The default tests use a deterministic fake app-server. They do not require a
Codex install, model quota, or network access, and they can force protocol
events that are hard to reproduce with a real model.

```bash
pytest tests/test_runtimes_codex_app_server.py \
  tests/test_workflows_issue_runner_workspace.py \
  -k codex
```

This verifies JSON-RPC start/resume, WebSocket reuse, cancellation,
read/stall timeout behavior, token/rate-limit mapping, and workflow scheduler
thread persistence.

## Real Local Smoke

Run the real smoke only on a machine with a working `codex` CLI and app-server
auth. It starts a real `codex app-server` subprocess, sends a tiny prompt,
persists the returned thread id, then resumes the same thread for a second
tiny prompt.

```bash
DAEDALUS_REAL_CODEX_APP_SERVER=1 \
pytest tests/test_runtimes_codex_app_server.py \
  -k real_smoke_start_and_resume -q -s
```

Optional model override:

```bash
DAEDALUS_REAL_CODEX_MODEL=gpt-5.4-mini \
DAEDALUS_REAL_CODEX_APP_SERVER=1 \
pytest tests/test_runtimes_codex_app_server.py \
  -k real_smoke_start_and_resume -q -s
```

Keep this test opt-in. It depends on local Codex installation, account state,
quota, model availability, and live runtime timing. Use it before production
changes to Codex runtime/service behavior, not as a required CI gate.

## Token Accounting Rule

When Codex emits both `tokenUsage.last` and cumulative `tokenUsage.total`,
Daedalus records `last` as the per-turn delta for workflow totals. If only
`total` is available, Daedalus uses that value. This avoids double-counting
cumulative thread totals across resumed turns.
