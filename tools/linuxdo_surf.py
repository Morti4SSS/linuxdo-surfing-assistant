from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


MODES = {"research", "goldmine", "skill-feedback", "discover"}
CONTROL_CHANNELS = {"codex-browser", "user-chrome", "mac-goal"}
DEFAULT_CONTROL_CHANNEL = "codex-browser"
PRIMARY_QUEUE_NAMES = ("new", "active-old", "low-traffic")
DISCOVERY_QUEUE_NAMES = ("author-tracking", "comment-reference", "tool-lookup", "skill-workflow-evidence")
DEFAULT_QUEUE_QUOTAS = {"new": 0.4, "active-old": 0.4, "low-traffic": 0.2}
DEFAULT_KEYWORDS = {
    "goldmine": ["ai coding", "codex", "claude code", "skill", "mcp", "workflow", "工作流", "插件", "开源", "经验"],
    "discover": ["skill", "workflow", "harness", "mcp", "cli", "插件", "工具", "开源", "推荐"],
}


def validate_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in MODES:
        raise ValueError(f"未知模式：{mode}")
    return normalized


def validate_channel(channel: str) -> str:
    normalized = channel.strip().lower()
    if normalized not in CONTROL_CHANNELS:
        raise ValueError(f"未知操控通道：{channel}")
    return normalized


