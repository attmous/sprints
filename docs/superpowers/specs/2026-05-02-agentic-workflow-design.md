# Agentic Workflow Design

## Goal

Replace the hardcoded `issue_runner` and `change_delivery` workflow implementations with one generic agent-orchestrated workflow. `WORKFLOW.md` becomes the workflow policy source of truth. Python keeps mechanics only: loading config, rendering prompts, calling runtimes, validating structured output, executing declared actions, and persisting state.

## Problem

The current workflow packages encode too much production policy in Python:

- `change_delivery/workflow.py` owns next-action decisions.
- `change_delivery/actions.py` owns publish/push/merge/dispatch branching.
- `change_delivery/reviews.py` owns review verdict policy and repair handoff rules.
- `change_delivery/status.py` owns workflow state normalization.
- `change_delivery/workspace.py` owns adapter shims, defaults, and fallback behavior.
- `issue_runner/orchestrator.py` and `issue_runner/workspace.py` duplicate dispatch mechanics.

This makes production behavior brittle because changing workflow intent requires code changes. The operator should instead describe the workflow in `WORKFLOW.md`, and the orchestrator agent should decide how to advance from current state.

## New Package

Create a clean workflow package:

```text
daedalus/workflows/agentic/
  __init__.py
  schema.yaml
  config.py
  contract.py
  orchestrator.py
  stages.py
  gates.py
  actors.py
  actions.py
  prompts.py
  state.py
  cli.py
```

Workflow name:

```yaml
workflow: agentic
```

The legacy workflows remain until parity is proven:

```text
daedalus/workflows/issue_runner/      # legacy
daedalus/workflows/change_delivery/   # legacy
```

After both are represented as `agentic` templates and tests pass, delete the legacy folders.

## Core Model

The new workflow has only these domain concepts:

- **Orchestrator**: an authoritative agent that decides workflow transitions.
- **Stage**: a configured workflow step.
- **Gate**: a condition the orchestrator evaluates before advancing.
- **Actor**: an agent that performs work for a stage.
- **Action**: a deterministic side effect that code can execute when requested.

Minimum workflow:

```text
entry -> stage -> gate
              |-> actor
              |-> action
```

Long workflow:

```text
entry -> stage -> gate -> stage -> gate -> ...
              |-> actor
              |-> action
```

Stages are declarative containers. Code should not hardcode what an "implementation", "review", "publish", or "merge" stage means. The orchestrator policy defines that.

## WORKFLOW.md Shape

`WORKFLOW.md` has three logical chunks.

### A. Front Matter Config

YAML front matter defines mechanical bindings:

```yaml
---
workflow: agentic
schema-version: 1

instance:
  name: your-org-your-repo-agentic
  engine-owner: hermes

repository:
  local-path: /home/you/src/repo
  slug: your-org/your-repo

orchestrator:
  actor: orchestrator

runtimes:
  codex-app-server:
    kind: codex-app-server
    mode: external
    endpoint: ws://127.0.0.1:4500

actors:
  orchestrator:
    runtime: codex-app-server
    model: gpt-5.4

  implementer:
    runtime: codex-app-server
    model: gpt-5.4

stages:
  implement:
    actors: [implementer]
    actions: [command.validate]
    gates: [implementation-complete]
    next: done

gates:
  implementation-complete:
    type: orchestrator-evaluated

actions:
  command.validate:
    type: command
    command: ["pytest", "tests/focused"]

storage:
  state: memory/workflow-state.json
  audit-log: memory/workflow-audit.jsonl
---
```

Front matter config defines what exists and how to call it. It does not define Python decision trees.

### B. Orchestrator Policy

The Markdown body contains a required orchestrator section:

```markdown
# Orchestrator Policy

You decide the next workflow transition from:

- the current durable workflow state;
- the current stage;
- stage outputs;
- gate definitions;
- action results;
- actor outputs;
- tracker and repository state;
- this policy.

Return JSON only:

{
  "decision": "advance|retry|run_actor|run_action|operator_attention|complete",
  "stage": "implement",
  "target": "implementer",
  "reason": "why this is the next valid step",
  "inputs": {},
  "operator_message": null
}
```

The orchestrator is an actor with authority. It is configured by runtime like any other actor, but only the orchestrator may decide transitions.

### C. Actor Policies

Each actor gets a named policy section:

```markdown
# Actor: implementer

## Input

Issue: {{ issue.identifier }} - {{ issue.title }}

State: {{ issue.state }}
Labels: {{ issue.labels }}
Priority: {{ issue.priority }}
Branch: {{ issue.branch_name }}
URL: {{ issue.url }}
Attempt: {{ attempt }}

Description:
{{ issue.description }}

## Policy

Make the smallest correct code change for the current stage. Keep the output
grounded in files changed and validation run.

## Output

Return JSON only:

{
  "status": "done|blocked|needs_retry",
  "summary": "what changed",
  "artifacts": [],
  "validation": [],
  "next_recommendation": "what the orchestrator should consider next"
}
```

Actor output is handed back to the orchestrator. Actors do not decide workflow transitions unless they are the orchestrator.

