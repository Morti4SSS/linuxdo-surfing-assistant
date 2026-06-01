from __future__ import annotations

from typing import Any

from .bookmarks import extract_topic_id
from .config import KnowledgeConfig
from .state import load_hot_indexes, now_iso


HIGH_SIGNAL_WORDS = ("实测", "踩坑", "替代", "不推荐", "更新了", "解决了", "对比", "争议")
LOW_VALUE_TERMS = ("签到", "水贴", "闲聊")
RENDER_SIGNALS = ("如图", "看图", "截图", "效果如下", "UI", "WebUI", "按钮", "报错图")

REPLY_POLICIES = {
    0: "Level 0 metadata only",
    1: "Level 1 main post + small high-signal replies + minimal context",
    2: "Level 2 main post + popular/disputed/linked/author/contextual replies",
    3: "Level 3 deep read most replies because topic affects comparison/resource choice",
}


def decide_reading_plan(topic: dict[str, Any], topic_state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = topic_state if isinstance(topic_state, dict) else {}
    text = _topic_text(topic)
    render_required = _has_any(text, RENDER_SIGNALS)
    reply_count = _int(topic.get("reply_count"))
    read_reply_count = _int(state.get("read_reply_count", state.get("reply_count")))
    last_activity_at = _str_or_empty(topic.get("last_activity_at"))
    read_activity_at = _str_or_empty(state.get("last_activity_at", state.get("read_last_activity_at")))

    if _is_unchanged_read_topic(reply_count, read_reply_count, last_activity_at, read_activity_at):
        return _plan(0, "skip", "unchanged_read_topic", render_required)

    if state.get("watchlist") and _has_new_replies(reply_count, read_reply_count):
        return _plan(2, "read_incremental", "", render_required)

    if _has_any(text, LOW_VALUE_TERMS) and not _has_any(text, HIGH_SIGNAL_WORDS):
        return _plan(0, "metadata_only", "low_value_topic", render_required)

    hinted_level = _suggested_level(topic.get("suggested_level"))
    level = hinted_level if hinted_level is not None else 1
    if _has_any(text, HIGH_SIGNAL_WORDS):
        level = max(level, 2)

    return _plan(level, "read", "", render_required)


def build_knowledge_task(
    config: KnowledgeConfig,
    batch_size: int = 20,
    created_at: str | None = None,
) -> dict[str, Any]:
    indexes = load_hot_indexes(config)
    topic_updates = _dict_items(indexes.get("topic_update_state"), "topics")
    topic_index = _dict_items(indexes.get("topic_index"), "topics")
    frontier = indexes.get("frontier_queue", {})
    frontier_items = frontier.get("items", []) if isinstance(frontier, dict) else []
    sorted_items = sorted(
        [item for item in frontier_items if isinstance(item, dict)],
        key=lambda item: (-_int(item.get("priority"), 0), str(item.get("title", ""))),
    )

    items: list[dict[str, Any]] = []
    for frontier_item in sorted_items:
        if len(items) >= batch_size:
            break
        topic_id = _topic_id_for(frontier_item)
        if topic_id is None:
            continue
        indexed_topic = topic_index.get(str(topic_id), {})
        topic = {**indexed_topic, **frontier_item, "topic_id": topic_id}
        if _is_suppressed_topic(topic):
            continue
        plan = decide_reading_plan(topic, topic_updates.get(str(topic_id), {}))
        level = plan["level"]
        items.append(
            {
                "topic_id": topic_id,
                "title": str(topic.get("title", "")),
                "url": str(topic.get("url", "")) or f"https://linux.do/t/topic/{topic_id}",
                "reading_level": level,
                "action": plan["action"],
                "skip_reason": plan["skip_reason"],
                "render_required": plan["render_required"],
                "render_policy": "render_on_demand" if plan["render_required"] else "dom_text_first",
                "reply_policy": REPLY_POLICIES[level],
            }
        )

    return {
        "source": "knowledge_frontier_queue",
        "created_at": created_at or now_iso(),
        "batch_size": batch_size,
        "extraction_policy": "dom_text_first_render_on_demand",
        "history_policy": "load_hot_indexes_only",
        "reply_policies": REPLY_POLICIES,
        "items": items,
    }


def _plan(level: int, action: str, skip_reason: str, render_required: bool) -> dict[str, Any]:
    return {
        "level": level,
        "action": action,
        "skip_reason": skip_reason,
        "render_required": render_required,
    }


def _topic_text(topic: dict[str, Any]) -> str:
    parts = [
        topic.get("title", ""),
        topic.get("first_text", ""),
        topic.get("reason", ""),
        topic.get("folder", ""),
        topic.get("cate", ""),
        " ".join(str(tag) for tag in topic.get("tags", []) or []),
    ]
    return " ".join(str(part) for part in parts if str(part).strip())


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    lower_text = text.lower()
    return any(word.lower() in lower_text for word in words)


def _is_unchanged_read_topic(
    reply_count: int | None,
    read_reply_count: int | None,
    last_activity_at: str,
    read_activity_at: str,
) -> bool:
    has_reply_match = reply_count is not None and read_reply_count is not None and reply_count == read_reply_count
    has_activity_match = bool(last_activity_at) and last_activity_at == read_activity_at
    if has_reply_match and has_activity_match:
        return True
    return has_reply_match and not last_activity_at and not read_activity_at


def _has_new_replies(reply_count: int | None, read_reply_count: int | None) -> bool:
    if reply_count is None or read_reply_count is None:
        return False
    return reply_count > read_reply_count


def _suggested_level(value: Any) -> int | None:
    parsed = _int(value)
    if parsed is None or parsed < 0 or parsed > 3:
        return None
    return parsed


def _topic_id_for(item: dict[str, Any]) -> int | None:
    topic_id = _int(item.get("topic_id"))
    if topic_id is not None:
        return topic_id
    return extract_topic_id(str(item.get("url", "")))


def _is_suppressed_topic(topic: dict[str, Any]) -> bool:
    return _str_or_empty(topic.get("status")).lower() in {"deprioritized", "archived"}


def _dict_items(value: Any, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    items = value.get(key, {})
    return items if isinstance(items, dict) else {}


def _int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _str_or_empty(value: Any) -> str:
    return str(value).strip() if value is not None else ""
