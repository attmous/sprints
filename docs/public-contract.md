# Public Contract

Compatibility-sensitive surfaces for the current Sprints release.

## Stable

- `hermes plugins install attmous/sprints --enable`
- plugin entry point: `sprints`
- `hermes sprints bootstrap`
- `hermes sprints scaffold-workflow`
- `hermes sprints validate`
- `hermes sprints doctor`
- `hermes sprints configure-runtime`
- `hermes sprints runtime-matrix`
- `hermes sprints codex-app-server ...`
- `/sprints ...`
- `/workflow agentic ...`
- repo contract: `WORKFLOW.md`
- named repo contracts: `WORKFLOW-<name>.md`
- repo pointer: `./.hermes/sprints/workflow-root`
- workflow root shape: `~/.hermes/workflows/<owner>-<repo>-agentic`

## Contract Format

Public workflow contracts use:

```yaml
workflow: agentic
schema-version: 1
```

Policy templates may be named `issue-runner`, `change-delivery`, `release`, or
`triage`, but they still run on the same `agentic` engine.

## Internal

These may change without compatibility promises:

- SQLite table layout
- event payload internals
- generated JSON/JSONL projection shape
- internal Python module names
- bundled template wording
- private helper functions

Code should integrate through Hermes commands, `WORKFLOW.md`, or documented
runtime/tracker config.
