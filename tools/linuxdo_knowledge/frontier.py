from __future__ import annotations

from pathlib import Path
from typing import Any

from .bookmarks import extract_topic_id
from .config import KnowledgeConfig
from .state import load_hot_indexes, now_iso, save_hot_index, write_json


def add_manual_frontier_item(
    config: KnowledgeConfig,
    *,
    url: str,
    reason: str,
    added_at: str | None = None,
) -> dict[str, Any]:
    topic_id = extract_topic_id(url)
    if topic_id is None:
        raise ValueError(f"cannot extract linux.do topic id from url: {url}")

    indexes = load_hot_indexes(config)
    frontier = indexes.setdefault("frontier_queue", {})
    items = frontier.setdefault("items", [])
    if not isinstance(items, list):
        items = []
        frontier["items"] = items

    timestamp = added_at or now_iso()
    payload = {
        "topic_id": topic_id,
        "url": url,
        "reason": reason,
        "source": "manual",
        "priority": 80,
        "added_at": timestamp,
    }
    existing = next(
        (item for item in items if isinstance(item, dict) and int(item.get("topic_id") or 0) == topic_id),
        None,
    )
    if existing is None:
        items.append(payload)
        result = payload
    else:
        existing.update(payload)
        existing["updated_at"] = timestamp
        result = existing

    save_hot_index(config, "frontier_queue", frontier)
    return result


def consume_frontier_items(
    config: KnowledgeConfig,
    readings: Any,
    *,
    batch_id: str,
    output: Path,
    consumed_at: str | None = None,
) -> dict[str, Any]:
    topic_ids = _topic_ids_from_readings(readings)
    timestamp = consumed_at or now_iso()

    indexes = load_hot_indexes(config)
    frontier = indexes.setdefault("frontier_queue", {})
    if not isinstance(frontier, dict):
        frontier = {}

    items = frontier.get("items", [])
    if not isinstance(items, list):
        items = []
    kept_items, consumed_items = _partition_frontier_items(items, topic_ids)
    frontier["items"] = kept_items

    consumed_queue: list[dict[str, Any]] = []
    if "queue" in frontier:
        queue = frontier.get("queue", [])
        if not isinstance(queue, list):
            queue = []
        kept_queue, consumed_queue = _partition_frontier_items(queue, topic_ids)
        frontier["queue"] = kept_queue

    frontier["last_consumed_batch"] = batch_id
    frontier["last_consumed_topic_ids"] = topic_ids
    frontier["last_consumed_at"] = timestamp
    frontier["updated_at"] = timestamp
    save_hot_index(config, "frontier_queue", frontier)

    payload = {
        "batch_id": batch_id,
        "topic_ids": topic_ids,
        "items": consumed_items,
        "queue": consumed_queue,
        "browser_summary": _browser_summary(readings),
        "consumed_at": timestamp,
    }
    write_json(output, payload)
    return payload


def _topic_ids_from_readings(readings: Any) -> list[int]:
    items = _reading_items(readings)
    topic_ids = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        topic_id = _safe_topic_id(item.get("topic_id", item.get("id")))
        if topic_id is None or topic_id in seen:
            continue
        seen.add(topic_id)
        topic_ids.append(topic_id)
    return topic_ids


def _reading_items(readings: Any) -> list[Any]:
    if isinstance(readings, list):
        return readings
    if not isinstance(readings, dict):
        return []
    items = readings.get("readings") or readings.get("topics") or readings.get("items") or []
    return items if isinstance(items, list) else []


def _partition_frontier_items(items: list[Any], topic_ids: list[int]) -> tuple[list[Any], list[dict[str, Any]]]:
    consumed_ids = set(topic_ids)
    kept: list[Any] = []
    consumed: list[dict[str, Any]] = []
    for item in items:
        topic_id = _safe_topic_id(item.get("topic_id")) if isinstance(item, dict) else None
        if topic_id in consumed_ids and isinstance(item, dict):
            consumed.append(item)
        else:
            kept.append(item)
    return kept, consumed


def _browser_summary(readings: Any) -> Any:
    if not isinstance(readings, dict):
        return ""
    return readings.get("browser_summary", "")


def _safe_topic_id(value: Any) -> int | None:
    try:
        topic_id = int(value)
    except (TypeError, ValueError):
        return None
    return topic_id if topic_id > 0 else None
