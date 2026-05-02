"""Notification type exports for the integrations namespace."""

try:
    from workflows.change_delivery.webhooks import Webhook, WebhookContext
except ModuleNotFoundError:
    from daedalus.workflows.change_delivery.webhooks import Webhook, WebhookContext

__all__ = ["Webhook", "WebhookContext"]