## Runtime Model

All agents are runtime-bound actors:

```yaml
actors:
  orchestrator:
    runtime: codex-app-server
    model: gpt-5.4

  implementer:
    runtime: codex-app-server
    model: gpt-5.4

  reviewer:
    runtime: hermes-final
    model: gpt-5.5
```

The orchestrator and actors can share one runtime or use different runtimes. Workflow code should only require a runtime profile that can run a prompt and return output.

## Data Flow

One tick:

1. Load `WORKFLOW.md`.
2. Load durable workflow state from engine-backed storage.
3. Gather current external facts needed by declared actions and integrations.
4. Render the orchestrator prompt with policy, config, durable state, recent events, and available actions.
5. Run the orchestrator actor.
6. Validate orchestrator JSON output.
7. Execute the requested mechanical step:
   - run an actor;
   - run an action;
   - advance stage;
   - retry;
   - complete;
   - raise operator attention.
8. Persist state, outputs, action results, and audit events.

Actor run:

1. Render the actor's policy and input template.
2. Run the actor through its configured runtime.
3. Validate actor JSON output.
4. Persist output.
5. Return output to durable state for the orchestrator's next decision.

## Engine Boundary

Engine owns mechanics only:

- runs;
- events;
- leases;
- retries;
- durable state;
- database writes;
- work item state.

Engine must not know workflow policy:

- no publish/merge decisions;
- no review verdict semantics;
- no actor selection policy;
- no stage transition policy;
- no special knowledge of `issue-runner`, `change-delivery`, or `agentic`.

## Code Boundary

The `agentic` workflow package owns reusable mechanics around agents:

- parse `WORKFLOW.md`;
- validate front matter schema;
- parse policy chunks;
- render orchestrator and actor prompts;
- call runtimes;
- validate JSON output;
- persist workflow state;
- execute declared actions;
- report malformed output;
- retry according to orchestrator decisions.

It must not own production workflow policy. If policy changes, the operator edits `WORKFLOW.md`.

## Actions

Actions are deterministic mechanical tools declared in config and invoked by orchestrator decision:

```yaml
actions:
  pr.publish:
    type: code-host.pr.publish

  pr.merge:
    type: code-host.pr.merge

  command.validate:
    type: command
    command: ["pytest", "tests/focused"]
```

Code validates that:

- the action exists;
- action input is structurally valid;
- required integrations are configured;
- execution succeeds or fails with a typed result.

Code does not decide whether the action is appropriate. That decision belongs to the orchestrator policy.

## Gates

Gates are configured evaluation points. The first implementation should support orchestrator-evaluated gates:

```yaml
gates:
  implementation-complete:
    type: orchestrator-evaluated
```

The orchestrator sees the gate definition and decides whether to advance, retry, run another actor, run an action, or raise operator attention.

Later, deterministic gate helpers can exist as action-like facts, but they should produce evidence rather than policy decisions.

## Durable State

The workflow state must be small and generic:

```json
{
  "workflow": "agentic",
  "current_stage": "implement",
  "status": "running",
  "attempt": 2,
  "stage_outputs": {},
  "actor_outputs": {},
  "action_results": {},
  "orchestrator_decisions": [],
  "operator_attention": null
}
```

State stores facts and decisions. It should not encode legacy-specific fields like `reviewLoopState`, `publishReady`, or `activeLane` unless a template defines them as generic state data.

## Error Handling

Malformed orchestrator output:

- persist the raw output;
- record a validation failure;
- retry according to runtime retry settings;
- raise operator attention after retry budget is exhausted.

Unknown stage, actor, action, or gate:

- reject the decision as invalid;
- record structured error;
- ask orchestrator to repair the decision if retry budget remains;
- otherwise raise operator attention.

Action failure:

- persist typed failure result;
- return the failure as evidence to orchestrator on the next tick.

Runtime failure:

- persist runtime error;
- retry according to config;
- raise operator attention if exhausted.

## Migration

Migration happens in stages:

1. Add `agentic/` package with schema, config model, and policy chunk parser.
2. Add durable generic state model.
3. Add orchestrator prompt and decision JSON schema.
4. Add actor prompt rendering and actor output JSON schema.
5. Add stage/gate/action execution loop.
6. Add basic actions: `noop`, `command`, and `comment`.
7. Add integration actions: tracker update, PR publish, PR update, PR merge.
8. Port `issue-runner` into an `agentic` template.
9. Port `change-delivery` into an `agentic` template.
10. Run parity tests against both legacy templates.
11. Delete `issue_runner/` and `change_delivery/`.

Do not delete legacy workflows until the templates pass their replacement tests.

## Acceptance

The second wave is complete when:

- `workflow: agentic` can run a minimal `entry -> stage -> gate` workflow;
- orchestrator decisions come from `WORKFLOW.md` policy, not Python decision trees;
- actor policies and output shapes are parsed from `WORKFLOW.md`;
- stage/gate/action definitions are front matter config, not hardcoded Python;
- engine remains policy-free;
- `issue-runner` and `change-delivery` are represented as `agentic` templates;
- legacy folders are deleted only after parity tests pass.