def rank_topics(
    topics: list[dict[str, Any]],
    mode: str,
    query: str = "",
    skill_names: list[str] | None = None,
    read_ids: set[int] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    validate_mode(mode)
    read_ids = read_ids or set()
    keywords = _keywords_for(mode, query, skill_names or [])
    ranked = []
    for topic in topics:
        topic_id = _safe_int(topic.get("id"))
        if topic_id is None:
            continue
        if topic_id in read_ids:
            continue
        score = _topic_score(topic, keywords)
        ranked.append({**topic, "surf_score": round(score, 2)})
    ranked.sort(key=lambda item: (-item["surf_score"], str(item.get("title", ""))))
    return ranked[:limit]


def build_frontier_queue(
    topics: list[dict[str, Any]],
    mode: str,
    query: str = "",
    skill_names: list[str] | None = None,
    read_ids: set[int] | None = None,
    now: str | datetime | None = None,
    max_candidates: int = 80,
) -> dict[str, Any]:
    mode = validate_mode(mode)
    read_ids = read_ids or set()
    current_time = _coerce_datetime(now) or datetime.now()
    queues = {name: [] for name in PRIMARY_QUEUE_NAMES}
    for topic in rank_topics(topics, mode, query, skill_names or [], read_ids, max_candidates):
        queue_name = _primary_queue_for_topic(topic, current_time)
        queues[queue_name].append(_frontier_item(topic, queue_name))
    return {
        "created_at": current_time.isoformat(timespec="seconds"),
        "mode": mode,
        "query": query,
        "queues": queues,
        "discovery_queues": {name: [] for name in DISCOVERY_QUEUE_NAMES},
        "quotas": dict(DEFAULT_QUEUE_QUOTAS),
    }


def select_next_batch(frontier: dict[str, Any], max_topics: int) -> list[dict[str, Any]]:
    _validate_positive("max-topics", max_topics)
    quotas = frontier.get("quotas", DEFAULT_QUEUE_QUOTAS)
    queues = frontier.get("queues", {})
    selected: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for queue_name in PRIMARY_QUEUE_NAMES:
        quota_count = max(1, int(round(max_topics * float(quotas.get(queue_name, 0)))))
        for item in queues.get(queue_name, [])[:quota_count]:
            item_id = _safe_int(item.get("id"))
            if item_id is None or item_id in seen_ids:
                continue
            selected.append(item)
            seen_ids.add(item_id)
            if len(selected) >= max_topics:
                return selected

    for queue_name in PRIMARY_QUEUE_NAMES:
        for item in queues.get(queue_name, []):
            item_id = _safe_int(item.get("id"))
            if item_id is None or item_id in seen_ids:
                continue
            selected.append(item)
            seen_ids.add(item_id)
            if len(selected) >= max_topics:
                return selected
    return _extend_batch_with_discovery(frontier, selected, seen_ids, max_topics)


def _extend_batch_with_discovery(
    frontier: dict[str, Any],
    selected: list[dict[str, Any]],
    seen_ids: set[int],
    max_topics: int,
) -> list[dict[str, Any]]:
    discovery = frontier.get("discovery_queues", {})
    for item in discovery.get("comment-reference", []):
        if len(selected) >= max_topics:
            return selected
        batch_item = _batch_item_from_comment_reference(item)
        if not batch_item:
            continue
        item_id = _safe_int(batch_item.get("id"))
        if item_id is None or item_id in seen_ids:
            continue
        selected.append(batch_item)
        seen_ids.add(item_id)
    return selected


def _batch_item_from_comment_reference(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("target_type") != "linuxdo-topic":
        return None
    target_url = str(item.get("target_url", "")).strip()
    match = re.search(r"https://linux\.do/t/topic/(\d+)", target_url)
    if not match:
        return None
    topic_id = int(match.group(1))
    return {
        "id": topic_id,
        "title": item.get("title", ""),
        "url": target_url,
        "queue": "comment-reference",
        "surf_score": item.get("score", 0),
        "reason": item.get("reason", "评论引用扩展"),
    }


def _primary_queue_for_topic(topic: dict[str, Any], now: datetime) -> str:
    created_at = _topic_datetime(topic, "created_at")
    last_posted_at = _topic_datetime(topic, "last_posted_at") or _topic_datetime(topic, "bumped_at")
    if created_at and last_posted_at:
        topic_age_days = (now - created_at).days
        active_age_days = (now - last_posted_at).days
        if topic_age_days >= 30 and active_age_days <= 14:
            return "active-old"
    views = _safe_int(topic.get("views")) or 0
    replies = _safe_int(topic.get("reply_count")) or 0
    if views <= 500 and replies <= 10:
        return "low-traffic"
    return "new"


def _frontier_item(topic: dict[str, Any], queue_name: str) -> dict[str, Any]:
    topic_id = _safe_int(topic.get("id")) or 0
    return {
        "id": topic_id,
        "title": topic.get("title", ""),
        "url": topic.get("url") or f"https://linux.do/t/topic/{topic_id}",
        "queue": queue_name,
        "surf_score": topic.get("surf_score", 0),
        "reason": _queue_reason(queue_name),
        "created_at": topic.get("created_at", ""),
        "last_posted_at": topic.get("last_posted_at") or topic.get("bumped_at", ""),
        "views": _safe_int(topic.get("views")) or 0,
        "reply_count": _safe_int(topic.get("reply_count")) or 0,
    }


def _queue_reason(queue_name: str) -> str:
    reasons = {
        "new": "新帖或近期候选",
        "active-old": "老帖近期活跃，需要结合历史上下文阅读",
        "low-traffic": "低流量但可能有价值，保留探索预算",
    }
    return reasons.get(queue_name, queue_name)


def _keywords_for(mode: str, query: str, skill_names: list[str]) -> list[str]:
    words: list[str] = []
    if query:
        words.extend(_split_terms(query))
    if mode in DEFAULT_KEYWORDS:
        words.extend(DEFAULT_KEYWORDS[mode])
    if mode == "skill-feedback":
        words.extend(skill_names)
        words.extend(["skill", "skills", "推荐", "吐槽", "对比", "替代"])
    return _unique([word for word in words if word])


def _topic_score(topic: dict[str, Any], keywords: list[str]) -> float:
    title = str(topic.get("title", ""))
    text = " ".join(
        [
            title,
            str(topic.get("first_text", "")),
            " ".join(str(tag) for tag in topic.get("tags", []) or []),
        ]
    ).lower()
    score = 0.0
    for keyword in keywords:
        key = keyword.lower()
        if not key:
            continue
        if key in title.lower():
            score += 10
        elif key in text:
            score += 4
    score += min(float(topic.get("like_count", 0) or 0), 50) / 5
    score += min(float(topic.get("reply_count", 0) or 0), 100) / 10
    score += min(float(topic.get("views", 0) or 0), 10000) / 2000
    return score


def _split_terms(text: str) -> list[str]:
    return [part for part in re.split(r"[\s,，、/]+", text.strip()) if part]


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


DEFAULT_STATE = {"read_topic_ids": [], "synced_skill_names": []}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_STATE)
    data = json.loads(path.read_text(encoding="utf-8"))
    return _normalize_state(data)


def save_state(path: Path, state: dict[str, Any]) -> None:
    normalized = _normalize_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def build_browser_task(
    mode: str,
    query: str,
    candidates: list[dict[str, Any]],
    skill_names: list[str],
    max_topics: int,
    max_replies: int,
    control_channel: str = DEFAULT_CONTROL_CHANNEL,
) -> dict[str, Any]:
    mode = validate_mode(mode)
    control_channel = validate_channel(control_channel)
    return {
        "mode": mode,
        "control_channel": control_channel,
        "query": query,
        "skill_names": skill_names,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "budget": {"max_topics": max_topics, "max_replies_per_topic": max_replies},
        "instructions": _browser_instructions(mode, control_channel),
        "candidates": [
            {
                "id": _safe_int(item.get("id")) or 0,
                "title": item.get("title", ""),
                "url": item.get("url") or f"https://linux.do/t/topic/{item.get('id')}",
                "surf_score": item.get("surf_score", 0),
            }
            for item in candidates[:max_topics]
        ],
    }


def build_goal_task(
    mode: str,
    query: str,
    frontier_path: Path,
    state_path: Path,
    output_path: Path,
    next_batch: list[dict[str, Any]],
    max_topics: int,
    max_replies: int,
) -> dict[str, Any]:
    mode = validate_mode(mode)
    return {
        "mode": mode,
        "control_channel": "mac-goal",
        "query": query,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "frontier_queue": str(frontier_path),
        "state": str(state_path),
        "output": str(output_path),
        "budget": {"max_topics": max_topics, "max_replies_per_topic": max_replies},
        "stop_conditions": [
            "next_batch 为空",
            "达到本轮深读预算",
            "连续批次没有发现高价值候选",
        ],
        "instructions": _goal_instructions(mode),
        "next_batch": next_batch,
    }


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    read_ids = sorted({int(item) for item in state.get("read_topic_ids", []) if str(item).strip().isdigit()})
    synced_names = _unique([str(item).strip() for item in state.get("synced_skill_names", []) if str(item).strip()])
    return {"read_topic_ids": read_ids, "synced_skill_names": synced_names}


def _browser_instructions(mode: str, control_channel: str) -> str:
    channel_notes = {
        "codex-browser": "请使用 Codex 内置浏览器打开候选 Linux.do 帖子。首次需要登录时请让用户完成登录，后续复用已保存登录态。",
        "user-chrome": "请使用用户本机 Chrome 中已经打开或按标签组整理的 Linux.do 帖子，理解标签组和页面之间的关系；不要把这个通道当作全站搜索。",
        "mac-goal": "这是 /goal 长任务执行形态，不是独立阅读通道；仍需使用 Codex 内置浏览器读取 Linux.do。执行前必须明确停止标准、预算和阶段汇报，不要假装能无限后台冲浪。",
    }
    return (
        channel_notes[control_channel]
        + "读取首帖和高价值回复，区分事实、观点、争议和行动建议。"
        + f"当前模式：{mode}。不要生成固定日报，只输出本轮任务结果。"
    )


def _goal_instructions(mode: str) -> str:
    return (
        "用于 /goal 长任务：仍必须使用 Codex 内置浏览器按 next_batch 逐帖阅读 Linux.do，保存每帖摘要、关键证据、工具名、作者、"
        "高价值回复和可继续扩展的引用。活跃老帖必须阅读首帖、关键历史回复和近期回复，不要只看最新回复。"
        f"当前模式：{mode}。完成停止条件后调用 session 记录本轮结果。"
    )


def build_mode_result(task: dict[str, Any], readings: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for reading in readings:
        reading_id = _safe_int(reading.get("id")) or 0
        items.append(
            {
                "id": reading_id,
                "title": reading.get("title", ""),
                "url": reading.get("url", ""),
                "summary": reading.get("summary", ""),
                "positive_feedback": reading.get("positive_feedback", []),
                "negative_feedback": reading.get("negative_feedback", []),
                "risk_notes": reading.get("risk_notes", []),
                "tools": reading.get("tools", []),
                "action_items": reading.get("action_items", []),
                "author": reading.get("author", ""),
                "first_post": reading.get("first_post", ""),
                "historical_replies": reading.get("historical_replies", []),
                "recent_replies": reading.get("recent_replies", []),
                "high_value_replies": reading.get("high_value_replies", []),
                "follow_up_links": reading.get("follow_up_links", []),
                "confidence": reading.get("confidence", ""),
            }
        )
    mode = str(task.get("mode", ""))
    return {
        "mode": mode,
        "query": task.get("query", ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "read_topic_ids": sorted({item["id"] for item in items if item["id"]}),
        "mode_summary": _mode_summary(mode, str(task.get("query", "")), items),
        "items": items,
    }


def build_session_record(task: dict[str, Any], readings: list[dict[str, Any]], stop_reason: str) -> dict[str, Any]:
    mode = validate_mode(str(task.get("mode", "")))
    result = build_mode_result(task, readings)
    return {
        "mode": mode,
        "query": task.get("query", ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "stop_reason": stop_reason,
        "read_topic_ids": result["read_topic_ids"],
        "items": result["items"],
        "mode_summary": result["mode_summary"],
        "discovery_queues": extract_discovery_items(readings),
    }


def build_skill_evidence_package(skill_names: list[str], readings: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = []
    for skill_name in skill_names:
        matched = [reading for reading in readings if _mentions_skill(reading, skill_name)]
        if not matched:
            continue
        evidence.append(
            {
                "skill_name": skill_name,
                "topic_links": _unique([str(item.get("url", "")) for item in matched if item.get("url")]),
                "positive_feedback": _flatten_unique(matched, "positive_feedback"),
                "negative_feedback": _flatten_unique(matched, "negative_feedback"),
                "comparison_notes": _flatten_unique(matched, "comparison_notes"),
                "risk_notes": _flatten_unique(matched, "risk_notes") or _flatten_unique(matched, "negative_feedback"),
                "trial_recommendation": _trial_recommendation(matched),
                "sync_target": "community/skill_reviews.json",
            }
        )
    return {"created_at": datetime.now().isoformat(timespec="seconds"), "evidence": evidence}


def extract_discovery_items(readings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    discovery = {name: [] for name in DISCOVERY_QUEUE_NAMES}
    for reading in readings:
        _add_author_discovery(discovery, reading)
        _add_tool_discovery(discovery, reading)
        _add_reference_discovery(discovery, reading)
    return {
        "author-tracking": _merge_author_discovery(discovery["author-tracking"]),
        "comment-reference": _dedupe_discovery_items(discovery["comment-reference"]),
        "tool-lookup": _merge_tool_discovery(discovery["tool-lookup"]),
        "skill-workflow-evidence": _dedupe_discovery_items(discovery["skill-workflow-evidence"]),
    }


def _add_author_discovery(discovery: dict[str, list[dict[str, Any]]], reading: dict[str, Any]) -> None:
    username = str(reading.get("author", "")).strip()
    if not username:
        return
    topic_id = _safe_int(reading.get("id")) or 0
    discovery["author-tracking"].append(
        {
            "username": username,
            "profile_url": f"https://linux.do/u/{username}",
            "source_topic_ids": [topic_id] if topic_id else [],
            "reason": "在高价值阅读结果中出现，适合追踪作者后续帖子",
            "score": 1,
            "last_seen_at": datetime.now().isoformat(timespec="seconds"),
            "cooldown_until": "",
        }
    )


def _add_tool_discovery(discovery: dict[str, list[dict[str, Any]]], reading: dict[str, Any]) -> None:
    names = _extract_tool_names(reading)
    if not names:
        return
    topic_id = _safe_int(reading.get("id")) or 0
    source_url = str(reading.get("url", "")).strip()
    positive_count = len(_field_as_list(reading.get("positive_feedback", [])))
    negative_count = len(_field_as_list(reading.get("negative_feedback", []))) + len(_field_as_list(reading.get("risk_notes", [])))
    for name in names:
        discovery["tool-lookup"].append(
            {
                "name": name,
                "aliases": [],
                "source_topic_ids": [topic_id] if topic_id else [],
                "source_urls": [source_url] if source_url else [],
                "category": "unknown",
                "evidence_count": 1,
                "positive_count": positive_count,
                "negative_count": negative_count,
                "score": 1 + positive_count - negative_count,
            }
        )


def _add_reference_discovery(discovery: dict[str, list[dict[str, Any]]], reading: dict[str, Any]) -> None:
    source_topic_id = _safe_int(reading.get("id")) or 0
    for target_url in _linuxdo_topic_urls(reading.get("follow_up_links", [])):
        discovery["comment-reference"].append(_reference_item(target_url, source_topic_id, 0, "", "reading follow_up_links 标记了后续延展帖子"))
    replies = reading.get("high_value_replies", []) or []
    for reply in replies:
        if not isinstance(reply, dict):
            continue
        urls = _linuxdo_topic_urls([str(reply.get("text", ""))] + _field_as_list(reply.get("links", [])))
        for target_url in urls:
            discovery["comment-reference"].append(
                _reference_item(
                    target_url,
                    source_topic_id,
                    _safe_int(reply.get("id")) or 0,
                    reply.get("author", ""),
                    "高价值回复引用了相关帖子，需要扩展阅读上下文",
                )
            )


def _linuxdo_topic_urls(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    urls: list[str] = []
    for value in values:
        urls.extend(re.findall(r"https://linux\.do/t/topic/\d+", str(value)))
    return _unique(urls)


def _reference_item(target_url: str, source_topic_id: int, source_reply_id: int, source_author: str, reason: str) -> dict[str, Any]:
    return {
        "target_url": target_url,
        "target_type": "linuxdo-topic",
        "source_topic_id": source_topic_id,
        "source_reply_id": source_reply_id,
        "source_author": source_author,
        "reason": reason,
        "score": 1,
        "depth": 1,
    }


def _extract_tool_names(reading: dict[str, Any]) -> list[str]:
    explicit = reading.get("tools", []) or []
    if isinstance(explicit, str):
        explicit = [explicit]
    names = [str(name).strip() for name in explicit]
    summary = str(reading.get("summary", ""))
    names.extend(re.findall(r"(?<![A-Za-z0-9_-])([A-Za-z][A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)(?![A-Za-z0-9_-])", summary))
    names.extend(re.findall(r"(?<![A-Za-z0-9_-])([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})(?![A-Za-z0-9_-])", summary))
    return _unique([name for name in names if _is_useful_tool_name(name)])


def _is_useful_tool_name(name: str) -> bool:
    stripped = name.strip()
    return len(stripped) >= 3 and any(char.isalpha() for char in stripped)


def _dedupe_discovery_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = (
            item.get("username")
            or item.get("target_url")
            or item.get("name")
            or json.dumps(item, ensure_ascii=False, sort_keys=True)
        )
        normalized = str(key).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
    return result


def _merge_author_discovery(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        username = str(item.get("username", "")).strip()
        if not username:
            continue
        key = username.lower()
        if key not in merged:
            merged[key] = {**item, "source_topic_ids": list(item.get("source_topic_ids", [])), "score": 0}
        merged[key]["source_topic_ids"] = _merge_int_lists(
            merged[key].get("source_topic_ids", []),
            item.get("source_topic_ids", []),
        )
        merged[key]["score"] = len(merged[key]["source_topic_ids"]) or 1
    return list(merged.values())


def _merge_tool_discovery(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key not in merged:
            merged[key] = {
                **item,
                "source_topic_ids": [],
                "source_urls": [],
                "evidence_count": 0,
                "positive_count": 0,
                "negative_count": 0,
                "score": 0,
            }
        target = merged[key]
        target["source_topic_ids"] = _merge_int_lists(target.get("source_topic_ids", []), item.get("source_topic_ids", []))
        target["source_urls"] = _unique(
            [str(url) for url in target.get("source_urls", []) + item.get("source_urls", []) if str(url).strip()]
        )
        target["evidence_count"] += int(item.get("evidence_count", 0) or 0)
        target["positive_count"] += int(item.get("positive_count", 0) or 0)
        target["negative_count"] += int(item.get("negative_count", 0) or 0)
        target["score"] = target["evidence_count"] + target["positive_count"] - target["negative_count"]
    return list(merged.values())


def _merge_int_lists(first: list[Any], second: list[Any]) -> list[int]:
    values = []
    for value in first + second:
        parsed = _safe_int(value)
        if parsed is not None:
            values.append(parsed)
    return sorted(set(values))


def _field_as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _mentions_skill(reading: dict[str, Any], skill_name: str) -> bool:
    haystack = " ".join(
        [
            str(reading.get("title", "")),
            str(reading.get("summary", "")),
            " ".join(str(item) for item in reading.get("tools", []) or []),
        ]
    ).lower()
    name = skill_name.lower().strip()
    if not name:
        return False
    pattern = rf"(?<![a-z0-9_-]){re.escape(name)}(?![a-z0-9_-])"
    return re.search(pattern, haystack) is not None


def _flatten_unique(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        raw = item.get(field, [])
        if isinstance(raw, str):
            raw = [raw]
        values.extend(str(value) for value in raw if str(value).strip())
    return _unique(values)


def _trial_recommendation(readings: list[dict[str, Any]]) -> str:
    negatives = _flatten_unique(readings, "negative_feedback") + _flatten_unique(readings, "risk_notes")
    positives = _flatten_unique(readings, "positive_feedback")
    if positives and not negatives:
        return "建议试用"
    if positives and negatives:
        return "可小范围试用，注意风险"
    return "仅记录证据，暂不建议启用"


def load_topics(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        topics = data.get("topics", [])
        return topics if isinstance(topics, list) else []
    return []


def load_readings(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        readings = data.get("readings") or data.get("topics") or []
        return readings if isinstance(readings, list) else []
    return []


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_frontier(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def merge_discovery_into_frontier(path: Path, discovery: dict[str, list[dict[str, Any]]]) -> None:
    frontier = load_frontier(path)
    if not frontier:
        frontier = {"queues": {name: [] for name in PRIMARY_QUEUE_NAMES}, "discovery_queues": {}, "quotas": dict(DEFAULT_QUEUE_QUOTAS)}
    discovery_queues = frontier.setdefault("discovery_queues", {})
    for name in DISCOVERY_QUEUE_NAMES:
        existing = discovery_queues.get(name, [])
        incoming = discovery.get(name, [])
        combined = existing + incoming
        if name == "author-tracking":
            discovery_queues[name] = _merge_author_discovery(combined)
        elif name == "tool-lookup":
            discovery_queues[name] = _merge_tool_discovery(combined)
        else:
            discovery_queues[name] = _dedupe_discovery_items(combined)
    write_json(path, frontier)


def preserve_discovery_queues(frontier: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    previous_discovery = previous.get("discovery_queues", {}) if isinstance(previous, dict) else {}
    if not isinstance(previous_discovery, dict):
        return frontier
    current_discovery = frontier.get("discovery_queues", {})
    merged = {name: current_discovery.get(name, []) for name in DISCOVERY_QUEUE_NAMES}
    for name in DISCOVERY_QUEUE_NAMES:
        combined = previous_discovery.get(name, []) + merged.get(name, [])
        if name == "author-tracking":
            merged[name] = _merge_author_discovery(combined)
        elif name == "tool-lookup":
            merged[name] = _merge_tool_discovery(combined)
        else:
            merged[name] = _dedupe_discovery_items(combined)
    frontier["discovery_queues"] = merged
    return frontier


def run_plan(args: argparse.Namespace) -> int:
    _validate_positive("max-topics", args.max_topics)
    _validate_positive("max-replies", args.max_replies)
    state = load_state(args.state)
    topics = load_topics(args.topics)
    skill_names = _split_cli_values(args.skills)
    if args.mode == "skill-feedback" and not skill_names:
        raise SystemExit(2)
    candidates = rank_topics(
        topics,
        mode=args.mode,
        query=args.query,
        skill_names=skill_names,
        read_ids=set(state["read_topic_ids"]),
        limit=args.max_topics,
    )
    task = build_browser_task(
        args.mode,
        args.query,
        candidates,
        skill_names,
        args.max_topics,
        args.max_replies,
        args.channel,
    )
    write_json(args.output / f"browser_task_{args.mode}.json", task)
    save_state(args.state, state)
    return 0


def run_goal_plan(args: argparse.Namespace) -> int:
    _validate_positive("max-topics", args.max_topics)
    _validate_positive("max-replies", args.max_replies)
    _validate_positive("max-candidates", args.max_candidates)
    state = load_state(args.state)
    topics = load_topics(args.topics)
    skill_names = _split_cli_values(args.skills)
    if args.mode == "skill-feedback" and not skill_names:
        raise SystemExit(2)
    previous_frontier = load_frontier(args.queue)
    frontier = build_frontier_queue(
        topics,
        mode=args.mode,
        query=args.query,
        skill_names=skill_names,
        read_ids=set(state["read_topic_ids"]),
        max_candidates=args.max_candidates,
    )
    frontier = preserve_discovery_queues(frontier, previous_frontier)
    next_batch = select_next_batch(frontier, args.max_topics)
    task = build_goal_task(
        args.mode,
        args.query,
        args.queue,
        args.state,
        args.output,
        next_batch,
        args.max_topics,
        args.max_replies,
    )
    write_json(args.queue, frontier)
    write_json(args.output / f"goal_task_{args.mode}.json", task)
    save_state(args.state, state)
    return 0


def run_evidence(args: argparse.Namespace) -> int:
    skill_names = _split_cli_values(args.skills)
    readings = load_readings(args.readings)
    package = build_skill_evidence_package(skill_names, readings)
    write_json(args.output / "skill_evidence_package.json", package)
    if args.state:
        state = load_state(args.state)
        state["synced_skill_names"] = state["synced_skill_names"] + [item["skill_name"] for item in package["evidence"]]
        save_state(args.state, state)
    return 0


def run_result(args: argparse.Namespace) -> int:
    task = json.loads(args.task.read_text(encoding="utf-8"))
    readings = _filter_readings_to_task(load_readings(args.readings), task)
    result = build_mode_result(task, readings)
    mode = validate_mode(result["mode"])
    write_json(args.output / f"mode_result_{mode}.json", result)
    state = load_state(args.state)
    state["read_topic_ids"] = state["read_topic_ids"] + result["read_topic_ids"]
    save_state(args.state, state)
    return 0


def run_session(args: argparse.Namespace) -> int:
    task = json.loads(args.task.read_text(encoding="utf-8"))
    readings = _filter_readings_to_task(load_readings(args.readings), task)
    session = build_session_record(task, readings, args.stop_reason)
    mode = validate_mode(session["mode"])
    write_json(_next_session_path(args.output, mode), session)
    state = load_state(args.state)
    state["read_topic_ids"] = state["read_topic_ids"] + session["read_topic_ids"]
    save_state(args.state, state)
    frontier_path = str(task.get("frontier_queue", "")).strip()
    if frontier_path:
        merge_discovery_into_frontier(Path(frontier_path), session["discovery_queues"])
    return 0


def _next_session_path(output: Path, mode: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    path = output / f"session_{mode}_{stamp}.json"
    suffix = 1
    while path.exists():
        path = output / f"session_{mode}_{stamp}_{suffix}.json"
        suffix += 1
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Linux.do 任务型冲浪工具。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="生成 Codex 内置浏览器阅读任务包。")
    plan.add_argument("--mode", required=True, choices=sorted(MODES))
    plan.add_argument("--channel", choices=sorted(CONTROL_CHANNELS), default=DEFAULT_CONTROL_CHANNEL)
    plan.add_argument("--query", default="")
    plan.add_argument("--skills", nargs="*", default=[])
    plan.add_argument("--topics", type=Path, default=Path("output/linuxdo_skill_research/topic_details_top220.json"))
    plan.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    plan.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
    plan.add_argument("--max-topics", type=int, default=10)
    plan.add_argument("--max-replies", type=int, default=8)
    plan.set_defaults(func=run_plan)

    goal_plan = subparsers.add_parser("goal-plan", help="生成 Mac /goal 持续冲浪任务包。")
    goal_plan.add_argument("--mode", required=True, choices=sorted(MODES))
    goal_plan.add_argument("--query", default="")
    goal_plan.add_argument("--skills", nargs="*", default=[])
    goal_plan.add_argument("--topics", type=Path, default=Path("output/linuxdo_skill_research/topic_details_top220.json"))
    goal_plan.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    goal_plan.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
    goal_plan.add_argument("--queue", type=Path, default=Path("state/linuxdo_frontier_queue.json"))
    goal_plan.add_argument("--max-candidates", type=int, default=80)
    goal_plan.add_argument("--max-topics", type=int, default=12)
    goal_plan.add_argument("--max-replies", type=int, default=8)
    goal_plan.set_defaults(func=run_goal_plan)

    evidence = subparsers.add_parser("evidence", help="从阅读结果生成 skill 管理证据包。")
    evidence.add_argument("--skills", nargs="+", required=True)
    evidence.add_argument("--readings", type=Path, required=True)
    evidence.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    evidence.add_argument("--state", type=Path)
    evidence.set_defaults(func=run_evidence)

    result = subparsers.add_parser("result", help="保存本轮阅读结果，并更新已读状态。")
    result.add_argument("--task", type=Path, required=True)
    result.add_argument("--readings", type=Path, required=True)
    result.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    result.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
    result.set_defaults(func=run_result)

    session = subparsers.add_parser("session", help="保存 /goal 长任务阅读会话，并更新发现队列和已读状态。")
    session.add_argument("--task", type=Path, required=True)
    session.add_argument("--readings", type=Path, required=True)
    session.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    session.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
    session.add_argument("--stop-reason", required=True)
    session.set_defaults(func=run_session)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.mode = validate_mode(args.mode) if hasattr(args, "mode") else ""
    args.channel = validate_channel(args.channel) if hasattr(args, "channel") else ""
    return args.func(args)


def _split_cli_values(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        result.extend(_split_terms(value))
    return _unique(result)


def _mode_summary(mode: str, query: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    if mode == "research":
        return {
            "research_focus": query,
            "worth_reading": [item["title"] for item in items if item.get("summary")],
            "action_items": _flatten_items(items, "action_items"),
        }
    if mode == "goldmine":
        return {
            "worth_deep_reading": [item["title"] for item in items if item.get("summary")],
            "no_action_yet": [item["title"] for item in items if not item.get("action_items")],
            "follow_up_candidates": _flatten_items(items, "tools"),
        }
    if mode == "skill-feedback":
        return {
            "skills_with_feedback": _flatten_items(items, "tools"),
            "positive_feedback": _flatten_items(items, "positive_feedback"),
            "negative_feedback": _flatten_items(items, "negative_feedback"),
        }
    if mode == "discover":
        candidates = _flatten_items(items, "tools")
        return {
            "new_candidates": candidates,
            "needs_github_verification": candidates,
            "possible_overlap_or_conflict": _flatten_items(items, "risk_notes"),
        }
    return {}


def _flatten_items(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        raw = item.get(field, [])
        if isinstance(raw, str):
            raw = [raw]
        values.extend(str(value) for value in raw if str(value).strip())
    return _unique(values)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_datetime(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _topic_datetime(topic: dict[str, Any], field: str) -> datetime | None:
    return _coerce_datetime(topic.get(field))


def _validate_positive(name: str, value: int) -> None:
    if value <= 0:
        raise SystemExit(2)


def _filter_readings_to_task(readings: list[dict[str, Any]], task: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = task.get("candidates") or task.get("next_batch") or []
    candidate_ids = {
        parsed
        for parsed in (_safe_int(item.get("id")) for item in candidates if isinstance(item, dict))
        if parsed is not None
    }
    if not candidate_ids:
        return readings
    return [reading for reading in readings if _safe_int(reading.get("id")) in candidate_ids]


if __name__ == "__main__":
    raise SystemExit(main())
