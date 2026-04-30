# `issue-runner`

`issue-runner` is the generic bundled workflow. It is intentionally smaller
than `change-delivery`: it selects an eligible issue, creates or reuses an
issue workspace, runs hooks, renders a prompt, and invokes one agent runtime.

## What it does

For each eligible tracker issue:

1. load the tracker feed
2. select the next eligible issue
3. create/reuse an isolated issue workspace
4. run lifecycle hooks
5. render the shared workflow policy + issue payload into a prompt
6. invoke the configured runtime/agent
7. persist output and audit state

## Use it when

- you want a generic tracker-driven automation loop
- you do not want built-in PR review/merge policy
- you want a starting point for a more Symphony-shaped workflow

## Default template

- Public example: [`docs/examples/issue-runner.workflow.md`](../examples/issue-runner.workflow.md)
- Bundled payload template: [`daedalus/workflows/issue_runner/workflow.template.md`](/home/radxa/WS/daedalus/daedalus/workflows/issue_runner/workflow.template.md)
- Sample tracker file: [`daedalus/workflows/issue_runner/issues.template.json`](/home/radxa/WS/daedalus/daedalus/workflows/issue_runner/issues.template.json)

## Key config blocks

- `tracker`: tracker kind, source path, active/terminal states, label filters
- `workspace`: per-issue workspace root
- `hooks`: `after-create`, `before-run`, `after-run`, `before-remove`
- `runtimes`: the runtime profiles available to the workflow
- `agent`: model/runtime/optional command override
- `retry`: continuation and backoff settings

## Current operator path

`issue-runner` is bundled and scaffoldable, but it is not yet part of the
managed `bootstrap` / `service-up` public path.

Use the explicit scaffold path:

```bash
hermes daedalus scaffold-workflow \
  --workflow issue-runner \
  --workflow-root ~/.hermes/workflows/<owner>-<repo>-issue-runner \
  --github-slug <owner>/<repo>
```

Then edit:

- `WORKFLOW.md`
- `config/issues.json` (or replace it with your own local-json tracker input)

Run it through the workflow CLI:

```bash
/workflow issue-runner status
/workflow issue-runner doctor
/workflow issue-runner tick
```

## Current limitation

The broader Daedalus runtime/service layer still assumes the richer
`change-delivery` status model. That is why `issue-runner` is bundled and
fully loadable through `/workflow ...`, but not yet wired into the default
managed daemon path.

## Related docs

- [Architecture](../architecture.md)
- [Runtimes](../concepts/runtimes.md)
- [Hot-reload](../concepts/hot-reload.md)
- [Symphony conformance](../symphony-conformance.md)
