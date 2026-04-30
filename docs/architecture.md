# Daedalus Architecture

<div align="center">

![Daedalus Architecture Diagram](assets/daedalus-architecture-diagram.png)

> **Daedalus is a durable orchestration runtime that wraps an SDLC workflow brain with leases, canonical state, action queues, role handoffs, retries, and operator tooling so agentic lanes can run continuously without turning into invisible cron-driven chaos.**

</div>

---

## The 30-Second Read

| Question | Answer |
|---|---|
| **What is it?** | A plugin that turns fragile cron-loop automation into explicit, durable 24/7 workflow orchestration. |
| **What problem does it solve?** | Agentic SDLC breaks because policy is buried in prompts, state is scattered, failures are logged but not modeled, and handoffs are implicit. |
| **How?** | Leases. SQLite canonical state. JSONL event history. Shadow/active execution. Workflow packages with explicit contracts. |
| **Who owns what?** | The **workflow package** decides *what* should happen. **Daedalus** decides *how* to orchestrate it durably. |

---

## The Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL TRIGGERS                                   │
│   Tracker Issue        Operator (/daedalus)    WORKFLOW.md (hot-reload)     │
└─────────────────────────────────────────────────────────────────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│     DAEDALUS ENGINE                  │  │    WORKFLOW PACKAGE                  │
│  ─────────────────────────────────   │  │  ─────────────────────────────────   │
│  Runtime Loop                        │  │  Status / Read Model                 │
│    Tick → Ingest → Derive → Dispatch │◄─┤  Policy Engine                       │
│    → Record                          │  │  Roles / Hooks / Gates               │
│                                      │  │  Workflow State Machine              │
│  Leases (heartbeat · TTL · recovery) │  │  Handoffs (explicit, durable)        │
│                                      │  │                                      │
│  SQLite ──► lanes · actions ·        │  │  Semantic Actions                    │
│             reviews · failures       │  │    select_issue                      │
│                                      │  │    render_prompt                     │
│  JSONL ───► turn_started ·           │  │    publish_ready_pr                  │
│             turn_completed · stall   │  │                                      │
│                                      │  │  ▼                                   │
│  Shadow Mode ──► observe · plan      │  │  Execution Actions                   │
│  Active Mode ──► execute · dispatch  │◄─┤    dispatch_turn                     │
│                                      │  │    publish_pr                        │
│  Operator Surfaces                   │  │    merge_pr                          │
│    /daedalus status · doctor · watch │  │    run_hooks                         │
│    shadow-report · active-gate       │  │                                      │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
         │                                           │
         ▼                                           ▼
┌────────────────────────────┐              ┌────────────────────────────┐
│  SUPERVISION               │              │  EXTERNAL                  │
│  systemd service           │              │  GitHub API                │
│  /daedalus watch (TUI)     │              │  Webhooks (Slack / HTTP)   │
│  HTTP status :8765         │              │  Comments (PR audit trail) │
└────────────────────────────┘              └────────────────────────────┘
```

---

## The Two Brains

Daedalus has **two brains** that speak different languages. The boundary between them is the most important design decision in the system.

### Brain 1: The Workflow Package (Semantic)

> *"What should happen next?"*

The workflow package is the **policy engine**. It knows about:
- the tracker and issue model
- workflow-specific states and transitions
- role and prompt structure
- review/publish/merge policy when the workflow has those concepts

It speaks **workflow semantics**:
```
select_issue
render_prompt
publish_ready_pr
merge_and_promote
```

Examples:
- `change-delivery` knows about GitHub issues, PRs, reviewer gates, and merge policy.
- `issue-runner` knows about tracker selection, isolated issue workspaces, lifecycle hooks, and one-agent execution.

### Brain 2: Daedalus Runtime (Execution)

> *"How do I orchestrate this durably?"*

Daedalus is the **execution engine**. It knows about:
- Leases and heartbeats
- SQLite canonical state
- Action queues and idempotency keys
- Retry bookkeeping and failure tracking
- Shadow vs active execution modes

It speaks **execution semantics**:
```
request_internal_review
publish_pr
merge_pr
dispatch_implementation_turn
dispatch_repair_handoff
```

### Why two vocabularies?

Because **policy changes faster than orchestration**. A workflow package can change its issue lifecycle, gate structure, or prompt strategy. Daedalus still has to guarantee that dispatch happens durably, survives crashes, and retries correctly.

---

## The Five Guarantees

Daedalus exists to provide five guarantees that fragile cron-loop automation cannot:

### 1. Exactly-One Ownership (Leases)

```
┌─────────┐    acquire lease     ┌─────────┐
│ Runtime │ ───────────────────► │  Lane   │
│    A    │ ◄─────────────────── │  #42    │
└─────────┘    heartbeat (TTL)   └─────────┘
      │
      │  process dies
      ▼
