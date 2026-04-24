#!/usr/bin/env python3
"""One-shot migrator: legacy yoyopod-workflow.json → workflow.yaml.

Usage: python3 scripts/migrate_config.py <old-json-path> <new-yaml-path>

Reads the legacy JSON, projects each setting into its new YAML location
under the shape defined by workflows/code_review/schema.yaml, and writes
the YAML file. The legacy JSON is NOT deleted by this script — do that
manually after verifying the migration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


def convert(old: dict) -> dict:
    session = old.get("sessionPolicy", {}) or {}
    review = old.get("reviewPolicy", {}) or {}
    labels = old.get("agentLabels", {}) or {}

    engine_owner = old.get("engineOwner", "openclaw")
    repo_path = old.get("repoPath", "")
    # Infer workspace name from paths (used as instance.name).
    instance_name = Path(old.get("ledgerPath", "")).parent.parent.name or "default"

    # Derive github-slug from repoPath when possible; otherwise require operator
    # fixup post-migration. The live YoyoPod_Core path is well-known.
    github_slug = "FIXME/FIXME"
    if "YoyoPod_Core" in repo_path:
        github_slug = "moustafattia/YoyoPod_Core"

    return {
        "workflow": "code-review",
        "schema-version": 1,

        "instance": {
            "name": instance_name,
            "engine-owner": engine_owner,
        },

        "repository": {
            "local-path": repo_path,
            "github-slug": github_slug,
            "active-lane-label": old.get("activeLaneLabel", "active-lane"),
        },

        "runtimes": {
            "acpx-codex": {
                "kind": "acpx-codex",
                "session-idle-freshness-seconds": int(session.get("codexSessionFreshnessSeconds", 900)),
                "session-idle-grace-seconds": int(session.get("codexSessionPokeGraceSeconds", 1800)),
                "session-nudge-cooldown-seconds": int(session.get("codexSessionNudgeCooldownSeconds", 600)),
            },
            "claude-cli": {
                "kind": "claude-cli",
                "max-turns-per-invocation": int(
                    review.get("interReviewAgentMaxTurns")
                    or review.get("internalReviewerAgentMaxTurns")
                    or review.get("claudeReviewMaxTurns", 24)
                ),
                "timeout-seconds": int(
                    review.get("interReviewAgentTimeoutSeconds")
                    or review.get("internalReviewerAgentTimeoutSeconds")
                    or review.get("claudeReviewTimeoutSeconds", 1200)
                ),
            },
        },

        "agents": {
            "coder": {
                "default": {
                    "name": labels.get("internalCoderAgent", "Internal_Coder_Agent"),
                    "model": session.get("codexModel", "gpt-5.3-codex-spark/high"),
                    "runtime": "acpx-codex",
                },
                "high-effort": {
                    "name": labels.get("internalCoderAgent", "Internal_Coder_Agent"),
                    "model": session.get("codexModelLargeEffort") or session.get("codexModelHighEffort") or "gpt-5.3-codex",
                    "runtime": "acpx-codex",
                },
                "escalated": {
                    "name": labels.get("escalationCoderAgent", "Escalation_Coder_Agent"),
                    "model": session.get("codexModelEscalated", "gpt-5.4"),
                    "runtime": "acpx-codex",
                },
            },
            "internal-reviewer": {
                "name": labels.get("internalReviewerAgent", "Internal_Reviewer_Agent"),
                "model": review.get("interReviewAgentModel") or review.get("internalReviewerAgentModel") or review.get("claudeModel", "claude-sonnet-4-6"),
                "runtime": "claude-cli",
                "freeze-coder-while-running": bool(
                    review.get("freezeCoderWhileInterReviewAgentRunning",
                               review.get("freezeCoderWhileInternalReviewAgentRunning",
                                          review.get("freezeCoderWhileClaudeReviewRunning", True)))
                ),
            },
            "external-reviewer": {
                "enabled": True,
                "name": labels.get("externalReviewerAgent", "External_Reviewer_Agent"),
                "provider": "codex-cloud",
                "cache-seconds": int(old.get("reviewCache", {}).get("codexCloudSeconds", 1800)),
            },
            "advisory-reviewer": {
                "enabled": False,
                "name": labels.get("advisoryReviewerAgent", "Advisory_Reviewer_Agent"),
            },
        },

        "gates": {
            "internal-review": {
                "pass-with-findings-tolerance": int(
                    review.get("interReviewAgentPassWithFindingsReviews")
                    or review.get("internalReviewerAgentPassWithFindingsReviews")
                    or review.get("claudePassWithFindingsReviews", 1)
                ),
                "require-pass-clean-before-publish": True,
                "request-cooldown-seconds": int(old.get("reviewCache", {}).get("claudeReviewRequestCooldownSeconds", 1200)),
            },
            "external-review": {
                "required-for-merge": True,
            },
            "merge": {
                "require-ci-acceptable": True,
            },
        },

        "triggers": {
            "lane-selector": {
                "type": "github-label",
                "label": old.get("activeLaneLabel", "active-lane"),
            },
        },

        "escalation": {
            "restart-count-threshold": int(session.get("codexEscalateRestartCount", 2)),
            "local-review-count-threshold": int(session.get("codexEscalateLocalReviewCount", 2)),
            "postpublish-finding-threshold": int(session.get("codexEscalatePostpublishFindingCount", 3)),
            "lane-failure-retry-budget": int(session.get("laneFailureRetryBudget", 3)),
            "no-progress-tick-budget": int(session.get("laneNoProgressTickBudget", 3)),
            "operator-attention-retry-threshold": int(session.get("laneOperatorAttentionRetryThreshold", 5)),
            "operator-attention-no-progress-threshold": int(session.get("laneOperatorAttentionNoProgressThreshold", 5)),
            "lane-counter-increment-min-seconds": int(session.get("laneCounterIncrementMinSeconds", 240)),
        },

        "schedules": {
            "watchdog-tick": {"interval-minutes": 5},
            "milestone-notifier": {
                "interval-hours": 1,
                "delivery": {
                    "channel": "telegram",
                    "chat-id": "-1003651617977",
                },
            },
        },

        "prompts": {
            "internal-review": "internal-review-strict",
            "coder-dispatch": "coder-dispatch",
            "repair-handoff": "repair-handoff",
        },

        "storage": {
            "ledger": "memory/workflow-status.json",
            "health": "memory/workflow-health.json",
            "audit-log": "memory/workflow-audit.jsonl",
            "cron-jobs-path": old.get("cronJobsPath", ""),
            "hermes-cron-jobs-path": old.get("hermesCronJobsPath", str(Path.home() / ".hermes/cron/jobs.json")),
            "sessions-state": "state/sessions",
        },

        "codex-bot": {
            "logins": ["chatgpt-codex-connector", "chatgpt-codex-connector[bot]"],
            "clean-reactions": ["+1"],
            "pending-reactions": ["eyes"],
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: migrate_config.py <old-json-path> <new-yaml-path>", file=sys.stderr)
        return 2
    old_path = Path(argv[0]).expanduser().resolve()
    new_path = Path(argv[1]).expanduser().resolve()
    if not old_path.exists():
        print(f"input JSON not found: {old_path}", file=sys.stderr)
        return 1
    if new_path.exists():
        print(f"refusing to overwrite existing file: {new_path}", file=sys.stderr)
        return 1
    old = json.loads(old_path.read_text(encoding="utf-8"))
    new = convert(old)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(yaml.safe_dump(new, sort_keys=False, default_flow_style=False), encoding="utf-8")
    print(f"wrote {new_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
