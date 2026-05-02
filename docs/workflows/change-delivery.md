# `change-delivery` Template

`change-delivery` is a bundled agentic policy template for issue-to-reviewed
change delivery.

It is not a separate Python workflow package. It is a `WORKFLOW.md` starting
point that runs on the shared `workflow: agentic` engine.

## Template Path

```text
sprints/workflows/templates/change-delivery.md
```

## Shape

Stages:

- `implement`
- `review`

Actors:

- `orchestrator`
- `implementer`
- `reviewer`

Gates:

- `implementation-ready`
- `review-ready`

The orchestrator decides when to run implementation, when to ask for review,
when to retry, when to complete, and when to raise operator attention.

## Use It When

- you want issue-to-change delivery with an explicit review stage
- you want implementation and review context split between actors
- you want the workflow policy to live in `WORKFLOW.md`, not Python

## Use

Copy the template into the repo-owned workflow contract and edit the policy for
your project:

```bash
cp sprints/workflows/templates/change-delivery.md WORKFLOW.md
$EDITOR WORKFLOW.md
hermes sprints validate
```