┌─────────┐    lease expires     ┌─────────┐
│ Runtime │ ◄─────────────────── │  Lane   │
│    B    │ ───────────────────► │  #42    │
└─────────┘   claim on next tick └─────────┘
```

- **Exclusivity:** One runtime owns a lane at a time.
- **Liveness:** Heartbeats prove the owner is alive.
- **Recovery:** Any instance can claim an expired lease. No coordinator needed.

### 2. Exactly-Once Actions (Idempotency)

Every active action has a composite key:
```
lane:<id>:<action_type>:<head_sha>
```

This prevents:
- Double-dispatching the same review on the same head
- Re-running `merge_pr` after the PR is already merged
- Spawning infinite coder sessions for a single issue

### 3. State Is Tracked, Not Guessed

| Layer | Storage | Purpose |
|---|---|---|
| **SQLite** | `daedalus.db` | Canonical runtime state now |
| **JSONL** | `daedalus-events.jsonl` | Append-only history |
| **Lane files** | `.lane-state.json` | Lane-local handoff artifacts |
| **Lane memos** | `.lane-memo.md` | Human-readable handoff notes |

Never reconstruct current state by replaying events. That's what the `lanes` table is for.

### 4. Bad Edits Don't Crash the Loop

```mermaid
flowchart TD
    A[tick begins] --> B{workflow contract changed?}
    B -- no --> C[reuse last ConfigSnapshot]
    B -- yes --> D[parse + validate]
    D -- ok --> E[swap AtomicRef]
    D -- fail --> F[keep last good config]
    F --> G[emit config_reload_failed]
    C --> H[continue tick]
    E --> H
    G --> H
```

A bad `WORKFLOW.md` edit is **ignored**, not fatal. The next valid save picks up automatically.

### 5. Recovery Is Automatic

When an action fails:
1. Failed row is persisted with `retry_count`
2. Next tick checks if retry budget remains
3. If yes: requeue with incremented `retry_count`
4. If no: transition to `operator_attention_required`
5. Human intervenes, or the lane is archived

Lost workers never block forward motion.

---

## Bundled Workflows

Daedalus does not ship one universal lifecycle. It ships a generic engine plus
bundled workflow packages.

| Workflow | Shape | Best for | Docs |
|---|---|---|---|
| `change-delivery` | GitHub issue -> code -> internal review -> PR -> external review -> merge | opinionated SDLC automation | [`workflows/change-delivery.md`](workflows/change-delivery.md) |
| `issue-runner` | tracker issue -> workspace -> hooks -> prompt -> one agent run | generic tracker-driven automation | [`workflows/issue-runner.md`](workflows/issue-runner.md) |

The workflow package owns the lifecycle. Daedalus owns the durable execution
machinery around it.

That means:
- `change-delivery` can define reviewer roles, PR publish, and merge gates.
- `issue-runner` can stay smaller and focus on issue selection plus isolated execution.
- both reuse the same workflow contract loader, runtime adapters, hot-reload primitives, and stall detection.

If you are looking for workflow-specific states, prompts, or operator commands,
read the workflow docs rather than treating the generic architecture as if it
described one universal lane state machine.

---

## Execution Modes

### Shadow Mode: "What would I do?"

- Reads workflow state
- Derives next action
- Writes **shadow** action rows (no idempotency check)
- Emits comparison reports
- **No side effects**

Use shadow mode to validate parity safely before promoting to active.

### Active Mode: "What actually happens."

- Reads workflow state
- Derives next action
- Writes **active** action rows (idempotency enforced)
- Dispatches to real runtimes
- Records success / failure / retry state

Promotion from shadow to active is gated by `active-gate-status` — an explicit operator step, not a config edit.

---

## The Data Flow (One Tick)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   TICK      │────►│    LOAD     │────►│   DERIVE    │────►│   DISPATCH  │
│  (cron/     │     │ workflow +  │     │ next step   │     │  to runtime │
│   manual)   │     │ runtime     │     │ from state  │     │  (active)   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                  │
                                                                  ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   NEXT      │◄────│   RECORD    │◄────│   RESULT    │◄────│   RUNTIME   │
│   TICK      │     │  success/   │     │  success/   │     │  executes   │
│             │     │  failure    │     │  failure    │     │  turn       │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

Each tick:
1. **Load** — Read the workflow contract plus the workflow package's current state
2. **Derive** — Ask the workflow package what operation should happen next
3. **Dispatch** — If the derived action is new and its idempotency key is free, dispatch to runtime
4. **Record** — Write result (success/failure/retry) to SQLite + JSONL
5. **Heartbeat** — Refresh lease to prove liveness

---

## Operator Surfaces

Daedalus exposes tooling instead of forcing DB archaeology.

| Surface | Command | What It Answers |
|---|---|---|
| **Status** | `/daedalus status` | Runtime row, lane count, paths, freshness |
| **Doctor** | `/daedalus doctor` | Full health check across all subsystems |
| **Watch** | `/daedalus watch` | Live TUI: lanes + alerts + events |
| **Shadow Report** | `/daedalus shadow-report` | Diff shadow plan vs active reality |
| **Active Gate** | `/daedalus active-gate-status` | What's blocking promotion to active |
| **Service** | `/daedalus service-status` | systemd health snapshot |
| **HTTP** | `GET localhost:8765/api/v1/state` | JSON snapshot for dashboards |

---

## Repository Anatomy

```
daedalus/
├── __init__.py              # Plugin registration
├── plugin.yaml              # Plugin manifest
├── schemas.py               # CLI/slash parser schema
├── tools.py                 # Operator surface + systemd helpers
├── runtime.py               # Durable engine (the heart)
│   ├── database schema
│   ├── leases + heartbeats
│   ├── ingestion
│   ├── action derivation
│   ├── active execution
│   ├── retries + failure tracking
│   └── runtime loops
├── alerts.py                # Outage alert logic
├── watch.py                 # TUI frame renderer
├── watch_sources.py         # Lane + alert + event aggregation
├── formatters.py            # Human-readable inspection output
├── migration.py             # relay→daedalus filesystem migration
├── observability_overrides.py  # Operator config overrides
├── agents/                  # Shared execution backends (Codex, Claude, Hermes)
├── trackers/                # Shared tracker clients (local-json, Linear, ...)
└── workflows/
    ├── __init__.py          # Workflow loader + CLI dispatcher
    ├── shared/              # Shared paths, config snapshots, stalls
    ├── change_delivery/
        ├── workflow.py      # Semantic policy engine
        ├── dispatch.py      # Action dispatch
        ├── actions.py       # Action primitives
        ├── reviews.py       # Review policy + findings
        ├── sessions.py      # Session protocol
        ├── runtimes/        # Workflow-local compatibility re-exports
        ├── reviewers/       # Reviewer implementations
        ├── webhooks/        # Outbound webhook subscribers
        ├── server/          # HTTP status surface
        ├── comments.py      # GitHub comment formatting
        └── observability.py # Config resolution
    └── issue_runner/
        ├── tracker.py       # Issue selection + workflow-specific tracker policy
        ├── workspace.py     # Issue workspace lifecycle + hooks
        ├── cli.py           # status / doctor / tick
        ├── preflight.py     # Dispatch-gated config checks
        └── schema.yaml      # Workflow contract shape
