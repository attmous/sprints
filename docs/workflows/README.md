# Workflows

Sprints defaults to `code`.

The bundled file under `packages/core/src/sprints/workflows/templates/` is the
policy template. Bootstrap writes the `code` template by default.

## Files

| File | Purpose |
| --- | --- |
| `packages/core/src/sprints/workflows/templates/code.md` | Single-actor code delivery policy template. |

## Contract

Use `WORKFLOW.md` in the target repo.

The file has YAML front matter for mechanics and Markdown sections for policy.
Read [workflow-contract.md](workflow-contract.md) for the exact shape.
