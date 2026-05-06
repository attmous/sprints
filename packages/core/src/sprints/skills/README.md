# Sprints Skills

Bundled Sprints skills are project-agnostic mechanics for actor work. Workflow
policy stays in `WORKFLOW.md`; skills only describe repeatable execution steps.

## Bundled Skills

```text
skills/
|-- pull/      # sync branch with origin/main
|-- debug/     # diagnose blocked or failing actor work
|-- commit/    # commit verified lane changes
|-- push/      # push branch and create/update PR
|-- review/    # review one lane PR and return required fixes
`-- land/      # PR landing support
```

The default `code` coder uses `pull`, `debug`, `commit`, `push`, and `land`.
The `push` skill owns pull request creation or update. The `land` skill owns the
merge loop when the lane reaches the `merge` step.
