# Restructure Shim Audit

Status: current as of Turn 12.

The restructure keeps public compatibility shims while internal workflow code
moves to the new namespaces.

## Retained Public Shims

- `engine/`
- `workflows/`
- `runtimes/`
- `trackers/`

These remain public compatibility paths for local plugin execution, direct
workflow CLI entrypoints, and existing imports.

## New Internal Namespaces

- `workflows.core`
- `integrations.trackers`
- `integrations.code_hosts`
- `integrations.notifications`
- `runtimes.types`
- `runtimes.registry`
- `runtimes.command`
- `daedalus.operator`

Workflow code should prefer these namespaces for new imports. Compatibility
wrappers may still import old paths internally because that is their purpose.

## Removed In This Turn

- Private duplicate change-delivery storage path resolver, replaced by
  `workflows.change_delivery.config.ChangeDeliveryConfig`.

No public shim was removed in this branch because root-level compatibility
packages are still listed as stable public contract.
