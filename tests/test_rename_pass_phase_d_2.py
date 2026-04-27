"""Phase D-2 tests: function renames + alias drops."""
from __future__ import annotations

import pytest


def test_fetch_external_review_aliased():
    from workflows.code_review.reviews import fetch_external_review, fetch_codex_cloud_review
    assert fetch_codex_cloud_review is fetch_external_review


def test_summarize_external_review_aliased():
    from workflows.code_review.reviews import summarize_external_review, summarize_codex_cloud_review
    assert summarize_codex_cloud_review is summarize_external_review


def test_build_external_review_thread_aliased():
    from workflows.code_review.reviews import build_external_review_thread, build_codex_cloud_thread
    assert build_codex_cloud_thread is build_external_review_thread


def test_should_dispatch_external_review_repair_handoff_aliased():
    from workflows.code_review.reviews import (
        should_dispatch_external_review_repair_handoff,
        should_dispatch_codex_cloud_repair_handoff,
    )
    assert should_dispatch_codex_cloud_repair_handoff is should_dispatch_external_review_repair_handoff


def test_external_review_placeholder_aliased():
    from workflows.code_review.reviews import external_review_placeholder, codex_cloud_placeholder
    assert codex_cloud_placeholder is external_review_placeholder


def test_build_external_review_repair_handoff_payload_aliased():
    from workflows.code_review.reviews import (
        build_external_review_repair_handoff_payload,
        build_codex_cloud_repair_handoff_payload,
    )
    assert build_codex_cloud_repair_handoff_payload is build_external_review_repair_handoff_payload


def test_record_external_review_repair_handoff_aliased():
    from workflows.code_review.reviews import (
        record_external_review_repair_handoff,
        record_codex_cloud_repair_handoff,
    )
    assert record_codex_cloud_repair_handoff is record_external_review_repair_handoff


def test_fetch_external_review_pr_body_signal_aliased():
    from workflows.code_review.reviews import (
        fetch_external_review_pr_body_signal,
        fetch_codex_pr_body_signal,
    )
    assert fetch_codex_pr_body_signal is fetch_external_review_pr_body_signal


def test_render_codex_cloud_repair_handoff_prompt_alias_dropped():
    from workflows.code_review import prompts
    assert not hasattr(prompts, "render_codex_cloud_repair_handoff_prompt")


def test_action_dispatcher_only_accepts_run_internal_review():
    """The 'run_claude_review' alias is dropped — dispatcher matches only the new name."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "workflows/code_review/actions.py").read_text()
    assert "'run_internal_review'" in src or '"run_internal_review"' in src
    assert "'run_claude_review'" not in src
    assert '"run_claude_review"' not in src


def test_get_review_no_longer_falls_back_to_legacy_key():
    from workflows.code_review.migrations import get_review
    # With the legacy fallback dropped, only the new key is found.
    assert get_review({"claudeCode": {"v": 1}}, "internalReview") == {}
    assert get_review({"codexCloud": {"v": 2}}, "externalReview") == {}


def test_parity_map_no_longer_includes_run_claude_review_pair():
    from pathlib import Path
    runtime_src = (Path(__file__).resolve().parent.parent / "runtime.py").read_text()
    tools_src = (Path(__file__).resolve().parent.parent / "tools.py").read_text()
    legacy = '("run_claude_review", "request_internal_review")'
    assert legacy not in runtime_src
    assert legacy not in tools_src


def test_synthesize_repair_brief_no_longer_routes_codex_cloud_key():
    """After the alias drop, source='codexCloud' falls through to the else branch."""
    from workflows.code_review.reviews import synthesize_repair_brief
    reviews = {
        "codexCloud": {
            "required": True,
            "threads": [
                {"id": "t1", "severity": "critical", "status": "open", "summary": "x"},
            ],
        }
    }
    out = synthesize_repair_brief(reviews, head_sha="head", now_iso="2026-04-26T00:00:00Z")
    # The threads should NOT appear as externalReview-prefixed must-fix items.
    must_fix = (out or {}).get("mustFix", []) if out else []
    must_fix_ids = [item.get("id", "") for item in must_fix]
    assert not any(i.startswith("externalReview:") for i in must_fix_ids)
    assert not any(i.startswith("codexCloud:") for i in must_fix_ids)
