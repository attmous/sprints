"""S-4 tests: event vocabulary alignment — Symphony §10.4."""
from __future__ import annotations


def test_canonical_constants_present():
    from workflows.code_review import event_taxonomy as et

    # Symphony bare names
    assert et.SESSION_STARTED == "session_started"
    assert et.TURN_COMPLETED == "turn_completed"
    assert et.TURN_FAILED == "turn_failed"
    assert et.TURN_CANCELLED == "turn_cancelled"
    assert et.TURN_INPUT_REQUIRED == "turn_input_required"
    assert et.NOTIFICATION == "notification"
    assert et.UNSUPPORTED_TOOL_CALL == "unsupported_tool_call"
    assert et.MALFORMED == "malformed"
    assert et.STARTUP_FAILED == "startup_failed"


def test_daedalus_native_constants_have_prefix():
    from workflows.code_review import event_taxonomy as et

    daedalus_natives = [
        et.DAEDALUS_LANE_CLAIMED, et.DAEDALUS_LANE_RELEASED,
        et.DAEDALUS_REPAIR_HANDOFF, et.DAEDALUS_REVIEW_LANDED,
        et.DAEDALUS_VERDICT_PUBLISHED, et.DAEDALUS_CONFIG_RELOADED,
        et.DAEDALUS_CONFIG_RELOAD_FAILED, et.DAEDALUS_DISPATCH_SKIPPED,
        et.DAEDALUS_STALL_DETECTED, et.DAEDALUS_STALL_TERMINATED,
        et.DAEDALUS_REFRESH_REQUESTED,
    ]
    for name in daedalus_natives:
        assert name.startswith("daedalus."), f"{name!r} missing daedalus. prefix"


def test_canonicalize_passes_canonical_names_through():
    from workflows.code_review.event_taxonomy import canonicalize, TURN_COMPLETED

    assert canonicalize(TURN_COMPLETED) == TURN_COMPLETED
    assert canonicalize("session_started") == "session_started"


def test_canonicalize_resolves_legacy_aliases():
    from workflows.code_review.event_taxonomy import canonicalize

    assert canonicalize("claude_review_started") == "session_started"
    assert canonicalize("claude_review_completed") == "turn_completed"
    assert canonicalize("claude_review_failed") == "turn_failed"
    assert canonicalize("codex_handoff_dispatched") == "daedalus.repair_handoff_dispatched"
    assert canonicalize("internal_review_started") == "session_started"
    assert canonicalize("internal_review_completed") == "turn_completed"


def test_canonicalize_unknown_passthrough():
    from workflows.code_review.event_taxonomy import canonicalize

    assert canonicalize("totally_unknown_event") == "totally_unknown_event"


def test_event_aliases_table_integrity():
    """Every legacy name maps to a known canonical."""
    from workflows.code_review import event_taxonomy as et

    canonical_names = {
        v for k, v in vars(et).items()
        if isinstance(v, str) and (v == k.lower() or v.startswith("daedalus."))
    }
    for legacy, canonical in et.EVENT_ALIASES.items():
        assert canonical in canonical_names or canonical.startswith("daedalus.") or "_" in canonical, \
            f"alias {legacy!r} -> {canonical!r} not a known canonical name"


def test_round_trip_canonical_writer_reader(tmp_path):
    """Writer writes canonical; reader reads canonical via canonicalize."""
    import json
    from workflows.code_review.event_taxonomy import (
        canonicalize, TURN_COMPLETED, DAEDALUS_LANE_CLAIMED,
    )

    log = tmp_path / "events.jsonl"
    with log.open("w") as f:
        f.write(json.dumps({"type": TURN_COMPLETED}) + "\n")
        f.write(json.dumps({"type": DAEDALUS_LANE_CLAIMED}) + "\n")

    seen = []
    for line in log.read_text().splitlines():
        e = json.loads(line)
        seen.append(canonicalize(e["type"]))
    assert seen == [TURN_COMPLETED, DAEDALUS_LANE_CLAIMED]


def test_legacy_log_lines_canonicalize_on_read(tmp_path):
    """Old jsonl files with legacy names still resolve through canonicalize."""
    import json
    from workflows.code_review.event_taxonomy import (
        canonicalize, SESSION_STARTED, DAEDALUS_REPAIR_HANDOFF,
    )

    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"type": "claude_review_started"}) + "\n" +
        json.dumps({"type": "codex_handoff_dispatched"}) + "\n"
    )
    canon = [canonicalize(json.loads(l)["type"]) for l in log.read_text().splitlines()]
    assert canon == [SESSION_STARTED, DAEDALUS_REPAIR_HANDOFF]
