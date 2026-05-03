# Workflow Daemon

Use this after `WORKFLOW.md` validates and the actor runtime is available.

```bash
hermes sprints daemon up
hermes sprints daemon status
```

The daemon owns the workflow tick loop. It runs one tick immediately, then
sleeps based on lane state:

```text
active lanes: 15s
idle workflow: 60s
retry wake cap: 30s
error backoff: 60s
```

Foreground mode:

```bash
hermes sprints daemon run
```

Run one tick through the daemon path:

```bash
hermes sprints daemon run --once
```

Logs:

```bash
hermes sprints daemon logs --lines 100
```

Stop:

```bash
hermes sprints daemon down
```

The daemon takes an engine lease per workflow root. If another daemon owns the
lease, it sleeps instead of dispatching duplicate ticks.
