# Bundled workflows

Daedalus ships more than one workflow. The engine, lease model, runtime
adapters, and `WORKFLOW.md` contract are shared; each workflow package defines
its own lifecycle, prompts, gates, and operator commands.

## At a glance

| Workflow | Use it when... | Default template | Managed path |
|---|---|---|---|
| [`change-delivery`](change-delivery.md) | you want the opinionated GitHub SDLC workflow: issue -> code -> review -> PR -> merge | [`docs/examples/change-delivery.workflow.md`](../examples/change-delivery.workflow.md) | yes — `bootstrap` + `service-up` |
| [`issue-runner`](issue-runner.md) | you want a generic tracker-driven workflow that selects issues, creates workspaces, runs hooks, and invokes one agent | [`docs/examples/issue-runner.workflow.md`](../examples/issue-runner.workflow.md) | yes — `bootstrap --workflow issue-runner` or explicit `scaffold-workflow` + `service-up` |

## The boundary

- Generic docs such as [architecture](../architecture.md), [public contract](../public-contract.md), [security](../security.md), and the engine-level concept docs describe Daedalus itself.
- Workflow docs describe the lifecycle and contract details that belong to one workflow package.
- If a doc is mostly about GitHub review gates, PR publish/merge stages, or reviewer roles, it belongs to `change-delivery`, not to the generic engine story.
