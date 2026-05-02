import importlib


def test_code_host_old_and_new_namespace_imports_resolve_same_public_objects():
    old = importlib.import_module("code_hosts")
    new = importlib.import_module("integrations.code_hosts")
    new_types = importlib.import_module("integrations.code_hosts.types")
    new_registry = importlib.import_module("integrations.code_hosts.registry")
    old_github = importlib.import_module("code_hosts.github")
    new_github = importlib.import_module("integrations.code_hosts.github")

    assert new.CodeHostConfigError is old.CodeHostConfigError
    assert new_types.CodeHostClient is old.CodeHostClient
    assert new_registry.build_code_host_client is old.build_code_host_client
    assert new_registry.register is old.register
    assert new_github.GithubCodeHostClient is old_github.GithubCodeHostClient


def test_notification_namespace_wraps_change_delivery_webhooks():
    old_webhooks = importlib.import_module("workflows.change_delivery.webhooks")
    new_webhooks = importlib.import_module("integrations.notifications.webhooks")
    new_types = importlib.import_module("integrations.notifications.types")
    old_slack = importlib.import_module("workflows.change_delivery.webhooks.slack_incoming")
    new_slack = importlib.import_module("integrations.notifications.slack")
    old_http_json = importlib.import_module("workflows.change_delivery.webhooks.http_json")
    new_http_json = importlib.import_module("integrations.notifications.http_json")

    assert new_webhooks.build_webhooks is old_webhooks.build_webhooks
    assert new_types.WebhookContext is old_webhooks.WebhookContext
    assert new_slack.SlackIncomingWebhook is old_slack.SlackIncomingWebhook
    assert new_http_json.HttpJsonWebhook is old_http_json.HttpJsonWebhook
