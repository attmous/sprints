"""Typed access helpers for workflow configuration dictionaries."""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_MISSING = object()


class ConfigError(ValueError):
    """Raised when workflow config is missing or has an unexpected type."""


def _key_aliases(key: str) -> tuple[str, ...]:
    aliases = [key]
    dashed = key.replace("_", "-")
    underscored = key.replace("-", "_")
    for alias in (dashed, underscored):
        if alias not in aliases:
            aliases.append(alias)
    return tuple(aliases)


def _find_key(mapping: Mapping[str, Any], key: str) -> tuple[bool, Any]:
    for alias in _key_aliases(key):
        if alias in mapping:
            return True, mapping[alias]
    return False, None


def _lookup_path(config: Mapping[str, Any], key: str) -> tuple[bool, Any]:
    current: Any = config
    for part in key.split("."):
        if not isinstance(current, Mapping):
            return False, None
        found, current = _find_key(current, part)
        if not found:
            return False, None
    return True, current


def _path_label(keys: Sequence[str]) -> str:
    return " / ".join(keys)


def get_value(config: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first configured value for ``keys`` with dash/underscore aliases."""

    for key in keys:
        found, value = _lookup_path(config, key)
        if found:
            return value
    return default


def first_present(config: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """Alias for ``get_value`` that reads naturally at call sites with fallbacks."""

    return get_value(config, *keys, default=default)


def require(config: Mapping[str, Any], *keys: str) -> Any:
    value = get_value(config, *keys, default=_MISSING)
    if value is _MISSING or value in (None, ""):
        raise ConfigError(f"missing required config value: {_path_label(keys)}")
    return value


def _typed_value(
    config: Mapping[str, Any],
    *keys: str,
    expected: type | tuple[type, ...],
    default: Any = None,
    required: bool = False,
) -> Any:
    value = require(config, *keys) if required else get_value(config, *keys, default=_MISSING)
    if value is _MISSING:
        return default
    if value is None:
        if required:
            raise ConfigError(f"missing required config value: {_path_label(keys)}")
        return default
    if not isinstance(value, expected):
        expected_name = (
            " or ".join(t.__name__ for t in expected)
            if isinstance(expected, tuple)
            else expected.__name__
        )
        raise ConfigError(
            f"config value {_path_label(keys)} must be {expected_name}; "
            f"got {type(value).__name__}"
        )
    return value


def get_str(
    config: Mapping[str, Any],
    *keys: str,
    default: str | None = None,
    required: bool = False,
) -> str | None:
    return _typed_value(config, *keys, expected=str, default=default, required=required)


def get_int(
    config: Mapping[str, Any],
    *keys: str,
    default: int | None = None,
    required: bool = False,
) -> int | None:
    value = require(config, *keys) if required else get_value(config, *keys, default=_MISSING)
    if value is _MISSING or value is None:
        return default
    if isinstance(value, bool):
        raise ConfigError(f"config value {_path_label(keys)} must be int; got bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return int(stripped)
        except ValueError as exc:
            raise ConfigError(f"config value {_path_label(keys)} must be int; got str") from exc
    raise ConfigError(f"config value {_path_label(keys)} must be int; got {type(value).__name__}")


def get_bool(
    config: Mapping[str, Any],
    *keys: str,
    default: bool | None = None,
    required: bool = False,
) -> bool | None:
    value = require(config, *keys) if required else get_value(config, *keys, default=_MISSING)
    if value is _MISSING or value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ConfigError(f"config value {_path_label(keys)} must be bool; got {type(value).__name__}")


def get_list(
    config: Mapping[str, Any],
    *keys: str,
    default: list[Any] | None = None,
    required: bool = False,
) -> list[Any] | None:
    value = _typed_value(config, *keys, expected=list, default=_MISSING, required=required)
    if value is _MISSING:
        return list(default) if default is not None else None
    return list(value)


def get_mapping(
    config: Mapping[str, Any],
    *keys: str,
    default: Mapping[str, Any] | None = None,
    required: bool = False,
) -> dict[str, Any] | None:
    value = _typed_value(config, *keys, expected=Mapping, default=_MISSING, required=required)
    if value is _MISSING:
        return dict(default) if default is not None else None
    return dict(value)


def resolve_env_indirection(
    value: Any,
    *,
    env: Mapping[str, str] | None = None,
    required: bool = False,
) -> Any:
    """Resolve ``$NAME`` values against the environment; literals pass through."""

    if not isinstance(value, str) or not value.startswith("$") or len(value) == 1:
        return value
    env_name = value[1:]
    source = os.environ if env is None else env
    resolved = source.get(env_name)
    if resolved in (None, "") and required:
        raise ConfigError(f"environment variable {env_name} is required")
    return resolved


def resolve_path(
    value: str | Path | None,
    *,
    workflow_root: Path,
    default: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    raw: Any = value if value not in (None, "") else default
    if raw in (None, ""):
        raise ConfigError("path value is required")
    raw = resolve_env_indirection(raw, env=env)
    if raw in (None, ""):
        raise ConfigError("path value is required")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = workflow_root / path
    return path.resolve()


@dataclass(frozen=True)
class ConfigView:
    """Small typed facade around a raw workflow config mapping."""

    raw: Mapping[str, Any]
    workflow_root: Path | None = None

    def value(self, *keys: str, default: Any = None) -> Any:
        return get_value(self.raw, *keys, default=default)

    def first_present(self, *keys: str, default: Any = None) -> Any:
        return first_present(self.raw, *keys, default=default)

    def require(self, *keys: str) -> Any:
        return require(self.raw, *keys)

    def str(self, *keys: str, default: str | None = None, required: bool = False) -> str | None:
        return get_str(self.raw, *keys, default=default, required=required)

    def int(self, *keys: str, default: int | None = None, required: bool = False) -> int | None:
        return get_int(self.raw, *keys, default=default, required=required)

    def bool(self, *keys: str, default: bool | None = None, required: bool = False) -> bool | None:
        return get_bool(self.raw, *keys, default=default, required=required)

    def list(self, *keys: str, default: list[Any] | None = None, required: bool = False) -> list[Any] | None:
        return get_list(self.raw, *keys, default=default, required=required)

    def mapping(
        self,
        *keys: str,
        default: Mapping[str, Any] | None = None,
        required: bool = False,
    ) -> dict[str, Any] | None:
        return get_mapping(self.raw, *keys, default=default, required=required)

    def path(
        self,
        *keys: str,
        default: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Path:
        if self.workflow_root is None:
            raise ConfigError("ConfigView.path requires workflow_root")
        return resolve_path(
            get_value(self.raw, *keys, default=None),
            workflow_root=self.workflow_root,
            default=default,
            env=env,
        )

    def section(self, *keys: str) -> "ConfigView":
        value = get_mapping(self.raw, *keys, default={})
        return ConfigView(value or {}, workflow_root=self.workflow_root)
