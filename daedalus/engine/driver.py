from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class WorkflowDriver(Protocol):
    """Minimal contract a workflow exposes to the Daedalus engine surface."""

    def build_status(self) -> dict[str, Any]: ...

    def doctor(self) -> dict[str, Any]: ...

    def tick(self) -> dict[str, Any]: ...
