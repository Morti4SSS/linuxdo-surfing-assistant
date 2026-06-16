from __future__ import annotations

from typing import Any

from .config import KnowledgeConfig
from .state import load_hot_indexes, now_iso, save_hot_index


def apply_topic_metadata_refresh(
    config: KnowledgeConfig,
    metadata_items: list[dict[str, Any]],
    *,
    refreshed_at: str | None = None,
) -> dict[str, int]:
    indexes = load_hot_indexes(config)
    topic_state = indexes.setdefault("topic_update_state", {}).setdefault("topics", {})
    updated = 0
    unchanged = 0
    timestamp = refreshed_at or now_iso()

    for item in metadata_items:
        topic_id = _topic_id(item)
        if topic_id is None:
            unchanged += 1
            continue
        key = str(topic_id)
        existing = topic_state.setdefault(key, {"topic_id": topic_id})
        before = dict(existing)
        for field in ("title", "url", "reply_count", "last_activity_at"):
            if field in item and item[field] not in (None, ""):
                existing[field] = item[field]
        if "reply_count" in existing and existing.get("last_activity_at"):
            existing.pop("metadata_refresh_needed", None)
            existing.pop("metadata_refresh_reason", None)
            existing.pop("metadata_refresh_marked_at", None)
        existing["metadata_refreshed_at"] = timestamp
        if existing != before:
            updated += 1
        else:
            unchanged += 1

    save_hot_index(config, "topic_update_state", indexes["topic_update_state"])
    return {"updated": updated, "unchanged": unchanged}


def park_topic_metadata_refresh_blocked(
    config: KnowledgeConfig,
    blocked_items: list[dict[str, Any]],
    *,
    parked_at: str | None = None,
) -> dict[str, int]:
    indexes = load_hot_indexes(config)
    topic_state = indexes.setdefault("topic_update_state", {}).setdefault("topics", {})
    topics = indexes.get("topic_index", {}).get("topics", {})
    if not isinstance(topics, dict):
        topics = {}
    parked = 0
    unchanged = 0
    timestamp = parked_at or now_iso()

    for item in blocked_items:
        topic_id = _topic_id(item)
        if topic_id is None:
            unchanged += 1
            continue
        key = str(topic_id)
        existing = topic_state.setdefault(key, {"topic_id": topic_id})
        canonical = topics.get(key, {})
        if not isinstance(canonical, dict):
            canonical = {}
        before = dict(existing)
        if item.get("url"):
            existing["metadata_refresh_blocked_page_url"] = item["url"]
        if item.get("title"):
            existing["metadata_refresh_blocked_page_title"] = item["title"]
        if canonical.get("url"):
            existing["url"] = canonical["url"]
        elif item.get("url") and not _blocked_page_title(item.get("title")):
            existing.setdefault("url", item["url"])
        if canonical.get("title"):
            existing["title"] = canonical["title"]
        elif item.get("title") and not _blocked_page_title(item.get("title")):
            existing.setdefault("title", item["title"])
        existing.pop("metadata_refresh_needed", None)
        existing.pop("metadata_refresh_reason", None)
        existing.pop("metadata_refresh_marked_at", None)
        existing["metadata_refresh_blocked"] = True
        existing["metadata_refresh_blocked_at"] = timestamp
        existing["metadata_refresh_blocked_reason"] = _blocked_reason(item)
        if item.get("fetch_status"):
            existing["metadata_refresh_blocked_status"] = item["fetch_status"]
        if item.get("source"):
            existing["metadata_refresh_blocked_source"] = item["source"]
        if item.get("needed_human_action"):
            existing["metadata_refresh_blocked_action"] = item["needed_human_action"]
        if existing != before:
            parked += 1
        else:
            unchanged += 1

    save_hot_index(config, "topic_update_state", indexes["topic_update_state"])
    return {"parked": parked, "unchanged": unchanged}


def _topic_id(item: dict[str, Any]) -> int | None:
    try:
        return int(item.get("topic_id"))
    except (TypeError, ValueError):
        return None


def _blocked_reason(item: dict[str, Any]) -> str:
    for field in ("error", "fetch_status", "reason"):
        value = item.get(field)
        if value not in (None, ""):
            return str(value)
    return "live_access_blocked"


def _blocked_page_title(value: Any) -> bool:
    text = "" if value is None else str(value)
    return "找不到页面" in text or "请稍候" in text or "Just a moment" in text or "Cloudflare" in text
