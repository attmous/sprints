# Daedalus Restructure Implementation Plan

Status: implementation turns complete  
Branch: `codex/daedalus-restructure-implementation-plan`  
Worktree: `/tmp/daedalus-restructure-implementation-plan`  
Current turn: Turn 12 complete

This plan breaks the Daedalus restructure into small turns. Each turn should be
reviewable on its own, preserve public behavior, and leave the repository in a
passing state.

The target architecture is a durable workflow engine plus workflow SDK plus
bundled workflows:

- `engine/` owns durable orchestration primitives.
- `workflows/core/` owns shared workflow contract/config/hook/prompt/status
  helpers.
- `workflows/` owns workflow-specific policy.
- `runtimes/` owns agent/runtime protocols and adapters.
- `integrations/` owns trackers, code hosts, and notifications.
- `operator/` owns CLI, doctor, status, watch, HTTP, and service control.
- `platform/` owns host utilities such as paths, env, process, files, and time.

## Ground Rules

### Preserve Public Behavior

Do not break these surfaces unless there is a separate breaking-change plan:

- `WORKFLOW.md`
- `WORKFLOW-<workflow>.md`
- workflow root layout
- `/daedalus ...`
- `/workflow <name> ...`
- `hermes daedalus bootstrap`
- `hermes daedalus scaffold-workflow`
- `hermes daedalus validate`
- workflow names:
  - `issue-runner`
  - `change-delivery`
- documented status/doctor JSON fields
- root-level compatibility imports until packaging tests prove removal is safe

### Keep Moves Separate From Behavior

For each turn, choose one primary kind of change:

- add tests and guardrails;
- add a new shared module;
- migrate one narrow caller group;
- add compatibility shims;
- remove dead compatibility only after all callers are moved.

Avoid combining broad file moves with policy changes.

### Dependency Direction

Allowed direction:

```text
operator -> workflows -> workflows.core -> engine
workflows -> runtimes
workflows -> integrations
engine -> platform
runtimes -> platform
integrations -> platform
```

Forbidden direction:

```text
engine -> workflows
engine -> runtimes
engine -> integrations
runtimes -> workflows
integrations -> workflows
operator -> workflow internals when stable status/driver APIs exist
```

## Turn 0: Baseline Guardrails

Status: complete on 2026-05-02.

Objective: add tests and docs that protect the current public contract before
moving code.

Scope:

- no behavior changes;
- no file moves;
- no import rewrites beyond test-only imports.

Tasks:

1. Add public import smoke tests for:
   - `engine`
   - `workflows`
   - `runtimes`
   - `trackers`
   - `daedalus.engine`
   - `daedalus.workflows`
   - `daedalus.runtimes`
   - `daedalus.trackers`
2. Add workflow discovery tests:
   - bundled workflows list includes `issue-runner`;
   - bundled workflows list includes `change-delivery`;
   - workflow CLI dispatch still resolves both names.
3. Add contract loader tests:
   - `WORKFLOW.md`;
   - `WORKFLOW-issue-runner.md`;
   - workflow-root pointer;
   - Markdown body preserved as `prompt_template`;
   - body projected as `workflow-policy`.
4. Add a short architecture note to `docs/public-contract.md` or a new
   `docs/restructure-notes.md` saying source of truth remains under
   `daedalus/`, while root-level packages are compatibility shims.

Suggested tests:

```bash
pytest tests/test_workflow_contract_loader.py \
  tests/test_workflows_dispatcher.py \
  tests/test_public_cli_docs_drift.py
```

Acceptance criteria:

- new guardrail tests pass;
- existing relevant tests pass;
- no runtime behavior changes;
- no production imports are moved yet.

## Turn 1: Introduce `workflows/core/config.py`

Status: complete on 2026-05-02.

Objective: create shared config primitives without migrating workflow behavior
broadly.

New files:

```text
daedalus/workflows/core/__init__.py
daedalus/workflows/core/config.py
tests/test_workflows_core_config.py
```

Initial API:

