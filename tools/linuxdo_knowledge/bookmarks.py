from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .state import ensure_knowledge_state, load_json, now_iso, paths_for, write_json


TOPIC_URL_RE = re.compile(r"^https?://linux\.do/t/(?:topic|[^/?#]+)/(\d+)(?:[/?#].*)?$")
DEFAULT_COUNTS = {"new": 0, "metadata_changed": 0, "unchanged": 0}
BOOKMARK_SOURCE = "linuxdo_scripts_bookmark"


def parse_bookmark_export(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []

    items: list[dict[str, Any]] = []
    for folder in data:
        if not isinstance(folder, dict):
            continue
        folder_name = str(folder.get("name", "")).strip()
        entries = folder.get("list", [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("url", "")).strip()
            if not url:
                continue
            item = {
                "folder": folder_name,
                "cate": str(entry.get("cate", "")).strip(),
                "tags": _normalize_tags(entry.get("tags", [])),
                "timestamp": entry.get("timestamp"),
                "title": str(entry.get("title", "")).strip(),
                "url": url,
                "topic_id": extract_topic_id(url),
            }
            item["content_hash"] = bookmark_hash(item)
            items.append(item)
    return items


def extract_topic_id(url: str) -> int | None:
    match = TOPIC_URL_RE.match(url.strip())
    if not match:
        return None
    return int(match.group(1))


def bookmark_hash(item: dict[str, Any]) -> str:
    content = {
        "title": str(item.get("title", "")),
        "folder": str(item.get("folder", "")),
        "cate": str(item.get("cate", "")),
        "tags": _normalize_tags(item.get("tags", [])),
    }
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_bookmark_export(path: Path) -> list[dict[str, Any]]:
    return parse_bookmark_export(json.loads(path.read_text(encoding="utf-8")))


def sync_bookmarks(config: KnowledgeConfig, seen_at: str | None = None) -> dict[str, int]:
    if not config.bookmark_enabled:
        return dict(DEFAULT_COUNTS)

    source_path = _bookmark_source_path(config)
    if source_path is None:
        return dict(DEFAULT_COUNTS)

    seen = seen_at or now_iso()
    bookmarks = load_bookmark_export(source_path)
    ensure_knowledge_state(config)
    paths = paths_for(config)
    bookmark_index = load_json(paths.bookmark_source_index, {"bookmarks": {}})
    frontier = load_json(paths.frontier_queue, {"items": []})
    if not isinstance(bookmark_index, dict):
        bookmark_index = {"bookmarks": {}}
    if not isinstance(frontier, dict):
        frontier = {"items": []}
    index_items = bookmark_index.setdefault("bookmarks", {})
    frontier_items = frontier.setdefault("items", [])

    counts = dict(DEFAULT_COUNTS)
    frontier_by_url = {
        str(item.get("url")): item
        for item in frontier_items
        if isinstance(item, dict) and item.get("url")
    }

    for item in bookmarks:
        url = item["url"]
        existing = index_items.get(url)
        if not isinstance(existing, dict):
            index_items[url] = _bookmark_index_item(item, seen)
            frontier_items.append(_frontier_item(item, seen))
            frontier_by_url[url] = frontier_items[-1]
            counts["new"] += 1
            continue

        if existing.get("content_hash") == item["content_hash"]:
            existing["last_seen_at"] = seen
            counts["unchanged"] += 1
            continue

        index_items[url] = {**existing, **_bookmark_index_item(item, seen), "first_seen_at": existing.get("first_seen_at", seen)}
        frontier_item = frontier_by_url.get(url)
        if frontier_item is None:
            frontier_item = _frontier_item(item, seen)
            frontier_items.append(frontier_item)
            frontier_by_url[url] = frontier_item
        else:
            frontier_item.update(_frontier_update(item, seen))
        counts["metadata_changed"] += 1

    write_json(paths.bookmark_source_index, bookmark_index)
    write_json(paths.frontier_queue, frontier)
    return counts


def _bookmark_source_path(config: KnowledgeConfig) -> Path | None:
    if config.bookmark_path and config.bookmark_path.exists():
        return config.bookmark_path
    if config.fallback_bookmark_path and config.fallback_bookmark_path.exists():
        return config.fallback_bookmark_path
    return None


def _bookmark_index_item(item: dict[str, Any], seen_at: str) -> dict[str, Any]:
    return {
        "url": item["url"],
        "topic_id": item.get("topic_id"),
        "title": item.get("title", ""),
        "folder": item.get("folder", ""),
        "cate": item.get("cate", ""),
        "tags": item.get("tags", []),
        "timestamp": item.get("timestamp"),
        "content_hash": item["content_hash"],
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
    }


def _frontier_item(item: dict[str, Any], seen_at: str) -> dict[str, Any]:
    return {
        **_frontier_update(item, seen_at),
        "created_at": seen_at,
    }


def _frontier_update(item: dict[str, Any], seen_at: str) -> dict[str, Any]:
    return {
        "url": item["url"],
        "topic_id": item.get("topic_id"),
        "title": item.get("title", ""),
        "source": BOOKMARK_SOURCE,
        "priority": _priority_for(item),
        "reason": _reason_for(item),
        "folder": item.get("folder", ""),
        "tags": item.get("tags", []),
        "suggested_level": "frontier",
        "updated_at": seen_at,
    }


def _priority_for(item: dict[str, Any]) -> int:
    tags = {tag.lower() for tag in item.get("tags", [])}
    if tags.intersection({"skill", "plugin", "插件"}):
        return 80
    return 60


def _reason_for(item: dict[str, Any]) -> str:
    parts = [part for part in [item.get("folder"), item.get("cate")] if part]
    location = " / ".join(str(part) for part in parts)
    if location:
        return f"LinuxDo Scripts bookmark: {location}"
    return "LinuxDo Scripts bookmark"


def _normalize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_tags = [value]
    elif isinstance(value, list):
        raw_tags = value
    else:
        raw_tags = []
    return [str(tag).strip() for tag in raw_tags if str(tag).strip()]
