# Slash Commands

Sprints exposes two Hermes command roots.

## `/sprints`

| Command | Purpose |
| --- | --- |
| `/sprints status` | Show workflow state and important paths. |
| `/sprints doctor` | Run config, state, runtime, and integration checks. |
| `/sprints doctor --fix` | Apply conservative local repairs and report each change. |
| `/sprints validate` | Validate the active `WORKFLOW.md`. |
| `/sprints runs` | Inspect durable engine runs. |
| `/sprints events` | Inspect durable engine events. |
| `/sprints watch` | Render the operator watch view. |
| `/sprints init` | Run the first-time setup wizard and write `WORKFLOW.md`. |
| `/sprints bootstrap` | Create workflow root and repo contract. |
| `/sprints scaffold-workflow` | Scaffold with explicit paths. |
| `/sprints configure-runtime` | Bind actors to runtime presets. |
| `/sprints runtime-matrix` | Show actor/runtime bindings. |

## `/sprints daemon`

| Command | Purpose |
| --- | --- |
| `run` | Run the workflow tick loop in the foreground. |
| `install` | Write the workflow daemon systemd user unit. |
| `up` | Install, enable, and start the workflow daemon. |
| `status` | Show unit and engine lease state. |
| `restart` | Restart the workflow daemon. |
| `logs` | Show recent logs. |
| `down` | Stop and disable the workflow daemon. |

## `/sprints codex-app-server`

| Command | Purpose |
| --- | --- |
| `install` | Write the systemd user unit. |
| `up` | Install, enable, and start the listener. |
| `status` | Show unit and readiness state. |
| `doctor` | Diagnose listener config and auth. |
| `restart` | Restart the listener. |
| `logs` | Show recent logs. |
| `down` | Stop and disable the listener. |

## `/workflow`

| Command | Purpose |
| --- | --- |
| `/workflow` | List installed workflows. |
| `/workflow code status` | Show code workflow state. |
| `/workflow code lanes` | List lane summaries. |
| `/workflow code lanes --attention` | List lanes blocked on operator attention. |
| `/workflow code lanes <lane-id>` | Show one full lane record. |
| `/workflow code retry <lane-id>` | Queue a retry after the operator fixed the blocker. |
| `/workflow code release <lane-id>` | Release a lane without completing it. |
| `/workflow code complete <lane-id>` | Mark a lane complete through the operator command. |
| `/workflow code validate` | Validate the contract. |
| `/workflow code tick` | Run one workflow tick. |

Most commands accept `--workflow-root <path>`. JSON-capable commands expose
`--json` or `--format json`.