- `ConfigError`
- `ConfigView`
- `get_value`
- `get_str`
- `get_int`
- `get_bool`
- `get_list`
- `get_mapping`
- `resolve_env_indirection`
- `resolve_path`
- `first_present`
- `require`

Rules:

- support dash/underscore aliases;
- never mutate the caller's raw config;
- path helpers must support relative-to-workflow-root resolution;
- env indirection should support `$NAME` and plain literal values;
- helper behavior must be unit tested before workflow adoption.

Acceptance criteria:

- helper tests cover defaults, missing values, wrong types, aliases, env values,
  and path normalization;
- no workflow behavior changes;
- no public config shape changes.

## Turn 2: Add `issue_runner/config.py`

Status: complete on 2026-05-02.

Objective: normalize `issue-runner` config in one place while keeping raw config
available.

New files:

```text
daedalus/workflows/issue_runner/config.py
tests/test_issue_runner_config.py
```

Typed config objects:

- `IssueRunnerConfig`
- `PollingConfig`
- `WorkspaceConfig`
- `StorageConfig`
- `AgentConfig`
- `TrackerRuntimeConfig`

Normalize:

- `polling.interval_ms`;
- `polling.interval_seconds` / `polling.interval-seconds`;
- `agent.max_concurrent_agents`;
- `agent.max_concurrent_agents_by_state`;
- `agent.max_retry_backoff_ms`;
- `workspace.root`;
- `storage.status`;
- `storage.health`;
- `storage.audit-log`;
- `storage.scheduler`;
- tracker state aliases:
  - `active_states` / `active-states`
  - `terminal_states` / `terminal-states`
  - `required_labels` / `required-labels`
  - `exclude_labels` / `exclude-labels`

First adoption points:

- scheduler state derivation;
- workspace/storage path resolution;
- retry backoff config.

Acceptance criteria:

- `issue-runner` status output remains compatible;
- hot reload still keeps last-known-good config on invalid reload;
- existing `issue-runner` tests pass;
- raw config remains available for schema validation and status/debug payloads.

## Turn 3: Extract Shared Prompt and Hook Utilities

Status: complete on 2026-05-02.

Objective: move generic prompt rendering and hook execution out of
`issue_runner/workspace.py`.

New files:

```text
daedalus/workflows/core/prompts.py
daedalus/workflows/core/hooks.py
tests/test_workflows_core_prompts.py
tests/test_workflows_core_hooks.py
```

Move or wrap:

- simple `{{ issue.field }}` prompt rendering;
- `attempt` substitution;
- unsupported control-block detection;
- hook timeout handling;
- hook result shape;
- common hook environment construction helpers where safe.

Keep workflow-local:

- issue-specific prompt variable policy;
- change-delivery actor prompt composition;
- lane memo/state prompt content.

Acceptance criteria:

- existing prompt rendering behavior is unchanged;
- existing hook result payloads are unchanged;
- `issue-runner` tests pass;
- no `change-delivery` prompt behavior changes in this turn.

## Turn 4: Create `integrations/trackers`

Status: complete on 2026-05-02.

Objective: introduce the target tracker namespace while preserving existing
imports.

New target layout:

```text
daedalus/integrations/__init__.py
daedalus/integrations/trackers/__init__.py
daedalus/integrations/trackers/types.py
daedalus/integrations/trackers/registry.py
daedalus/integrations/trackers/github.py
daedalus/integrations/trackers/linear.py
daedalus/integrations/trackers/local_json.py
daedalus/integrations/trackers/feedback.py
```

Migration approach:

1. Add new modules as wrappers/re-exports first.
2. Move implementation only after import tests cover old and new paths.
3. Keep `daedalus/trackers/*` as compatibility shims.
4. Keep root-level `trackers` package working.

Acceptance criteria:

- old imports work;
- new imports work;
- GitHub tracker tests pass;
- local-json tracker tests pass;
- Linear tests pass or remain explicitly marked experimental;
- no workflow config key changes.

## Turn 5: Create `integrations/code_hosts` and `integrations/notifications`

