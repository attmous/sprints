# Harness Engineering

Daedalus uses repo-level harness checks to keep the public project clean while
the implementation continues to move quickly.

## Public Posture

The public release is GitHub-first:

- `change-delivery` is the supported managed SDLC workflow.
- `issue-runner` supports GitHub as the first-class tracker path.
- `local-json` exists for local development and deterministic tests.
- Linear remains an experimental adapter until the GitHub path has real
  integration coverage and stronger operator docs.

## Guardrails

The harness tests should catch these regressions before review:

- public docs must describe the GitHub-first path clearly
- public examples must use generic placeholders like `your-org/your-repo`
- bundled workflow templates must match their public docs copies
- bootstrap must safely promote `WORKFLOW.md` to `WORKFLOW-<workflow>.md`
  without overwriting existing named contracts
- project-specific playground names must not leak outside `daedalus/projects/**`
- installation docs must keep the landing-page quick start short and link to
  detailed operator docs

## Next Checks

Add tests for the next hardening slice in this order:

1. `WORKFLOW*.md` bootstrap branch creation and update behavior when a repo
   already has one workflow contract.
2. Codex app-server diagnostics for managed and external service modes.
3. CLI/docs drift checks for every command shown in the install guide.

## Live GitHub Smoke

The first live GitHub smoke is implemented but skipped by default:

```bash
export DAEDALUS_GITHUB_SMOKE_REPO=your-org/your-repo
pytest tests/test_github_issue_runner_smoke.py -q
```

See [operator/github-smoke.md](operator/github-smoke.md) for setup and cleanup
details.
