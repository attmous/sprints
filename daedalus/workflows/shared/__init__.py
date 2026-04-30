"""Shared workflow infrastructure reused across bundled workflows.

This package holds generic workflow mechanics that stay workflow-agnostic:

- workflow-root resolution and plugin path helpers
- immutable config snapshots and hot-reload primitives
- stall detection helpers

Shared execution backends now live under top-level ``runtimes/`` and shared
tracker integrations under top-level ``trackers/``. Policy-heavy code stays in
individual workflow packages such as ``workflows.change_delivery`` and
``workflows.issue_runner``.
"""
