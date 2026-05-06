"""Code-host review context collection and compaction."""

from __future__ import annotations

from typing import Any

_MAX_REVIEW_CONTEXT_ITEMS = 8
_MAX_COMMENT_TEXT = 600
_SPRINTS_COMMENT_MARKERS = (
    "sprints-workpad",
    "sprints:idempotency-key",
)


def collect_review_context(*, client: Any, pr_number: str) -> dict[str, Any]:
    context: dict[str, Any] = {
        "reviews": [],
        "pull_request_comments": [],
        "review_threads": {},
        "errors": [],
    }
    for key, method_name in (
        ("reviews", "fetch_pull_request_reviews"),
        ("pull_request_comments", "fetch_pull_request_comments"),
        ("review_threads", "fetch_pull_request_review_threads"),
    ):
        method = getattr(client, method_name, None)
        if not callable(method):
            continue
        try:
            context[key] = method(pr_number)
        except Exception as exc:
            context["errors"].append(
                {
                    "source": method_name,
                    "pull_request": pr_number,
                    "error": str(exc),
                }
            )
    if not context["errors"]:
        context.pop("errors", None)
    return context


def compact_review_context(context: dict[str, Any]) -> dict[str, Any]:
    context = context if isinstance(context, dict) else {}
    comments = [
        *_compact_comments(context.get("pull_request_comments"), source="pull_request"),
        *_compact_comments(
            _review_thread_comments(context.get("review_threads")),
            source="review_thread",
        ),
    ][-_MAX_REVIEW_CONTEXT_ITEMS:]
    return {
        key: value
        for key, value in {
            "reviews": _compact_reviews(context.get("reviews")),
            "comments": comments,
            "context_errors": context.get("errors"),
        }.items()
        if value not in (None, "", [], {})
    }


def _compact_reviews(value: Any) -> list[dict[str, Any]]:
    reviews = [item for item in value or [] if isinstance(item, dict)]
    compacted: list[dict[str, Any]] = []
    for review in reviews[-_MAX_REVIEW_CONTEXT_ITEMS:]:
        user = review.get("user") if isinstance(review.get("user"), dict) else {}
        compacted.append(
            {
                key: field
                for key, field in {
                    "id": review.get("id"),
                    "state": review.get("state"),
                    "author": user.get("login"),
                    "body": _compact_text(review.get("body")),
                    "url": review.get("html_url") or review.get("url"),
                    "submitted_at": review.get("submitted_at"),
                }.items()
                if field not in (None, "", [], {})
            }
        )
    return compacted


def _compact_comments(value: Any, *, source: str) -> list[dict[str, Any]]:
    comments = [item for item in value or [] if isinstance(item, dict)]
    compacted: list[dict[str, Any]] = []
    for comment in comments:
        body = str(comment.get("body") or "").strip()
        if not body or _is_sprints_comment(body):
            continue
        user = (
            comment.get("user")
            if isinstance(comment.get("user"), dict)
            else comment.get("author")
            if isinstance(comment.get("author"), dict)
            else {}
        )
        compacted.append(
            {
                key: field
                for key, field in {
                    "source": source,
                    "id": comment.get("id"),
                    "author": user.get("login"),
                    "body": _compact_text(body),
                    "url": comment.get("html_url") or comment.get("url"),
                    "created_at": comment.get("created_at") or comment.get("createdAt"),
                    "path": comment.get("path"),
                    "line": comment.get("line"),
                }.items()
                if field not in (None, "", [], {})
            }
        )
    return compacted[-_MAX_REVIEW_CONTEXT_ITEMS:]


def _review_thread_comments(threads: Any) -> list[dict[str, Any]]:
    review_threads = threads.get("reviewThreads") if isinstance(threads, dict) else {}
    nodes = review_threads.get("nodes") if isinstance(review_threads, dict) else []
    comments: list[dict[str, Any]] = []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        comment_block = (
            node.get("comments") if isinstance(node.get("comments"), dict) else {}
        )
        for comment in comment_block.get("nodes") or []:
            if not isinstance(comment, dict):
                continue
            comments.append(
                {
                    **comment,
                    "path": node.get("path"),
                    "line": node.get("line"),
                    "thread_id": node.get("id"),
                    "thread_resolved": node.get("isResolved"),
                    "thread_outdated": node.get("isOutdated"),
                }
            )
    return comments


def _compact_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= _MAX_COMMENT_TEXT:
        return text
    return text[: _MAX_COMMENT_TEXT - 1].rstrip() + "."


def _is_sprints_comment(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _SPRINTS_COMMENT_MARKERS)
