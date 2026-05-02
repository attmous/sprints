"""Immutable config snapshot + atomic reference wrapper.

Symphony §6.2 (hot-reload) and §13.7 (HTTP server) require multiple
threads to read the parsed workflow config concurrently while a single
writer thread swaps in a freshly parsed snapshot.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Generic, Mapping, TypeVar


def _freeze_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, dict):
        return MappingProxyType(value)
    return value


@dataclass(frozen=True)
class ConfigSnapshot:
    config: Mapping[str, Any]
    prompts: Mapping[str, Any]
    loaded_at: float
    source_mtime: float
    source_size: int = -1

    def __post_init__(self) -> None:
        object.__setattr__(self, "config", _freeze_mapping(self.config))
        object.__setattr__(self, "prompts", _freeze_mapping(self.prompts))


T = TypeVar("T")


class AtomicRef(Generic[T]):
    """Lock-protected single-value reference cell."""

    def __init__(self, initial: T) -> None:
        self._lock = threading.Lock()
        self._value: T = initial

    def get(self) -> T:
        return self._value

    def set(self, new_value: T) -> None:
        with self._lock:
            self._value = new_value

    def swap(self, new_value: T) -> T:
        with self._lock:
            old = self._value
            self._value = new_value
            return old

