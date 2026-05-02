# Workflows

Sprints ships one workflow engine: `agentic`.

The bundled files under `sprints/workflows/templates/` are policy templates for
that engine. They are not separate Python workflow packages.

## Files

| File | Purpose |
| --- | --- |
| `sprints/workflows/workflow.template.md` | Minimal bootstrap contract. |
| `sprints/workflows/templates/issue-runner.md` | Issue-focused policy template. |
| `sprints/workflows/templates/change-delivery.md` | Implementation/review policy template. |
| `sprints/workflows/templates/release.md` | Release planning and verification template. |
| `sprints/workflows/templates/triage.md` | Incoming work triage template. |

## Contract

Use `WORKFLOW.md` in the target repo.

The file has YAML front matter for mechanics and Markdown sections for policy.
Read [workflow-contract.md](workflow-contract.md) for the exact shape.
