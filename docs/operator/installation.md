# Sprints installation

This is the supported community install path for the first public release.
The managed path is the agentic workflow engine plus a repo-owned
`WORKFLOW.md` policy contract.

## Requirements

- Linux
- Hermes with plugin loading enabled
- `gh` authenticated for GitHub-backed workflows
- `python3` with `yaml` and `jsonschema` available
- `systemd --user` for supervised active/shadow mode
- the host CLIs required by the runtimes named in `WORKFLOW.md`

The bundled templates default runtime-backed stages to `codex-app-server`.
Start the shared listener with `hermes sprints codex-app-server up`, or edit
`WORKFLOW.md` / run `configure-runtime` if a stage should use Hermes Agent
instead.

Bundled policy templates live under `sprints/workflows/templates/` and are
copyable starting points for common operator flows.

## Bundled workflows

Sprints ships one workflow engine, `agentic`, and four policy templates:

- `issue-runner.md`
- `change-delivery.md`
- `release.md`
- `triage.md`

## Install the plugin

```bash
sudo apt install python3-yaml python3-jsonschema
hermes plugins install attmous/sprints --enable
```

The plugin source of truth is:

```text
~/.hermes/plugins/sprints
```

Sprints also ships a standard Hermes pip plugin entry point. If you install it
as a Python package instead of through `hermes plugins install`, Hermes will
discover it on the next startup and you must enable it explicitly:

```bash
python3 -m pip install .
hermes plugins enable sprints
```

## Bootstrap a workflow root

```bash
cd /path/to/your/repo
hermes sprints bootstrap
$EDITOR WORKFLOW.md
hermes sprints codex-app-server up
hermes sprints validate
hermes sprints status
```

This bootstraps an agentic workflow root and writes the repo-owned contract.
Replace `WORKFLOW.md` with one of the bundled policy templates if you want a
fuller workflow shape than the minimal bootstrap contract.

`bootstrap`:

- detects the git repo root from the current checkout
- derives `repo-slug` from `origin`
- creates the supported instance layout below
- writes or promotes the repo-owned workflow contract
- creates a dedicated bootstrap branch
- commits the workflow contract changes
- writes `./.hermes/sprints/workflow-root` in the repo checkout so later
  Sprints commands can resolve the workflow root automatically

```text
~/.hermes/workflows/<owner>-<repo>-<workflow-type>/
```

## Manual scaffold path

If you want explicit control over the target root or slug:

```bash
hermes sprints scaffold-workflow \
  --workflow-root ~/.hermes/workflows/your-org-your-repo-issue-runner \
  --repo-slug your-org/your-repo
```

That creates the same supported instance layout:

```text
~/.hermes/workflows/<owner>-<repo>-<workflow-type>/
```

Bundled policy templates live under `sprints/workflows/templates/`:

- `issue-runner.md`
- `change-delivery.md`
- `release.md`
- `triage.md`

Use one of those as the starting point for the repo-owned `WORKFLOW.md` when
you want a fuller policy than the minimal bootstrap contract.

The first workflow in a repo is written to:

```text
/path/to/repo/WORKFLOW.md
```

If the repo later carries multiple workflows, Sprints promotes the contracts
to:

```text
/path/to/repo/WORKFLOW-change-delivery.md
/path/to/repo/WORKFLOW-issue-runner.md
```

Promotion is fail-safe. If `WORKFLOW.md` exists but is not a Sprints contract,
bootstrap stops and leaves the file unchanged. If a target named contract
already exists, bootstrap also stops instead of overwriting user edits.

## Configure the workflow

Edit the path printed by `bootstrap` as `edit next`. For a repo with one
workflow this is usually:

```text
/path/to/repo/WORKFLOW.md
```

For a repo with multiple workflows, edit the workflow-specific file, for
example:

```text
/path/to/repo/WORKFLOW-issue-runner.md
```

At minimum, set:

- `repository.local-path`
- runtime kinds/models that exist on your host
- any gates, webhooks, or tracker-feedback settings your repo needs

