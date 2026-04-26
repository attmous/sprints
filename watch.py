"""TUI frame rendering for /daedalus watch.

Phase 2 (this file) implements the frame renderer. The live loop is wired
in later — this module exposes ``render_frame_to_string(snapshot)`` so the
CLI handler and tests can both produce frame text without spinning up a
real TTY.
"""
from __future__ import annotations

from typing import Any, Mapping

from rich.console import Console
from rich.markup import escape as _esc
from rich.panel import Panel
from rich.table import Table


def _lanes_table(lanes: list[dict[str, Any]]) -> Table:
    t = Table(title="Active lanes", expand=True)
    t.add_column("Lane")
    t.add_column("State")
    t.add_column("GH Issue")
    if not lanes:
        t.add_row("(no active lanes)", "", "")
        return t
    for lane in lanes:
        if lane.get("_stale"):
            t.add_row(_esc("[stale]"), _esc("[stale]"), _esc("[stale]"))
            continue
        t.add_row(
            str(lane.get("lane_id") or ""),
            str(lane.get("state") or ""),
            str(lane.get("github_issue_number") or ""),
        )
    return t


def _alerts_panel(alert_state: Mapping[str, Any]) -> Panel | None:
    if alert_state.get("_stale"):
        return Panel(_esc("[stale] alert source unreadable"), title="⚠️  Active alerts")
    if not alert_state or not alert_state.get("active"):
        return None
    msg = alert_state.get("message") or alert_state.get("fingerprint") or "active alert"
    return Panel(str(msg), title="⚠️  Active alerts")


def _events_table(events: list[dict[str, Any]]) -> Table:
    t = Table(title="Recent events", expand=True)
    t.add_column("Time")
    t.add_column("Source")
    t.add_column("Event")
    t.add_column("Detail")
    if not events:
        t.add_row("(no events)", "", "", "")
        return t
    for ev in events[:50]:
        t.add_row(
            str(ev.get("at") or ev.get("time") or "")[:19],
            str(ev.get("source") or "daedalus"),
            str(ev.get("event") or ev.get("action") or ""),
            str(ev.get("detail") or ev.get("summary") or ""),
        )
    return t


def render_frame_to_string(snapshot: Mapping[str, Any]) -> str:
    """Render one TUI frame as a plain string (suitable for tests + no-TTY)."""
    console = Console(record=True, width=120, force_terminal=False)
    console.print(Panel("Daedalus active lanes", style="bold"))
    console.print(_lanes_table(snapshot.get("active_lanes") or []))
    alerts_panel = _alerts_panel(snapshot.get("alert_state") or {})
    if alerts_panel is not None:
        console.print(alerts_panel)
    console.print(_events_table(snapshot.get("recent_events") or []))
    return console.export_text()


# Sibling-import boilerplate for the aggregator.
try:
    from . import watch_sources as _watch_sources  # type: ignore[import-not-found]
except ImportError:
    import importlib.util as _ilu
    from pathlib import Path as _Path
    _spec = _ilu.spec_from_file_location("daedalus_watch_sources_for_watch", _Path(__file__).resolve().parent / "watch_sources.py")
    _watch_sources = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_watch_sources)


def build_snapshot(workflow_root) -> dict[str, Any]:
    """Aggregate all data sources into one TUI snapshot dict."""
    daedalus_events = _watch_sources.recent_daedalus_events(workflow_root, limit=25)
    workflow_audit = _watch_sources.recent_workflow_audit(workflow_root, limit=25)

    # Tag source onto each row, then merge + sort newest-first by 'at'.
    daedalus_tagged = [{**e, "source": "daedalus"} for e in daedalus_events]
    workflow_tagged = [{**e, "source": "workflow"} for e in workflow_audit]
    merged = daedalus_tagged + workflow_tagged
    merged.sort(key=lambda e: e.get("at") or "", reverse=True)

    return {
        "active_lanes": _watch_sources.active_lanes(workflow_root),
        "alert_state": _watch_sources.alert_state(workflow_root),
        "recent_events": merged[:50],
    }
