"""Webhook notification compatibility exports."""

try:
    from workflows.change_delivery.webhooks import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from daedalus.workflows.change_delivery.webhooks import *  # type: ignore # noqa: F401,F403

