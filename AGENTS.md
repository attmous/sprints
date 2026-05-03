# AGENTS.md

Sprints is a Hermes-Agent plugin for durable supervised workflow execution.

## General

- Repo: `https://github.com/attmous/hermes-sprints`
- High-confidence answers only when fixing/triaging: verify source, tests, shipped/current behavior, and dependency contracts before deciding.
- Dependency-backed behavior: read upstream dependency docs/source/types first. Do not assume APIs, defaults, errors, timing, or runtime behavior.

## Package Boundaries

| Path | Owns |
| --- | --- |
| `sprints/cli/` | Hermes command surface and output rendering. |
| `sprints/workflows/` | Contract loading, typed config, lane reconciliation, runner ticks, daemon loop, prompt rendering, decision application. |
| `sprints/engine/` | SQLite schema, `EngineStore`, leases, events, runs, retries, runtime sessions, work projections, reports. |
| `sprints/runtimes/` | Backend-neutral turns plus runtime adapters. |
| `sprints/trackers/` | Tracker and code-host protocols plus GitHub/Linear implementations. |
| `sprints/skills/` | Actor skill docs injected into actor prompts. |
| `sprints/observe/` | Read-only operator views. |
| `docs/` | Operator and architecture docs. |

## Coding Style

- Keep changes direct.
- Prefer existing local patterns over new abstractions.
- Use typed config/dataclasses where config shape matters.
- Use structured parsers/APIs for structured data.
- Avoid legacy fallback paths unless explicitly required.
- Avoid one-file wrapper modules with only one import.
- Keep docs factual and operator-useful. No corporate filler.
- Do not add broad tests unless the operator asks. Use focused verification commands instead.

## Validation

- Use the narrowest useful checks for the change.
- Only run runtime execution checks when the required runtime is actually available.

## Git Hygiene

- Work from a clean branch or worktree.
- main: no merge commits; rebase on latest origin/main before push.
- branches: named with convention "feature/*" "bugfix/*"
- Commits: conventional-ish, concise, grouped.
- User says commit: your changes only. commit all: all changes in grouped chunks. push: may git pull --rebase first.
- Do not delete/rename unexpected files; ask if blocking, else ignore.
- No manual stash/autostash unless explicit. No branch/worktree changes unless requested.

## High-Value References

- [README.md](README.md): landing page and quick start.
- [docs/architecture.md](docs/architecture.md): full engineering mental model.
- [docs/operator/installation.md](docs/operator/installation.md): install and bootstrap.
- [docs/operator/workflow-daemon.md](docs/operator/workflow-daemon.md): daemon loop.
- [docs/workflows/workflow-contract.md](docs/workflows/workflow-contract.md): contract format.
- [sprints/workflows/README.md](sprints/workflows/README.md): workflow package layout.
- [sprints/engine/README.md](sprints/engine/README.md): engine state model.
