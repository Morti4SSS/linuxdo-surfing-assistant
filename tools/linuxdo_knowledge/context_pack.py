from __future__ import annotations

from typing import Any

from .config import KnowledgeConfig
from .state import load_hot_indexes


PROJECT_FIELDS = (
    "id",
    "title",
    "type",
    "status",
    "watchlist",
    "path",
    "url",
    "topic_id",
    "reason",
    "unread_replies",
    "last_activity_at",
    "reply_count",
    "read_reply_count",
)


def build_context_pack(config: KnowledgeConfig, *, focus: str = "", limit: int = 40) -> dict[str, Any]:
    indexes = load_hot_indexes(config)
    resources = list(indexes.get("resource_index", {}).get("resources", {}).values())
    topics = list(indexes.get("topic_update_state", {}).get("topics", {}).values())
    feedback = list(indexes.get("user_feedback", {}).get("items", []))
    watchlist = [item for item in resources if item.get("watchlist") is True]
    watching = [item for item in resources if item.get("status") == "watching" and item.get("watchlist") is not True]

    topic_updates = []
    for item in topics:
        reply_count = int(item.get("reply_count") or 0)
        read_reply_count = int(item.get("read_reply_count") or item.get("highest_post_number") or 0)
        unread = max(0, reply_count - read_reply_count)
        if unread:
            topic_updates.append({**item, "unread_replies": unread})

    return {
        "focus": focus,
        "watchlist": _project_filter_limit(watchlist, focus, limit),
        "watching": _project_filter_limit(watching, focus, limit),
        "topic_updates": _project_filter_limit(
            sorted(topic_updates, key=lambda item: -int(item.get("unread_replies", 0))),
            focus,
            limit,
        ),
        "feedback": _project_filter_limit(feedback, focus, limit),
    }


def _project_filter_limit(items: list[dict[str, Any]], focus: str, limit: int) -> list[dict[str, Any]]:
    return [_project_item(item) for item in _filter_limit(items, focus, limit)]


def _project_item(item: dict[str, Any]) -> dict[str, Any]:
    projected = {field: item[field] for field in PROJECT_FIELDS if field in item}
    feedback = str(item.get("feedback") or item.get("summary") or "").strip()
    if feedback:
        projected["feedback_preview"] = feedback[:500]
    return projected


def _filter_limit(items: list[dict[str, Any]], focus: str, limit: int) -> list[dict[str, Any]]:
    if focus:
        needle = focus.lower()
        focused = [item for item in items if needle in str(item).lower()]
        if focused:
            return focused[:limit]
    return items[:limit]
