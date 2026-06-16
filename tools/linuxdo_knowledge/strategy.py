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
    refresh_triggers = _string_list(topic.get("refresh_triggers")) or _string_list(state.get("refresh_triggers"))

    if refresh_triggers:
        if "unread_replies" in refresh_triggers:
            level = 2 if "watchlist" in refresh_triggers else 1
            return _plan(
                level,
                "read_incremental",
                "",
                render_required,
                reason=_refresh_reason(refresh_triggers),
                refresh_triggers=refresh_triggers,
                refresh_mode="lightweight",
            )
        if "disputed_claim" in refresh_triggers:
            return _plan(
                2,
                "refresh_light",
                "",
                render_required,
                reason=_refresh_reason(refresh_triggers),
                refresh_triggers=refresh_triggers,
                refresh_mode="lightweight",
            )
        return _plan(
            1,
            "refresh_light",
            "",
            render_required,
            reason=_refresh_reason(refresh_triggers),
            refresh_triggers=refresh_triggers,
            refresh_mode="lightweight",
        )

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
    claim_index = _dict_items(indexes.get("claim_index"), "claims")
    frontier = indexes.get("frontier_queue", {})
    frontier_items = frontier.get("items", []) if isinstance(frontier, dict) else []
    frontier_by_topic = _frontier_by_topic(frontier_items)
    sorted_items = sorted(
        [item for item in frontier_items if isinstance(item, dict)],
        key=lambda item: (-_int(item.get("priority"), 0), str(item.get("title", ""))),
    )

    items: list[dict[str, Any]] = []
    used_topic_ids: set[str] = set()

    for manual_item in [item for item in sorted_items if item.get("source") == "manual"]:
        if len(items) >= batch_size:
            break
        topic_id = _topic_id_for(manual_item)
        if topic_id is None or str(topic_id) in used_topic_ids:
            continue
        indexed_topic = topic_index.get(str(topic_id), {})
        update_state = topic_updates.get(str(topic_id), {})
        topic = {**indexed_topic, **update_state, **manual_item, "topic_id": topic_id}
        if _is_suppressed_topic(topic):
            continue
        items.append(_task_item(topic, update_state))
        used_topic_ids.add(str(topic_id))

    refresh_candidates = _refresh_candidates(
        topic_updates=topic_updates,
        topic_index=topic_index,
        claim_index=claim_index,
        user_feedback=indexes.get("user_feedback", {}),
        frontier_by_topic=frontier_by_topic,
    )

    for refresh_item in refresh_candidates:
        if len(items) >= batch_size:
            break
        topic_id = _topic_id_for(refresh_item)
        if topic_id is None:
            continue
        if _is_suppressed_topic(refresh_item):
            continue
        items.append(_task_item(refresh_item, topic_updates.get(str(topic_id), {})))
        used_topic_ids.add(str(topic_id))

    for frontier_item in sorted_items:
        if len(items) >= batch_size:
            break
        topic_id = _topic_id_for(frontier_item)
        if topic_id is None or str(topic_id) in used_topic_ids:
            continue
        indexed_topic = topic_index.get(str(topic_id), {})
        update_state = topic_updates.get(str(topic_id), {})
        topic = {**indexed_topic, **update_state, **frontier_item, "topic_id": topic_id}
        if _is_suppressed_topic(topic):
            continue
        items.append(_task_item(topic, update_state))
        used_topic_ids.add(str(topic_id))

    return {
        "source": "knowledge_frontier_queue",
        "created_at": created_at or now_iso(),
        "batch_size": batch_size,
        "extraction_policy": "dom_text_first_render_on_demand",
        "history_policy": "load_hot_indexes_only",
        "reply_policies": REPLY_POLICIES,
        "items": items,
    }


