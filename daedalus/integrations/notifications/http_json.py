"""HTTP JSON webhook notification compatibility exports."""

try:
    from workflows.change_delivery.webhooks.http_json import *  # type: ignore # noqa: F401,F403
except ModuleNotFoundError:
    from daedalus.workflows.change_delivery.webhooks.http_json import *  # type: ignore # noqa: F401,F403

