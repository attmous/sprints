"""Filesystem migration for the Daedalus rebrand.

Renames relay-era files to daedalus paths in a workflow root. Idempotent
and conservative: if a new-named file already exists, the matching old
file is left untouched (operator must inspect manually).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _rename_if_only_old_exists(old: Path, new: Path) -> str | None:
    """Rename old → new only if old exists and new does not.

    Returns a human-readable description of the rename, or None if no
    action was taken.
    """
    if not old.exists():
        return None
    if new.exists():
        return None
    new.parent.mkdir(parents=True, exist_ok=True)
    old.rename(new)
    return f"renamed {old} -> {new}"


def _rename_db_triplet(
    *,
    old_dir: Path,
    new_dir: Path,
    old_stem: str,
    new_stem: str,
) -> list[str]:
    """Atomic rename of a SQLite DB + its WAL/SHM sidecars.

    SQLite WAL mode requires the sidecar filenames to track the main
    DB filename. Moving them independently can produce a corrupt
    triplet (e.g. main DB unchanged, WAL moved to a different name)
    so we treat them as a unit: skip the entire group if the new
    main DB already exists or the old main DB is missing.
    """
    main_old = old_dir / f"{old_stem}.db"
    main_new = new_dir / f"{new_stem}.db"
    # Conflict: new main DB already exists. Leave the entire triplet
    # untouched so an operator can inspect manually.
    if main_new.exists():
        return []
    # No old DB: nothing to migrate (orphan WAL/SHM ignored — they're
    # meaningless without a main DB).
    if not main_old.exists():
        return []
    descriptions: list[str] = []
    for suffix in (".db", ".db-wal", ".db-shm"):
        desc = _rename_if_only_old_exists(
            old_dir / f"{old_stem}{suffix}",
            new_dir / f"{new_stem}{suffix}",
        )
        if desc:
            descriptions.append(desc)
    return descriptions


def migrate_filesystem_state(workflow_root: Path) -> list[str]:
    """Idempotent rename of relay-era paths to daedalus paths.

    Handles:
    - state/relay/relay.db (and SQLite WAL/SHM sidecars) -> state/daedalus/daedalus.db
    - memory/relay-events.jsonl -> memory/daedalus-events.jsonl
    - memory/hermes-relay-alert-state.json -> memory/daedalus-alert-state.json

    Removes the old state/relay/ directory if it ends up empty after
    the move.

    Returns a list of human-readable descriptions of renames performed.
    Empty list means no migration was needed (already in new shape, or
    workflow root has no relay-era data to migrate).
    """
    base = Path(workflow_root)
    descriptions: list[str] = []

    # SQLite DB triplet: main file + WAL + SHM. SQLite WAL mode requires
    # the sidecar filenames to match the main DB filename, so we move all
    # three together as a unit.
    old_state_dir = base / "state" / "relay"
    new_state_dir = base / "state" / "daedalus"
    descriptions.extend(
        _rename_db_triplet(
            old_dir=old_state_dir,
            new_dir=new_state_dir,
            old_stem="relay",
            new_stem="daedalus",
        )
    )

    # Event log and alert state files (single-file moves)
    memory_pairs: Iterable[tuple[Path, Path]] = (
        (base / "memory" / "relay-events.jsonl", base / "memory" / "daedalus-events.jsonl"),
        (
            base / "memory" / "hermes-relay-alert-state.json",
            base / "memory" / "daedalus-alert-state.json",
        ),
    )
    for old, new in memory_pairs:
        desc = _rename_if_only_old_exists(old, new)
        if desc:
            descriptions.append(desc)

    # If state/relay/ ended up empty, remove it
    if old_state_dir.exists() and old_state_dir.is_dir():
        try:
            next(old_state_dir.iterdir())
        except StopIteration:
            old_state_dir.rmdir()

    return descriptions
