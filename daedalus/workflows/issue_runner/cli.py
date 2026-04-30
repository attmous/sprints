from __future__ import annotations

import argparse
import json
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the issue-runner workflow.")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show tracker and last-run status.")
    status.add_argument("--json", action="store_true")

    doctor = sub.add_parser("doctor", help="Validate tracker, workspace, and runtime references.")
    doctor.add_argument("--json", action="store_true")

    tick = sub.add_parser("tick", help="Run one issue-runner dispatch tick.")
    tick.add_argument("--json", action="store_true")

    run = sub.add_parser("run", help="Run the long-lived issue-runner polling loop.")
    run.add_argument("--json", action="store_true")
    run.add_argument("--interval-seconds", type=int)
    run.add_argument("--max-iterations", type=int)

    serve = sub.add_parser("serve", help="Serve the optional workflow HTTP status surface.")
    serve.add_argument("--port", type=int)

    return parser


def _print_status(status: dict[str, Any]) -> None:
    tracker = status.get("tracker") or {}
    scheduler = status.get("scheduler") or {}
    selected = status.get("selectedIssue")
    print(f"health: {status.get('health')}")
    print(f"tracker: {tracker.get('kind')} issues={tracker.get('issueCount')} eligible={tracker.get('eligibleCount')}")
    print(
        "scheduler: "
        f"running={len(scheduler.get('running') or [])} "
        f"retry={len(scheduler.get('retry_queue') or [])}"
    )
    if selected:
        print(f"selected issue: {selected.get('id')} {selected.get('title')}")
    else:
        print("selected issue: none")
    last_run = status.get("lastRun") or {}
    if last_run:
        print(f"last run: ok={last_run.get('ok')} attempt={last_run.get('attempt')} at={last_run.get('updatedAt')}")
    metrics = status.get("metrics") or {}
    tokens = metrics.get("tokens") or {}
    total_tokens = int(tokens.get("total_tokens") or 0)
    if total_tokens:
        print(
            "tokens: "
            f"input={int(tokens.get('input_tokens') or 0)} "
            f"output={int(tokens.get('output_tokens') or 0)} "
            f"total={total_tokens}"
        )
    if metrics.get("rate_limits"):
        print(f"rate limits: {metrics.get('rate_limits')}")


def main(workspace: Any, argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "status":
        payload = workspace.build_status()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            _print_status(payload)
        return 0

    if args.command == "doctor":
        payload = workspace.doctor()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"ok: {payload.get('ok')}")
            for check in payload.get("checks") or []:
                print(f"- {check.get('name')}: {check.get('status')} ({check.get('detail')})")
        return 0 if payload.get("ok") else 1

    if args.command == "tick":
        payload = workspace.tick()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"ok={payload.get('ok')} issue={((payload.get('selectedIssue') or {}).get('id'))} "
                f"attempt={payload.get('attempt')} output={payload.get('outputPath')}"
            )
        return 0 if payload.get("ok") else 1

    if args.command == "run":
        payload = workspace.run_loop(
            interval_seconds=args.interval_seconds,
            max_iterations=args.max_iterations,
        )
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"loop={payload.get('loop_status')} iterations={payload.get('iterations')} "
                f"last_ok={((payload.get('last_result') or {}).get('ok'))}"
            )
        return 0

    if args.command == "serve":
        cfg = getattr(workspace, "config", None) or {}
        server_cfg = cfg.get("server") if isinstance(cfg, dict) else None
        server_cfg = server_cfg or {}
        port = args.port if args.port is not None else server_cfg.get("port", 8080)
        bind = server_cfg.get("bind", "127.0.0.1")
        from workflows.change_delivery.server import start_server
        handle = start_server(workspace.path, port=port, bind=bind)
        print(f"daedalus serve listening on http://{bind}:{handle.port}/")
        try:
            handle.thread.join()
        except KeyboardInterrupt:
            handle.shutdown()
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2