```

---

## Example Transitional Deployment

One practical deployment shape is a **sensible transitional architecture**:

| Layer | Owner | Role |
|---|---|---|
| **Workflow module** | Project workflow | Semantic policy engine |
| **Daedalus active service** | systemd | Recurring dispatcher |
| **Workflow `tick`** | Manual fallback | Operator override |
| **Milestone notifier** | Hermes cron | Support job (not orchestrator) |
| **Outage alerts** | Daedalus alerts | Support surface (not scheduler) |

It is not fully pure yet, but it is sane.

---

## Long-Term Vision

> Full agentic SDLC lanes that run continuously, respect policy and review gates, survive failures, and let humans stay passive by default while stepping in only when judgment or escalation is truly needed.

That means:
- Each lane is durable
- Coding and reviewing are explicit roles
- State transitions are auditable
- Failures are recoverable
- Humans observe or intervene without becoming the scheduler
- The system runs 24/7 without degrading into prompt spaghetti

**Daedalus is the control-plane skeleton for that future.**

---

## See Also

| Doc | What It Covers |
|---|---|
| [`workflows/README.md`](workflows/README.md) | Which bundled workflow to use and where its template lives |
| [`workflows/change-delivery.md`](workflows/change-delivery.md) | The opinionated GitHub SDLC workflow |
| [`workflows/issue-runner.md`](workflows/issue-runner.md) | The generic tracker-driven bundled workflow |
| [`concepts/lanes.md`](concepts/lanes.md) | Lane state machine, selection, workspace binding |
| [`concepts/actions.md`](concepts/actions.md) | Action types, idempotency, shadow vs active |
| [`concepts/failures.md`](concepts/failures.md) | Failure lifecycle, retry policy, lane-220 fixes |
| [`concepts/leases.md`](concepts/leases.md) | Lease acquisition, heartbeat, recovery, split-brain |
| [`concepts/reviewers.md`](concepts/reviewers.md) | Internal/external/advisory review pipeline |
| [`concepts/observability.md`](concepts/observability.md) | Watch TUI, HTTP server, GitHub comments |
| [`concepts/operator-attention.md`](concepts/operator-attention.md) | When attention triggers, thresholds, recovery |
| [`operator/cheat-sheet.md`](operator/cheat-sheet.md) | Day-to-day commands, debugging, SQL cheats |

---

## Architecture in One Sentence

**Daedalus is a durable orchestration runtime that wraps an SDLC workflow brain with leases, canonical state, action queues, role handoffs, retries, and operator tooling so agentic lanes can run continuously without turning into invisible cron-driven chaos.**
