"""Code-host registry exports for the integrations namespace."""

try:
    from code_hosts import build_code_host_client, code_host_kind, register
except ModuleNotFoundError:
    from daedalus.code_hosts import build_code_host_client, code_host_kind, register

__all__ = ["build_code_host_client", "code_host_kind", "register"]