def _task_item(topic: dict[str, Any], topic_state: dict[str, Any]) -> dict[str, Any]:
    topic_id = _topic_id_for(topic)
    plan = decide_reading_plan(topic, topic_state)
    level = plan["level"]
    item = {
        "topic_id": topic_id,
        "title": str(topic.get("title", "")),
        "url": str(topic.get("url", "")) or f"https://linux.do/t/topic/{topic_id}",
        "reading_level": level,
        "action": plan["action"],
        "skip_reason": plan["skip_reason"],
        "render_required": plan["render_required"],
        "render_policy": "render_on_demand" if plan["render_required"] else "dom_text_first",
        "reply_policy": REPLY_POLICIES[level],
        "reason": plan.get("reason", "") or str(topic.get("reason", "")),
        "refresh_triggers": plan.get("refresh_triggers", []),
        "refresh_mode": plan.get("refresh_mode", ""),
    }
    for field in ("reply_count", "last_activity_at"):
        if field in topic:
            item[field] = topic[field]
    return item


def _plan(
    level: int,
    action: str,
    skip_reason: str,
    render_required: bool,
    reason: str = "",
    refresh_triggers: list[str] | None = None,
    refresh_mode: str = "",
) -> dict[str, Any]:
    return {
        "level": level,
        "action": action,
        "skip_reason": skip_reason,
        "render_required": render_required,
        "reason": reason,
        "refresh_triggers": refresh_triggers or [],
        "refresh_mode": refresh_mode,
    }


