# Symphony vs Daedalus Component Audit

This audit compares the pasted OpenAI/Symphony system overview against the
current Daedalus implementation in this repository.

Summary: Daedalus is architecturally aligned with Symphony, but it is not a
strict Symphony realization yet. The closest compatibility target is the
generic `issue-runner` workflow. The `change-delivery` workflow is intentionally
richer and GitHub-first.

## Executive Summary

- `issue-runner` maps closely to the Symphony component model:
  workflow loader, tracker client, workspace manager, agent runner, polling
  orchestrator, status surface, and structured event/audit output.
- `change-delivery` extends beyond Symphony:
  lanes, actors, stages, gates, PR publish, internal/external review, merge
  promotion, code-host operations, shadow/active execution, and operator
  attention.
- Daedalus persists orchestration state in SQLite plus JSON/JSONL projections.
  Symphony's overview describes mainly in-memory runtime state plus logs.
- Daedalus is tracker-neutral in code, but GitHub is the supported production
  path today. Linear exists as an experimental adapter.

## Main Component Comparison

### Workflow Loader

Symphony reference:

- Reads `WORKFLOW.md`.
- Parses YAML front matter and prompt body.
- Returns `{config, prompt_template}`.

Daedalus realization:

- Supports `WORKFLOW.md`.
- Supports `WORKFLOW-<workflow>.md` for multiple workflows in one repo.
- Supports a workflow-root pointer at `config/workflow-contract-path`.
- Parses YAML front matter and Markdown body.
- Returns `WorkflowContract` with:
  - `source_path`
  - `config`
  - `prompt_template`
  - `front_matter`
- Also projects the Markdown body into `config["workflow-policy"]`.

Relevant code:

- `daedalus/workflows/contract.py`

Difference:

Daedalus is more flexible than the reference loader, but the projected
`workflow-policy` field means the body is not only returned as a prompt
template; it is also merged into the config model.

## Config Layer

Symphony reference:

- Exposes typed getters for workflow config values.
- Applies defaults.
- Resolves environment variable indirection.
- Performs validation before dispatch.

Daedalus realization:

- Uses workflow-specific JSON Schema validation.
- Uses workflow-specific preflight checks.
- Uses local helper getters such as `_cfg_value`.
- Resolves some environment indirection, for example:
  - Linear API key via `$LINEAR_API_KEY`
  - Codex WebSocket token env/file settings
- Does not yet have one central typed config facade for all config values.

Relevant code:

- `daedalus/workflows/validation.py`
- `daedalus/workflows/issue_runner/preflight.py`
- `daedalus/workflows/issue_runner/workspace.py`
- `daedalus/trackers/__init__.py`

Difference:

Daedalus validates strongly, but its config access is still distributed across
workflow modules instead of being one explicit typed getter layer.

## Issue Tracker Client

Symphony reference:

- Linear-first tracker in this specification version.
- Fetches active candidate issues.
- Refreshes specific issue IDs for reconciliation.
- Fetches terminal-state issues during startup cleanup.
- Normalizes tracker payloads into stable issue models.

Daedalus realization:

- Shared tracker protocol supports:
  - `github`
  - `local-json`
  - `linear`
- `issue-runner` uses this shared tracker boundary.
- GitHub is the first-class public production path.
- Linear exists, but is experimental/deferred.
- Normalized issue shape includes:
  - `id`
  - `identifier`
  - `title`
  - `description`
  - `priority`
  - `state`
  - `branch_name`
  - `url`
  - `labels`
  - `blocked_by`
  - timestamps

Relevant code:

- `daedalus/trackers/__init__.py`
- `daedalus/trackers/github.py`
- `daedalus/trackers/linear.py`
- `daedalus/trackers/local_json.py`
- `daedalus/workflows/issue_runner/tracker.py`

Difference:

Symphony is Linear-first. Daedalus is tracker-neutral in shape but GitHub-first
in supported production use.

## Orchestrator

Symphony reference:

- Owns the poll tick.
- Owns in-memory runtime state.
- Decides dispatch, retry, stop, and release behavior.
- Tracks session metrics and retry queue state.

Daedalus realization:

- `issue-runner` now has an explicit `IssueRunnerOrchestrator`.
- The orchestrator owns:
  - issue selection
  - retry priority
  - worker dispatch
  - worker reconciliation
  - terminal cancellation requests
  - run-loop behavior
