"""Generic hot-reload of a workflow contract file."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError as _JSValidationError

from workflows.contract import WorkflowContractError, load_workflow_contract_file
from workflows.config_snapshot import AtomicRef, ConfigSnapshot


class ParseError(Exception):
    """Raised when the workflow contract cannot be parsed or projected."""


class ValidationError(Exception):
    """Raised when the workflow contract parses but violates schema.yaml."""


def parse_and_validate_contract(
    workflow_contract_path: Path,
    *,
    schema_path: Path,
) -> ConfigSnapshot:
    try:
        contract = load_workflow_contract_file(workflow_contract_path)
    except WorkflowContractError as exc:
        raise ParseError(str(exc)) from exc
    config = contract.config
    try:
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        Draft7Validator(schema).validate(config)
    except _JSValidationError as exc:
        raise ValidationError(f"schema validation failed: {exc.message}") from exc

    prompts = config.get("prompts") or {}
    st = contract.source_path.stat()
    return ConfigSnapshot(
        config=config,
        prompts=prompts,
        loaded_at=time.monotonic(),
        source_mtime=st.st_mtime,
        source_size=st.st_size,
    )


@dataclass
class ConfigWatcher:
    workflow_contract_path: Path
    schema_path: Path
    snapshot_ref: AtomicRef[ConfigSnapshot]
    emit_event: Callable[[str, dict], None]
    _last_key: tuple[float, int] = (0.0, 0)

    def __post_init__(self) -> None:
        snap = self.snapshot_ref.get()
        self._last_key = (snap.source_mtime, snap.source_size)

    def poll(self) -> None:
        try:
            st = self.workflow_contract_path.stat()
        except OSError:
            return
        key = (st.st_mtime, st.st_size)
        if key == self._last_key:
            return
        try:
            new_snapshot = parse_and_validate_contract(
                self.workflow_contract_path,
                schema_path=self.schema_path,
            )
        except (ParseError, ValidationError, OSError, UnicodeDecodeError) as exc:
            self.emit_event(
                "daedalus.config_reload_failed",
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "mtime": st.st_mtime,
                    "size": st.st_size,
                },
            )
            self._last_key = key
            return

        self.snapshot_ref.set(new_snapshot)
        self._last_key = key
        self.emit_event(
            "daedalus.config_reloaded",
            {"loaded_at": new_snapshot.loaded_at, "source_mtime": st.st_mtime, "size": st.st_size},
        )