Status: complete on 2026-05-02.

Objective: separate external system adapters from workflow packages.

Target layout:

```text
daedalus/integrations/code_hosts/
  __init__.py
  types.py
  registry.py
  github.py

daedalus/integrations/notifications/
  __init__.py
  types.py
  webhooks.py
  slack.py
```

Migration approach:

- introduce wrappers first;
- move GitHub code-host behavior behind compatibility imports;
- move reusable webhook delivery logic out of `change_delivery/webhooks` only
  when tests pin payloads and retry behavior;
- keep change-delivery-specific subscriber policy workflow-local.

Acceptance criteria:

- `change-delivery` GitHub tests pass;
- webhook tests pass;
- old `daedalus/code_hosts` imports still work;
- webhook payload shapes are unchanged.

## Turn 6: Split Runtime Types and Registry

Status: complete on 2026-05-02.

Objective: make runtime API boundaries explicit without changing runtime
behavior.

Target files:

```text
daedalus/runtimes/types.py
daedalus/runtimes/registry.py
daedalus/runtimes/capabilities.py
daedalus/runtimes/stages.py
daedalus/runtimes/command.py
```

Migration approach:

- move protocol dataclasses to `types.py`;
- move register/build runtime logic to `registry.py`;
- leave `runtimes/__init__.py` as a compatibility export;
- keep concrete adapters in place;
- only extract command runtime behavior if tests cover it.

Acceptance criteria:

- runtime matrix tests pass;
- Codex app-server tests pass;
- workflow runtime binding tests pass;
- import compatibility tests pass.

## Turn 7: Engine Cleanup Without Schema Changes

Status: complete on 2026-05-02.

Objective: clarify engine internals while keeping `EngineStore` stable.

Possible target files:

```text
daedalus/engine/schema.py
daedalus/engine/runs.py
daedalus/engine/events.py
daedalus/engine/retries.py
```

Migration approach:

- keep `EngineStore` as the primary workflow-facing API;
- move implementation details only when tests already cover them;
- do not change database schema in this turn;
- do not change event payloads in this turn;
- keep `engine.state` compatibility imports until all callers move.

Acceptance criteria:

- engine primitive tests pass;
- DB migration tests pass;
- status server still reads runs/events/scheduler state;
- no schema migration is needed.

## Turn 8: Operator Namespace

Status: complete on 2026-05-02.

Objective: isolate human/operator surfaces from engine and workflow internals.

Target layout:

```text
daedalus/operator/
  __init__.py
  cli.py
  doctor.py
  formatters.py
  watch.py
  watch_sources.py
  http_server.py
  service.py
  systemd.py
```

Migration approach:

- keep `daedalus/daedalus_cli.py` as the public entrypoint until packaging says
  it can move;
- move formatter/watch/service helpers behind compatibility imports;
- prefer stable workflow driver/status APIs over direct workflow internals;
- update docs only after commands are verified.

Acceptance criteria:

- slash command tests pass;
- CLI dispatch tests pass;
- formatter tests pass;
- watch tests pass;
- docs drift tests pass.

## Turn 9: Add `change_delivery/config.py`

Status: complete on 2026-05-02.

Objective: normalize change-delivery config without flattening its rich policy
into the generic workflow model.

Typed config objects:

- `ChangeDeliveryConfig`
- `RepositoryConfig`
- `TrackerConfig`
- `CodeHostConfig`
- `RuntimeProfilesConfig`
- `ActorConfig`
- `StageConfig`
- `GateConfig`
- `StorageConfig`
- `WebhookConfig`

Adopt first in low-risk places:

- path resolution;
- runtime binding checks;
- actor lookup;
- storage paths;
- server config.

Keep workflow-local:

- lane state machine;
- review policy;
- gate policy;
- PR publish/merge policy;
- operator attention policy.

Acceptance criteria:

- change-delivery schema tests pass;
- status tests pass;
- action tests pass;
- review and repair handoff tests pass;
- no public workflow contract changes.

## Turn 10: Tighten Workflow Driver APIs

