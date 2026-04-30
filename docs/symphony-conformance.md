# Symphony Conformance

This note tracks Daedalus against the public `openai/symphony` draft spec as reviewed on **April 30, 2026**.

The short version: Daedalus is already **Symphony-aligned** in architecture, but only **partially Symphony-compatible** at the contract and integration boundaries.

## Positioning

- Daedalus is a long-running workflow orchestrator with durable state, hot reload, isolated lane worktrees, recovery, and operator observability.
- Daedalus is still **GitHub-first** in its managed/default workflow. The current Symphony draft is still **Linear-first**.
- Daedalus now uses a Symphony-style `WORKFLOW.md` as the native public contract for bundled workflows. `issue-runner` is the closer generic reference surface; `change-delivery` remains the richer GitHub SDLC workflow.

## Status Matrix

| Symphony concept | Daedalus status | Notes |
|---|---|---|
| `WORKFLOW.md` loader | Partial | Supported as a repo-owned public contract. Front matter maps to the selected workflow schema; `issue-runner` is the closer generic reference surface, while `change-delivery` still carries richer GitHub-specific semantics. |
| Typed config + hot reload | Implemented | Current `change-delivery` schema is validated and hot-reloaded with last-known-good behavior. |
| Issue tracker client boundary | Partial | `issue-runner` now has a tracker client boundary with `local-json` and first-pass `linear` adapters, but the broader engine is still not tracker-agnostic end-to-end. |
| Workspace manager | Partial | Generic workspace root, lifecycle hooks, terminal cleanup, managed long-running `issue-runner`, and persisted scheduler state now exist, but the scheduler policy is not yet fully spec-shaped. |
| Bounded concurrency | Partial | `issue-runner` now dispatches bounded batches and persists running-worker recovery, but the broader engine is still not uniformly scheduler-driven. |
| Retry/backoff policy | Partial | Durable retry/backoff state now survives scheduler restarts, but the policy is still not exposed as a clean spec-native contract. |
| Coding-agent protocol | Partial | CLI/session runtimes still exist, but `issue-runner` now ships a first-pass `codex-app-server` adapter. It is not yet a full spec-native session protocol. |
| Observability surface | Partial | Events, status, watch, and HTTP surfaces exist; `issue-runner` now records per-run token and rate-limit metrics, but broader operator surfaces still do not report them uniformly. |
| Trust/safety posture | Implemented | See [security.md](security.md). |
| Terminal workspace cleanup | Partial | Terminal lane states exist; full Symphony-style cleanup semantics still need explicit policy. |

## Important Differences

Daedalus currently differs from the Symphony draft in three material ways:

1. The supported managed workflow is GitHub-backed `change-delivery`; `issue-runner` is the generic reference workflow and now has a first-pass Linear adapter, but the broader product story is still not Linear-first.
2. Runtime adapters are still mixed: `issue-runner` now has a first-pass Codex app-server path, while the rest of Daedalus remains CLI/session-oriented.
3. `WORKFLOW.md` still maps into the current Daedalus schema rather than a tracker-agnostic Symphony config model.

## Recommended Next Gaps

1. Promote the current tracker boundary into a fuller, repo-documented contract and harden the Linear adapter.
2. Promote concurrency and retry policy into a fuller public scheduler contract.
3. Promote the current Codex app-server path into a fuller spec-native protocol implementation.

Until those land, Daedalus should be described as **Symphony-inspired and partially compatible**, not as a strict implementation of the current spec.
