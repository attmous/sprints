"""Code-host type exports for the integrations namespace."""

try:
    from code_hosts import CodeHostClient, CodeHostConfigError
except ModuleNotFoundError:
    from daedalus.code_hosts import CodeHostClient, CodeHostConfigError

__all__ = ["CodeHostClient", "CodeHostConfigError"]