Status: complete on 2026-05-02.

Objective: make operator surfaces depend on stable workflow APIs rather than
workflow internals.

Target API:

```python
class WorkflowDriver(Protocol):
    def build_status(self) -> dict: ...
    def doctor(self) -> dict: ...
    def tick(self) -> dict: ...
```

Extend only when needed:

- `run_loop`;
- `serve`;
- `preflight`;
- `runtime_matrix`;
- `workflow_cli_argv`.

Tasks:

- define or move protocol to `workflows/core/types.py`;
- ensure both bundled workflows conform;
- update operator code to use protocol boundaries;
- add conformance tests for bundled workflows.

Acceptance criteria:

- operator commands work for both workflows;
- workflow-specific commands still route correctly;
- no operator code imports change-delivery internals for generic status paths.

## Turn 11: Move Source Files Gradually

Status: complete on 2026-05-02.

Objective: perform physical moves only after wrappers and tests are in place.

Rules:

- one namespace per PR/turn;
- move files with compatibility imports;
- update direct imports in the moved namespace only;
- run import smoke tests after each move;
- defer deletion of old files.

Recommended order:

1. `workflows/core`
2. `integrations/trackers`
3. `integrations/code_hosts`
4. `integrations/notifications`
5. `runtimes/types.py` and `runtimes/registry.py`
6. `operator`
7. optional engine internals

Acceptance criteria:

- old imports still work;
- new imports work;
- packaging tests pass;
- docs are updated only where public paths changed.

## Turn 12: Remove Dead Shims

Status: complete on 2026-05-02.

Objective: remove compatibility layers only when they are proven unused and not
part of the public contract.

Tasks:

- use `rg` to find old imports;
- update internal imports to new paths;
- keep public shims documented if external users may rely on them;
- remove private-only shims;
- update packaging manifests if needed.

Acceptance criteria:

- no internal imports use removed paths;
- public import smoke tests match the intended public surface;
- plugin packaging tests pass;
- docs mention remaining compatibility paths.

## Per-Turn Implementation Template

Use this template for each turn:

```markdown
## Turn N: <title>

Goal:
- <one sentence>

Files expected to change:
- <paths>

Behavior changes:
- none
- or explicitly list them

Compatibility:
- old import path:
- new import path:
- shim retained:

Tests to run:
- <pytest commands>

Acceptance:
- <checklist>

Rollback:
- <what to revert if this turn fails>
```

## Verification Matrix

Run narrowly during each turn:

```bash
pytest tests/test_workflow_contract_loader.py
pytest tests/test_workflows_dispatcher.py
pytest tests/test_engine_primitives.py
pytest tests/test_runtime_matrix.py
pytest tests/test_workflows_issue_runner_workspace.py
pytest tests/test_workflows_code_review_workflow.py
```

Run before merging a multi-turn branch:

```bash
pytest
```

For packaging-sensitive turns, also run:

```bash
pytest tests/test_pip_plugin_packaging.py \
  tests/test_official_plugin_layout.py \
  tests/test_public_cli_docs_drift.py
```

## First Branch Sequence

Recommended first implementation branches:

1. `codex/restructure-guardrails`
2. `codex/workflow-core-config`
3. `codex/issue-runner-typed-config`
4. `codex/workflow-core-hooks-prompts`
5. `codex/integrations-trackers-namespace`
6. `codex/runtime-types-registry`

Do not start with physical file moves. Start with guardrails and typed config.

## Definition of Done

The restructure is done when:

- `issue-runner` can be understood as the reference generic workflow without
  reading `change-delivery`;
- `change-delivery` remains rich but workflow-local;
- workflow config normalization lives in typed config modules;
- engine imports no workflow, runtime, tracker, code-host, or operator modules;
- runtime adapters import no workflow modules;
- integrations import no workflow modules;
- operator surfaces use stable workflow/engine APIs;
- root-level compatibility packages are either removed safely or explicitly
  documented as public shims;
- public docs, examples, workflow templates, and CLI behavior agree.