- Runtime state is not only in memory.
- Scheduler state is persisted through `EngineStore` into SQLite.
- JSON scheduler files are generated operator projections.

Relevant code:

- `daedalus/workflows/issue_runner/orchestrator.py`
- `daedalus/workflows/issue_runner/workspace.py`
- `daedalus/engine/store.py`
- `daedalus/engine/scheduler.py`
- `daedalus/engine/lifecycle.py`

Difference:

Daedalus is more durable than the reference overview. It treats SQLite as the
source of truth for engine execution state instead of relying on in-memory
runtime state alone.

## Workspace Manager

Symphony reference:

- Maps issue identifiers to workspace paths.
- Ensures per-issue workspace directories exist.
- Runs workspace lifecycle hooks.
- Cleans workspaces for terminal issues.

Daedalus realization:

- `issue-runner` maps issue identifiers to sanitized workspace slugs.
- It enforces root containment checks before using workspace paths.
- It creates per-issue directories.
- It writes prompt/output under `.daedalus/`.
- It supports hooks:
  - `after_create`
  - `before_run`
  - `after_run`
  - `before_remove`
- It cleans terminal issue workspaces and suppresses retry state.

Relevant code:

- `daedalus/workflows/issue_runner/workspace.py`
- `daedalus/workflows/issue_runner/tracker.py`

Difference:

`issue-runner` matches the Symphony workspace manager closely. `change-delivery`
uses lane worktrees, lane state files, and lane memos instead of simple
per-issue workspaces.

## Agent Runner

Symphony reference:

- Creates workspace.
- Builds prompt from issue plus workflow template.
- Launches coding-agent app-server client.
- Streams agent updates back to the orchestrator.

Daedalus realization:

- `issue-runner` creates/reuses the workspace.
- It renders the Markdown body as the prompt template.
- It dispatches through a shared runtime stage boundary.
- Runtime backends include:
  - `codex-app-server`
  - `acpx-codex`
  - `claude-cli`
  - `hermes-agent`
  - command stages
- `codex-app-server` supports:
  - managed stdio mode
  - external WebSocket mode
  - thread resume
  - cooperative cancellation
  - token metrics
  - rate-limit metrics
  - structured turn events

Relevant code:

- `daedalus/runtimes/__init__.py`
- `daedalus/runtimes/stages.py`
- `daedalus/runtimes/codex_app_server.py`
- `daedalus/runtimes/capabilities.py`
- `daedalus/workflows/issue_runner/workspace.py`

Difference:

Symphony's overview centers on one coding-agent app-server executable. Daedalus
has a broader runtime abstraction. This is more flexible, but only
`codex-app-server` fully matches the structured app-server behavior.

## Status Surface

Symphony reference:

- Optional human-readable status surface.
- Could be terminal output, dashboard, or another operator-facing view.

Daedalus realization:

- CLI/slash status commands.
- `doctor` checks.
- Watch/TUI surfaces.
- Optional localhost HTTP server.
- Engine run history.
- Filterable event ledger.
- Per-work-item debug views.
- Status reads from SQLite plus JSON/JSONL projections.

Relevant docs/code:

- `docs/operator/http-status.md`
- `daedalus/workflows/change_delivery/server/`
- `daedalus/formatters.py`
- `daedalus/watch.py`
- `daedalus/watch_sources.py`

Difference:

Daedalus is stronger than the reference here. It has a larger operator control
surface and more durable observability.

## Logging

Symphony reference:

- Emits structured runtime logs to configured sinks.

Daedalus realization:

- Writes workflow audit JSONL.
- Writes Daedalus runtime event JSONL.
- Indexes events into SQLite best-effort.
- Exposes event retention controls.
- Supports webhook subscribers in `change-delivery`.
- Tracks runtime metrics such as tokens and rate limits where the runtime
  supports them.

Relevant code:

- `daedalus/engine/store.py`
- `daedalus/engine/audit.py`
- `daedalus/workflows/change_delivery/webhooks/`
- `daedalus/workflows/issue_runner/workspace.py`

Difference:

Daedalus logging is not only sink-based; it is also part of the durable engine
event model.

## Abstraction Layer Comparison

### Policy Layer

Symphony:

- `WORKFLOW.md` prompt body.
- Team rules for ticket handling, validation, and handoff.

Daedalus:

- `WORKFLOW.md` body is policy text.
- `issue-runner` uses it as the issue prompt template.
- `change-delivery` composes it into actor prompts and gate-specific behavior.

Difference:

