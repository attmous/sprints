"""Slack notification compatibility exports."""

try:
    from workflows.change_delivery.webhooks.slack_incoming import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from daedalus.workflows.change_delivery.webhooks.slack_incoming import *  # type: ignore # noqa: F401,F403

