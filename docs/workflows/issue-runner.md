# `issue-runner` Template

`issue-runner` is a bundled agentic policy template for taking one issue-like
work item through inspection, implementation, and completion.

It is not a separate Python workflow package. It is a `WORKFLOW.md` starting
point that runs on the shared `workflow: agentic` engine.

## Template Path

```text
sprints/workflows/templates/issue-runner.md
```

## Shape

Stages:

- `intake`

Actors:

- `orchestrator`
- `implementer`

Gates:

- `issue-ready`

The orchestrator decides whether the implementer should run, whether the result
needs retry, whether the operator must intervene, or whether the issue is
complete.

## Use It When

- you want a small issue-oriented automation flow
- you do not need a separate review or release stage
- you want to define issue input and output shape in `WORKFLOW.md`

## Use

Copy the template into the repo-owned workflow contract and edit the policy for
your project:

```bash
cp sprints/workflows/templates/issue-runner.md WORKFLOW.md
$EDITOR WORKFLOW.md
hermes sprints validate
```