Daedalus supports the same idea, but `change-delivery` has much more policy in
workflow code and schema, not only in the prompt body.

### Configuration Layer

Symphony:

- Typed getters.
- Defaults.
- Environment indirection.
- Path normalization.

Daedalus:

- Schema validation.
- Preflight checks.
- Local helper getters.
- Some environment indirection.
- Path normalization inside workspace/runtime loading.

Difference:

This is one of the clearest conformance gaps. Daedalus should centralize this
if strict Symphony compatibility is the goal.

### Coordination Layer

Symphony:

- Polling loop.
- Eligibility.
- Concurrency.
- Retries.
- Reconciliation.

Daedalus:

- `issue-runner` has this layer directly.
- Durable scheduler state is shared through engine primitives.
- `change-delivery` has a more complex lane/action orchestration model.

Difference:

Daedalus implements the layer, but it is split between generic engine primitives
and workflow-specific orchestration.

### Execution Layer

Symphony:

- Filesystem lifecycle.
- Workspace preparation.
- Coding-agent protocol.

Daedalus:

- Workspace lifecycle exists in `issue-runner`.
- Lane worktree lifecycle exists in `change-delivery`.
- Runtime dispatch is shared.
- Codex app-server is supported, but not the only runtime.

Difference:

Daedalus is broader and more plugin-like.

### Integration Layer

Symphony:

- Linear adapter.

Daedalus:

- GitHub adapter.
- Local JSON adapter.
- Experimental Linear adapter.
- Separate `code-host` abstraction for PR/review/merge in `change-delivery`.

Difference:

Daedalus splits tracker and code-host concerns. That is more suitable for
SDLC automation, but it diverges from the simpler Symphony overview.

### Observability Layer

Symphony:

- Logs and optional status surface.

Daedalus:

- Logs.
- Status.
- Doctor.
- Watch.
- HTTP API.
- SQLite runs/events.
- Runtime metrics.
- Tracker feedback.
- Webhooks.

Difference:

Daedalus is significantly more developed here.

## Workflow-Specific Notes

### `issue-runner`

Best match for Symphony.

It provides:

- Generic tracker-driven execution.
- Per-issue workspaces.
- Hooks.
- Prompt rendering from `WORKFLOW.md` body.
- One configured agent runtime.
- Retry/backoff.
- Running-worker recovery.
- Terminal-state cleanup.
- Optional tracker feedback.
- Optional HTTP status surface.

Remaining strict-conformance gaps:

- Public contract is still Daedalus-shaped, not purely Symphony-shaped.
- Runtime config uses `runtimes:` and `agent.runtime`, not a minimal Symphony
  `codex` app-server-only model.
- Config access is not centralized into a typed facade.
- GitHub is the hardened public tracker path; Linear is not the primary
  supported path.

### `change-delivery`

Opinionated SDLC workflow, not a strict Symphony port.

It adds:

- Active lane selection.
- Implementation actors.
- Internal review.
- External review.
- Repair handoff.
- PR publish/update.
- Maintainer approval gates.
- CI gates.
- Merge and promotion.
- Shadow/active execution controls.
- Operator attention state.
- Code-host integration.

This should be documented as a Daedalus extension rather than forced into the
generic Symphony component model.

## Material Differences to Track

1. Make `issue-runner` the strict Symphony compatibility target.
2. Move Daedalus-specific config under `daedalus:` where possible.
3. Add or formalize a typed config layer with consistent defaults, environment
   indirection, and path normalization.
4. Decide whether strict compatibility means Linear-first, or whether Daedalus
   will remain tracker-neutral with GitHub as the supported public path.
5. Keep `change-delivery` as an opinionated extension with clear docs instead
   of treating it as the reference Symphony realization.
6. Strengthen command-runtime cancellation if non-Codex runtimes are expected
   to behave like app-server runtimes.

## Bottom Line

Daedalus is a durable, production-oriented workflow engine inspired by the
Symphony component model. It already implements most of the important system
components, especially in `issue-runner`.

The main mismatch is shape and scope:

- Symphony describes a smaller Linear/app-server-centered reference workflow.
- Daedalus implements a broader durable orchestration system with multiple
  workflows, multiple runtime backends, durable SQLite state, GitHub-first
  production integration, and a richer SDLC workflow.

For release language, use:

> Daedalus is Symphony-inspired and partially compatible. `issue-runner` is the
> intended compatibility surface; `change-delivery` is an opinionated GitHub-first
> SDLC extension.
