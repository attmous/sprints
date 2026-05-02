import importlib


def test_operator_namespace_wraps_existing_cli_and_formatters():
    importlib.import_module("engine")
    cli = importlib.import_module("daedalus.operator.cli")
    service = importlib.import_module("daedalus.operator.service")
    systemd = importlib.import_module("daedalus.operator.systemd")
    formatters = importlib.import_module("daedalus.operator.formatters")
    watch = importlib.import_module("daedalus.operator.watch")

    daedalus_cli = importlib.import_module("daedalus.daedalus_cli")
    old_formatters = importlib.import_module("daedalus.formatters")
    old_watch = importlib.import_module("daedalus.watch")

    assert cli.execute_raw_args is daedalus_cli.execute_raw_args
    assert service.service_loop is daedalus_cli.service_loop
    assert systemd.install_supervised_service is daedalus_cli.install_supervised_service
    assert formatters.format_doctor is old_formatters.format_doctor
    assert watch.render_frame_to_string is old_watch.render_frame_to_string


def test_operator_http_server_wraps_status_server():
    importlib.import_module("engine")
    http_server = importlib.import_module("daedalus.operator.http_server")
    old_server = importlib.import_module("workflows.change_delivery.server")

    assert http_server.start_server is old_server.start_server
