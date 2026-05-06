# Public Contract

Compatibility-sensitive surfaces for the current Sprints release.

## Stable

- `hermes plugins install attmous/sprints --enable`
- plugin entry point: `sprints`
- `hermes sprints init`
- `hermes sprints bootstrap`
- `hermes sprints scaffold-workflow`
- `hermes sprints validate`
- `hermes sprints doctor`
- `hermes sprints doctor --fix`
- `hermes sprints configure-runtime`
- `hermes sprints runtime-matrix`
- `hermes sprints daemon ...`
- `hermes sprints codex-app-server ...`
- `/sprints ...`
- `/workflow code ...`
- repo contract: `WORKFLOW.md`
- named repo contracts: `WORKFLOW-<name>.md`
- repo pointer: `./.hermes/sprints/workflow-root`
- workflow root shape: `~/.hermes/workflows/<owner>-<repo>-code`

## Contract Format

Public workflow contracts use:

```yaml
workflow: code
schema-version: 1
```

Supported bundled workflow names are `code`, `change-delivery`, `release`, and
`triage`.

Policy templates may be named `code`, `change-delivery`, `release`, or
`triage`; the default generated contract is `code`. All bundled templates run
through the same Sprints workflow implementation.

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
