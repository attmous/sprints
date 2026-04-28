"""S-1 tests: ConfigSnapshot + AtomicRef primitives."""
from __future__ import annotations

import dataclasses

import pytest


def test_config_snapshot_is_frozen():
    from workflows.code_review.config_snapshot import ConfigSnapshot

    snap = ConfigSnapshot(
        config={"workflow": "code-review"},
        prompts={"coder": "hi"},
        loaded_at=1.0,
        source_mtime=2.0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.config = {}  # type: ignore[misc]


def test_config_snapshot_fields():
    from workflows.code_review.config_snapshot import ConfigSnapshot

    snap = ConfigSnapshot(
        config={"k": "v"},
        prompts={"t": "p"},
        loaded_at=1.5,
        source_mtime=2.5,
    )
    assert snap.config == {"k": "v"}
    assert snap.prompts == {"t": "p"}
    assert snap.loaded_at == 1.5
    assert snap.source_mtime == 2.5


def test_atomic_ref_get_set_roundtrip():
    from workflows.code_review.config_snapshot import AtomicRef

    ref: AtomicRef[int] = AtomicRef(0)
    assert ref.get() == 0
    ref.set(7)
    assert ref.get() == 7
    ref.set(42)
    assert ref.get() == 42


def test_atomic_ref_swap_returns_old_value():
    from workflows.code_review.config_snapshot import AtomicRef

    ref: AtomicRef[str] = AtomicRef("a")
    old = ref.swap("b")
    assert old == "a"
    assert ref.get() == "b"


def test_atomic_ref_holds_config_snapshot():
    from workflows.code_review.config_snapshot import AtomicRef, ConfigSnapshot

    s1 = ConfigSnapshot(config={"v": 1}, prompts={}, loaded_at=1.0, source_mtime=1.0)
    s2 = ConfigSnapshot(config={"v": 2}, prompts={}, loaded_at=2.0, source_mtime=2.0)
    ref: AtomicRef[ConfigSnapshot] = AtomicRef(s1)
    assert ref.get() is s1
    ref.set(s2)
    assert ref.get() is s2
    assert ref.get().config == {"v": 2}