def _refresh_candidates(
    topic_updates: dict[str, Any],
    topic_index: dict[str, Any],
    claim_index: dict[str, Any],
    user_feedback: Any,
    frontier_by_topic: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    feedback_signals = _feedback_signals(user_feedback)
    candidates: list[dict[str, Any]] = []
    topic_ids = sorted(set(topic_updates) | set(topic_index) | set(frontier_by_topic), key=_topic_sort_key)

    for topic_key in topic_ids:
        indexed_topic = topic_index.get(topic_key, {})
        update_state = topic_updates.get(topic_key, {})
        frontier_item = frontier_by_topic.get(topic_key, {})
        has_known_topic = (isinstance(indexed_topic, dict) and bool(indexed_topic)) or (
            isinstance(update_state, dict) and bool(update_state)
        )
        if not has_known_topic:
            continue
        topic = _merge_topic(topic_key, indexed_topic, update_state, frontier_item)
        triggers = _refresh_triggers(topic, update_state, feedback_signals, claim_index, bool(frontier_item))
        if not triggers:
            continue
        topic["refresh_triggers"] = triggers
        topic["reason"] = _refresh_reason(triggers)
        candidates.append(topic)

    return sorted(candidates, key=_refresh_sort_key)


def _merge_topic(
    topic_key: str,
    indexed_topic: Any,
    update_state: Any,
    frontier_item: Any,
) -> dict[str, Any]:
    topic_id = _int(topic_key)
    topic: dict[str, Any] = {"topic_id": topic_id if topic_id is not None else topic_key}
    for item in (indexed_topic, update_state, frontier_item):
        if isinstance(item, dict):
            topic.update(item)
    if _int(topic.get("topic_id")) is None and topic_id is not None:
        topic["topic_id"] = topic_id
    return topic


def _refresh_triggers(
    topic: dict[str, Any],
    topic_state: dict[str, Any],
    feedback_signals: dict[str, dict[str, Any]],
    claim_index: dict[str, Any],
    rediscovered: bool,
) -> list[str]:
    triggers: list[str] = []
    reply_count = _int(topic.get("reply_count"))
    read_reply_count = _int(topic_state.get("read_reply_count", topic.get("read_reply_count")))
    has_unread_replies = _has_new_replies(reply_count, read_reply_count)
    feedback_signal = _feedback_signal_for_topic(topic, feedback_signals)
    is_watchlist = bool(
        topic.get("watchlist") or topic_state.get("watchlist") or (feedback_signal or {}).get("watchlist") is True
    )
    has_feedback = bool((feedback_signal or {}).get("has_human_feedback"))

    if is_watchlist and (has_unread_replies or rediscovered or has_feedback):
        triggers.append("watchlist")
    if has_unread_replies:
        triggers.append("unread_replies")
    if has_feedback:
        triggers.append("human_feedback")
    if _topic_has_refresh_claim(topic, claim_index):
        triggers.append("disputed_claim")
    if rediscovered:
        triggers.append("rediscovered")
    return _dedupe_strings(triggers)


def _feedback_signals(user_feedback: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(user_feedback, dict):
        return {}
    items = user_feedback.get("items", [])
    if not isinstance(items, list):
        return {}
    signals: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = _str_or_empty(item.get("id"))
        status = _str_or_empty(item.get("status")).lower()
        watchlist = item.get("watchlist") if isinstance(item.get("watchlist"), bool) else None
        has_signal = any(_str_or_empty(item.get(field)) for field in ("feedback", "status", "synced_at")) or watchlist is not None
        if item_id and has_signal:
            synced_at = _str_or_empty(item.get("synced_at"))
            has_human_feedback = bool(_str_or_empty(item.get("feedback"))) or status in {
                "needs_verification",
                "needs_rewrite",
                "needs_source_review",
            }
            signal = {
                "synced_at": synced_at,
                "status": status,
                "watchlist": watchlist,
                "has_human_feedback": has_human_feedback,
                "negative": status in {"deprioritized", "rejected"} or watchlist is False,
            }
            if item_id not in signals or synced_at > _str_or_empty(signals[item_id].get("synced_at")):
                signals[item_id] = signal
    return signals


def _feedback_signal_for_topic(topic: dict[str, Any], feedback_signals: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    topic_id = _int(topic.get("topic_id"))
    candidate_ids = set()
    if topic_id is not None:
        candidate_ids.update({str(topic_id), f"topic:{topic_id}", f"source:topic-{topic_id}"})
    for field in ("resource_ids", "related_resources", "claim_ids"):
        for value in _string_list(topic.get(field)):
            candidate_ids.add(value)
            if ":" not in value:
                candidate_ids.update({f"resource:{value}", f"candidate:{value}", f"claim:{value}"})
    last_read_at = _str_or_empty(topic.get("last_read_at"))
    for candidate_id in candidate_ids:
        if candidate_id not in feedback_signals:
            continue
        signal = feedback_signals[candidate_id]
        if signal.get("negative"):
            continue
        synced_at = _str_or_empty(signal.get("synced_at"))
        if not last_read_at:
            return signal
        if synced_at and synced_at > last_read_at:
            return signal
    return None


def _topic_has_refresh_claim(topic: dict[str, Any], claim_index: dict[str, Any]) -> bool:
    refresh_statuses = {"disputed", "needs_retest", "partially_resolved"}
    for claim_id in _string_list(topic.get("claim_ids")):
        claim = claim_index.get(claim_id)
        if isinstance(claim, dict) and _str_or_empty(claim.get("status")).lower() in refresh_statuses:
            return True
    return False


def _frontier_by_topic(frontier_items: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(frontier_items, list):
        return {}
    by_topic: dict[str, dict[str, Any]] = {}
    for item in frontier_items:
        if not isinstance(item, dict):
            continue
        topic_id = _topic_id_for(item)
        if topic_id is None:
            continue
        topic_key = str(topic_id)
        current = by_topic.get(topic_key)
        if current is None or _int(item.get("priority"), 0) > _int(current.get("priority"), 0):
            by_topic[topic_key] = item
    return by_topic


def _refresh_reason(triggers: list[str]) -> str:
    labels = {
        "watchlist": "watchlist",
        "unread_replies": "unread replies",
        "human_feedback": "human feedback",
        "disputed_claim": "disputed claim",
        "rediscovered": "rediscovered",
    }
    return "; ".join(labels.get(trigger, trigger) for trigger in triggers)


def _refresh_sort_key(topic: dict[str, Any]) -> tuple[int, int, str]:
    triggers = set(_string_list(topic.get("refresh_triggers")))
    trigger_score = 0
    if "watchlist" in triggers:
        trigger_score += 40
    if "unread_replies" in triggers:
        trigger_score += 30
    if "human_feedback" in triggers:
        trigger_score += 20
    if "disputed_claim" in triggers:
        trigger_score += 25
    if "rediscovered" in triggers:
        trigger_score += 10
    return (-trigger_score, -_int(topic.get("priority"), 0), str(topic.get("title", "")))


def _topic_sort_key(value: str) -> tuple[int, str]:
    parsed = _int(value)
    return (parsed if parsed is not None else 10**12, value)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    elif isinstance(value, tuple):
        values = list(value)
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip()]


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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
    return _str_or_empty(topic.get("status")).lower() in {"deprioritized", "rejected", "archived"}


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