The YAML front matter is the structured config. The Markdown body below it is
the workflow policy contract. `change-delivery` composes it into actor prompts;
`issue-runner` renders it as the issue prompt template.

The bundled workflow templates bind runtime-backed stages to
`codex-app-server` by default. Start the shared Codex listener with
`hermes sprints codex-app-server up`, or use `configure-runtime` to bind a
stage to Hermes Agent instead.

For common runtime choices, use the preset command instead of hand-editing the
runtime block:

```bash
# default issue-runner role
hermes sprints configure-runtime --runtime hermes-final --role agent

# change-delivery implementer actor backed by the shared Codex listener
hermes sprints configure-runtime --runtime codex-app-server --role implementer
```

`configure-runtime` edits the repo-owned `WORKFLOW.md` contract, writes the
runtime profile under `runtimes:`, and updates the selected role binding. It
does not start external services.

To inspect the resulting role-to-runtime matrix:

```bash
hermes sprints runtime-matrix
hermes sprints runtime-matrix --execute
```

Use `--execute` only after the referenced local CLIs or shared Codex service are
available. It runs a tiny runtime-stage prompt without touching trackers or code
hosts.

## Bring it up

```bash
hermes sprints validate
hermes sprints doctor
hermes sprints codex-app-server up
hermes sprints status
```

Run `validate` after editing `WORKFLOW.md`. It checks the contract file,
workflow schema, schema version, instance naming, repository path, service mode,
runtime role bindings, and workflow preflight rules. `doctor` adds host/runtime
readiness checks such as missing CLIs, unreachable Codex app-server, GitHub auth,
and workspace access. Both commands include `next steps` recommendations when
they find a problem.

If your workflow contract uses an external `codex-app-server` runtime, bring up
the shared Codex listener once:

```bash
hermes sprints codex-app-server up
```

Then point the workflow runtime at `ws://127.0.0.1:4500`.
Use `hermes sprints codex-app-server doctor` for the full operator check:
managed service state, readiness, auth posture, and persisted Codex thread
mappings. If the listener is not loopback-only, pass one of the supported auth
flags during `install` or `up`, for example `--ws-token-file
/absolute/path/to/token`. See [Codex app-server operations](codex-app-server.md)
for external-mode diagnostics and troubleshooting.

## Manual low-level path

If you want to inspect or script each step separately, the lower-level commands
remain available:

```bash
hermes sprints validate \
  --workflow-root ~/.hermes/workflows/your-org-your-repo-agentic

hermes sprints doctor \
  --workflow-root ~/.hermes/workflows/your-org-your-repo-agentic \
  --format json

hermes sprints codex-app-server install \
  --workflow-root ~/.hermes/workflows/your-org-your-repo-agentic

hermes sprints codex-app-server up \
  --workflow-root ~/.hermes/workflows/your-org-your-repo-agentic

hermes sprints codex-app-server status \
  --workflow-root ~/.hermes/workflows/your-org-your-repo-agentic
```

## Operate it from Hermes

```bash
cd /path/to/your/repo
hermes
```

Then use:

```text
/sprints status
/sprints doctor
/workflow agentic status
/workflow agentic validate
/workflow agentic tick
```

To validate the GitHub-backed tracker path against a disposable live issue, see
run `hermes sprints doctor` and inspect tracker diagnostics.

## Plugin state

Hermes plugins are opt-in. `hermes plugins install ... --enable` is the
supported path because it installs the repo and enables the plugin in one step.

If you install Sprints by some other method, enable it explicitly:

```bash
hermes plugins enable sprints
```

`HERMES_ENABLE_PROJECT_PLUGINS=true` is only for project-local plugins under
`./.hermes/plugins/`. It is not required for a global `~/.hermes/plugins/sprints`
install.

## Manage the plugin

```bash
hermes plugins list
hermes plugins update sprints
hermes plugins disable sprints
```

## Local-dev fallback

If you want to install straight from a local checkout instead of the Hermes
plugin manager:

```bash
git clone https://github.com/attmous/sprints.git
cd sprints
./scripts/install.sh
hermes plugins enable sprints
```
