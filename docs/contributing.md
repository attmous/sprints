# Contributing

Keep the codebase small and current.

## Rules

- Prefer existing module boundaries.
- Do not add compatibility shims for deleted layouts.
- Do not add docs for behavior that no longer exists.
- Keep policy in `WORKFLOW.md` templates, not Python.
- Keep runtime execution in `runtimes/`, not `workflows/`.
- Keep durable state mechanics in `engine/`.

## Checks

Run focused checks for touched files:

```bash
uv run ruff format <files>
uv run ruff check <files>
python -m compileall sprints sprints_cli.py schemas.py __init__.py
```

For docs-only changes, check links and references to deleted files.
