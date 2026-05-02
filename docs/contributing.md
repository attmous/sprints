# Contributing to Sprints

So you want to hack on Sprints? This doc covers the current lightweight contributor path, adding a new runtime, adding workflow mechanics, and keeping docs in sync.

---

## Quick start

```bash
# Clone
git clone https://github.com/attmous/sprints.git
cd sprints

# Install contributor deps
python3 -m pip install -r requirements-dev.txt

# Install (into your Hermes home)
./scripts/install.sh

# Verify syntax/importability
python3 -m compileall sprints
```

If you touch files loaded at runtime via `Path(__file__).parent` — prompts,
skills, workflow templates, or `plugin.yaml` — keep the package metadata in
`pyproject.toml` / `MANIFEST.in` aligned. `sprints/projects/**`
is placeholder-only in the public repo and is intentionally not shipped in the
public plugin payload.

---

## Adding a new runtime

1. **Implement the Protocol** in `sprints/runtimes/your_runtime.py`:
   ```python
   from sprints.runtimes import register

   @register("your-kind")
   class YourRuntime:
       def ensure_session(self, *, worktree, session_name, model, resume_session_id): ...
       def run_prompt(self, *, worktree, session_name, prompt, model): ...
       def assess_health(self, session_meta, *, worktree, now_epoch): ...
       def close_session(self, *, worktree, session_name): ...
       def last_activity_ts(self) -> float | None: ...
   ```

2. **Add to schema** in `sprints/workflows/change_delivery/schema.yaml`:
   ```yaml
   runtimes:
     your-runtime:
       kind: your-kind
       timeout-seconds: 1200
   ```

3. **Document** in `docs/concepts/runtimes.md`.

---

## Adding a workflow stage

The current change-delivery workflow has stages: `implementing` → `awaiting_pre_publish_review` → `ready_to_publish` → `under_review` → `approved` → `merged`.

To add a new stage:

1. **Add the state** to the workflow state machine in `sprints/workflows/change_delivery/workflow.py`.
2. **Add the transition logic** in `sprints/workflows/change_delivery/dispatch.py`.
3. **Add the action type** in `sprints/workflows/change_delivery/actions.py`.
4. **Update the schema** in `sprints/workflows/change_delivery/migrations.py` (if new DB columns needed).
5. **Document** in `docs/concepts/lanes.md` and `docs/concepts/actions.md`.

---

## Keeping docs in sync

Every code change that affects operator-facing behavior must update docs:

| Change type | Docs to update |
|---|---|
| New slash command | `docs/operator/slash-commands.md`, `docs/operator/cheat-sheet.md` |
| New concept | `docs/concepts/<new-concept>.md`, `docs/architecture.md` |
| Schema change | `docs/concepts/lanes.md`, `docs/concepts/actions.md` |
| Config change | `sprints/workflows/templates/*.md`, `docs/examples/*.workflow.md`, `docs/concepts/hot-reload.md`, `docs/operator/cheat-sheet.md` |
| Rename/refactor | Relevant docs that describe the current public structure |

---

## Code style

- **Type hints everywhere.** `from __future__ import annotations` at the top of every file.
- **No external deps in core.** The runtime must work with stdlib + SQLite only. Rich is allowed for TUI rendering.
- **Fail soft.** Every subscriber, webhook, and observer must catch its own exceptions. Never let a side-effect failure crash the tick.
- `--json` is the default operator dialect. Humans read formatters, scripts read JSON.

---

## Where to get help

- Read the operator cheat sheet: `docs/operator/cheat-sheet.md`
- Check the architecture doc: `docs/architecture.md`
- Run `/sprints doctor` inside Hermes
- Open an issue with the output of `/sprints status --format json`
