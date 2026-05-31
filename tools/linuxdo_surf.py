from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


MODES = {"research", "goldmine", "skill-feedback", "discover"}
CONTROL_CHANNELS = {"codex-browser", "user-chrome", "mac-goal"}
RESEARCH_STRATEGIES = {"linuxdo-only", "github-only", "linuxdo-first", "github-first"}
DEFAULT_CONTROL_CHANNEL = "codex-browser"
DEFAULT_RESEARCH_STRATEGY = "linuxdo-only"
PRIMARY_QUEUE_NAMES = ("new", "active-old", "low-traffic")
DISCOVERY_QUEUE_NAMES = (
    "author-tracking",
    "comment-reference",
    "tool-lookup",
    "skill-workflow-evidence",
    "github-repo-research",
    "github-search",
)
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


def validate_research_strategy(strategy: str) -> str:
    normalized = strategy.strip().lower()
    if normalized not in RESEARCH_STRATEGIES:
        raise ValueError(f"未知研究策略：{strategy}")
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


DEFAULT_STATE = {
    "read_topic_ids": [],
    "synced_skill_names": [],
    "reviewed_github_repos": [],
    "reviewed_github_searches": [],
    "render_checked_topic_ids": [],
}


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
    research_strategy: str = DEFAULT_RESEARCH_STRATEGY,
) -> dict[str, Any]:
    mode = validate_mode(mode)
    control_channel = validate_channel(control_channel)
    research_strategy = validate_research_strategy(research_strategy)
    return {
        "mode": mode,
        "control_channel": control_channel,
        "research_strategy": research_strategy,
        "query": query,
        "skill_names": skill_names,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "budget": {"max_topics": max_topics, "max_replies_per_topic": max_replies},
        "instructions": _browser_instructions(mode, control_channel, research_strategy),
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
    research_strategy: str = DEFAULT_RESEARCH_STRATEGY,
) -> dict[str, Any]:
    mode = validate_mode(mode)
    research_strategy = validate_research_strategy(research_strategy)
    return {
        "mode": mode,
        "control_channel": "mac-goal",
        "research_strategy": research_strategy,
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
        "instructions": _goal_instructions(mode, research_strategy),
        "next_batch": next_batch,
    }


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    read_ids = sorted({int(item) for item in state.get("read_topic_ids", []) if str(item).strip().isdigit()})
    synced_names = _unique([str(item).strip() for item in state.get("synced_skill_names", []) if str(item).strip()])
    reviewed_repos = _normalize_repo_list(state.get("reviewed_github_repos", []))
    reviewed_searches = _unique(
        [str(item).strip().lower() for item in state.get("reviewed_github_searches", []) if str(item).strip()]
    )
    render_checked_ids = sorted({int(item) for item in state.get("render_checked_topic_ids", []) if str(item).strip().isdigit()})
    return {
        "read_topic_ids": read_ids,
        "synced_skill_names": synced_names,
        "reviewed_github_repos": reviewed_repos,
        "reviewed_github_searches": reviewed_searches,
        "render_checked_topic_ids": render_checked_ids,
    }


def _browser_instructions(mode: str, control_channel: str, research_strategy: str) -> str:
    channel_notes = {
        "codex-browser": "请使用 Codex 内置浏览器打开候选 Linux.do 帖子。首次需要登录时请让用户完成登录，后续复用已保存登录态。",
        "user-chrome": "请使用用户本机 Chrome 中已经打开或按标签组整理的 Linux.do 帖子，理解标签组和页面之间的关系；不要把这个通道当作全站搜索。",
        "mac-goal": "这是 /goal 长任务执行形态，不是独立阅读通道；仍需使用 Codex 内置浏览器读取 Linux.do。执行前必须明确停止标准、预算和阶段汇报，不要假装能无限后台冲浪。",
    }
    strategy_notes = {
        "linuxdo-only": "研究策略：只使用 Linux.do，不自动进入 GitHub；如发现项目线索，只记录为可补深挖候选。",
        "linuxdo-first": "研究策略：Linux.do 为主；只把值得验证的项目、skill、插件、工具、workflow、repo 交给 GitHub 深挖。",
        "github-first": "研究策略：GitHub 为主；搜索 Linux.do 来补社区反馈，不做全站泛搜。",
        "github-only": "研究策略：该策略通常不生成 Linux.do 阅读任务；如出现此任务，只记录需要人工确认的社区反馈缺口。",
    }
    return (
        channel_notes[control_channel]
        + strategy_notes[research_strategy]
        + "读取首帖和高价值回复，区分事实、观点、争议和行动建议。"
        + f"当前模式：{mode}。不要生成固定日报，只输出本轮任务结果。"
    )


def _goal_instructions(mode: str, research_strategy: str) -> str:
    strategy_notes = {
        "linuxdo-only": "本轮只在 Linux.do 内持续冲浪；GitHub 线索只入队，留给 backfill-plan 或后续 github-plan。",
        "linuxdo-first": "Linux.do 为主持续冲浪；遇到值得验证的项目、skill、插件、工具、workflow、repo 时，再生成 GitHub 深挖任务。",
        "github-first": "GitHub 为主；本轮只补 Linux.do 社区反馈，不做 Linux.do 全站泛搜。",
        "github-only": "本策略通常不使用 /goal 阅读 Linux.do；若生成此任务，只记录社区反馈缺口。",
    }
    return (
        "用于 /goal 长任务：仍必须使用 Codex 内置浏览器按 next_batch 逐帖阅读 Linux.do，保存每帖摘要、关键证据、工具名、作者、"
        "高价值回复和可继续扩展的引用。活跃老帖必须阅读首帖、关键历史回复和近期回复，不要只看最新回复。"
        + strategy_notes[research_strategy]
        + f"当前模式：{mode}。完成停止条件后调用 session 记录本轮结果。"
    )


def build_mode_result(task: dict[str, Any], readings: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for reading in readings:
        reading_id = _safe_int(reading.get("id")) or 0
        visual_review = _visual_review_fields(reading)
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
                "github_repos": reading.get("github_repos", []),
                "confidence": reading.get("confidence", ""),
                **visual_review,
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


def _visual_review_fields(reading: dict[str, Any]) -> dict[str, Any]:
    explicit_needed = bool(reading.get("visual_evidence_needed", False))
    inferred_needed, inferred_reason, inferred_priority = infer_visual_review_need(reading)
    needed = explicit_needed or inferred_needed
    status = str(reading.get("visual_review_status") or ("needed" if needed else "not-needed"))
    return {
        "visual_evidence_needed": needed,
        "visual_reason": reading.get("visual_reason") or inferred_reason,
        "visual_review_priority": reading.get("visual_review_priority") or inferred_priority,
        "visual_review_status": status,
        "visual_review_notes": _field_as_list(reading.get("visual_review_notes", [])),
        "visual_assets": _field_as_list(reading.get("visual_assets", [])),
    }


def infer_visual_review_need(reading: dict[str, Any]) -> tuple[bool, str, str]:
    haystack = " ".join(
        [
            str(reading.get("title", "")),
            str(reading.get("summary", "")),
            str(reading.get("first_post", "")),
            " ".join(str(item) for item in _field_as_list(reading.get("tools", []))),
            " ".join(str(item) for item in _field_as_list(reading.get("action_items", []))),
        ]
    ).lower()
    high_keywords = [
        "ui",
        "webui",
        "web ui",
        "tui",
        "可视化",
        "状态栏",
        "卡片",
        "dashboard",
        "界面",
        "审美",
        "排版",
    ]
    medium_keywords = ["安装", "配置", "教程", "命令输出", "workflow", "工作流", "多 agent", "multi-agent", "编排"]
    asset_keywords = ["截图", "图片", "视频"]
    for keyword in high_keywords:
        if keyword in haystack:
            return True, f"命中视觉证据关键词：{keyword}", "high"
    for keyword in medium_keywords:
        if keyword in haystack:
            return True, f"命中教程/流程视觉关键词：{keyword}", "medium"
    for keyword in asset_keywords:
        if keyword in haystack:
            return True, f"命中视觉素材关键词：{keyword}", "high"
    return False, "", "low"


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


def build_github_task(
    mode: str,
    query: str,
    frontier_path: Path,
    next_repos: list[dict[str, Any]],
    next_searches: list[dict[str, Any]],
    max_repos: int,
    max_searches: int,
    research_strategy: str = "linuxdo-first",
) -> dict[str, Any]:
    mode = validate_mode(mode)
    research_strategy = validate_research_strategy(research_strategy)
    return {
        "mode": mode,
        "control_channel": "github-mcp",
        "research_strategy": research_strategy,
        "query": query,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "frontier_queue": str(frontier_path),
        "budget": {"max_repos": max_repos, "max_searches": max_searches},
        "instructions": _github_instructions(mode, research_strategy),
        "next_batch": {
            "repositories": next_repos[:max_repos],
            "searches": next_searches[:max_searches],
        },
    }


def build_visual_review_task(
    readings: list[dict[str, Any]],
    state: dict[str, Any],
    max_topics: int,
) -> dict[str, Any]:
    _validate_positive("max-topics", max_topics)
    checked_ids = set(state.get("render_checked_topic_ids", []))
    candidates = []
    for reading in readings:
        visual = _visual_review_fields(reading)
        reading_id = _safe_int(reading.get("id")) or 0
        if not visual["visual_evidence_needed"]:
            continue
        if visual["visual_review_status"] == "checked" or reading_id in checked_ids:
            continue
        candidates.append(
            {
                "id": reading_id,
                "title": reading.get("title", ""),
                "url": reading.get("url", ""),
                "summary": reading.get("summary", ""),
                "visual_reason": visual["visual_reason"],
                "visual_review_priority": visual["visual_review_priority"],
                "visual_assets": visual["visual_assets"],
            }
        )
    candidates.sort(key=lambda item: (_visual_priority_rank(item["visual_review_priority"]), item["id"]))
    return {
        "task_type": "visual-review",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "budget": {"max_topics": max_topics},
        "instructions": _visual_review_instructions(),
        "items": candidates[:max_topics],
    }


def _visual_review_instructions() -> str:
    return (
        "Use Codex browser to open each Linux.do rendered page with logged-in state. "
        "Do not treat existing JSON readings as proof that render review is complete. "
        "Check screenshots, images, videos, UI/WebUI/TUI, tutorial steps, command output, workflow diagrams, cards, layout, and aesthetic claims. "
        "Write findings back into visual_evidence_needed, visual_review_status, visual_review_notes, and visual_assets."
    )


def _visual_priority_rank(priority: str) -> int:
    ranks = {"high": 0, "medium": 1, "low": 2}
    return ranks.get(str(priority).lower(), 3)


def build_github_result(task: dict[str, Any], github_readings: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    allowed_repos = {
        repo
        for repo in (
            _normalize_repo_name(item.get("repo") or item.get("url"))
            for item in (task.get("next_batch", {}) or {}).get("repositories", [])
            if isinstance(item, dict)
        )
        if repo
    }
    allowed_searches = {
        str(item.get("query", "")).strip().lower()
        for item in (task.get("next_batch", {}) or {}).get("searches", [])
        if isinstance(item, dict) and str(item.get("query", "")).strip()
    }
    for reading in github_readings:
        repo = _normalize_repo_name(reading.get("repo") or reading.get("url"))
        if not repo:
            continue
        source_query = str(reading.get("source_query", "")).strip()
        if allowed_repos or allowed_searches:
            if repo not in allowed_repos and source_query.lower() not in allowed_searches:
                continue
        items.append(
            {
                "repo": repo,
                "url": reading.get("url") or f"https://github.com/{repo}",
                "source_query": source_query,
                "summary": reading.get("summary", ""),
                "stars": _safe_int(reading.get("stars")) or 0,
                "last_commit_at": reading.get("last_commit_at", ""),
                "positive_signals": _field_as_list(reading.get("positive_signals", [])),
                "negative_signals": _field_as_list(reading.get("negative_signals", [])),
                "risk_notes": _field_as_list(reading.get("risk_notes", [])),
                "related_repos": _field_as_list(reading.get("related_repos", [])),
                "related_tools": _field_as_list(reading.get("related_tools", [])),
                "recommendation": reading.get("recommendation", ""),
                "confidence": reading.get("confidence", ""),
            }
        )
    reviewed_searches = [
        str(item.get("query", "")).strip().lower()
        for item in (task.get("next_batch", {}) or {}).get("searches", [])
        if str(item.get("query", "")).strip()
    ]
    return {
        "mode": task.get("mode", ""),
        "query": task.get("query", ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reviewed_github_repos": [item["repo"] for item in items],
        "reviewed_github_searches": _unique(reviewed_searches),
        "items": items,
        "discovery_queues": extract_github_discovery_items(items),
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
        _add_github_discovery(discovery, reading)
    return {
        "author-tracking": _merge_author_discovery(discovery["author-tracking"]),
        "comment-reference": _dedupe_discovery_items(discovery["comment-reference"]),
        "tool-lookup": _merge_tool_discovery(discovery["tool-lookup"]),
        "skill-workflow-evidence": _dedupe_discovery_items(discovery["skill-workflow-evidence"]),
        "github-repo-research": _merge_github_repo_discovery(discovery["github-repo-research"]),
        "github-search": _merge_github_search_discovery(discovery["github-search"]),
    }


def extract_github_discovery_items(github_readings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    discovery = {name: [] for name in DISCOVERY_QUEUE_NAMES}
    for reading in github_readings:
        source_repo = _normalize_repo_name(reading.get("repo") or reading.get("url"))
        for repo in _github_repos_from_values(reading.get("related_repos", [])):
            discovery["github-repo-research"].append(
                _github_repo_item(
                    repo,
                    source_topic_id=0,
                    source_url=str(reading.get("url", "")),
                    source_repo=source_repo,
                    focus="GitHub 研究结果提到的相关仓库，需要继续确认维护状态、README、issues 和替代方案",
                    score=1,
                )
            )
        for tool in _field_as_list(reading.get("related_tools", [])):
            query = str(tool).strip()
            if query:
                discovery["github-search"].append(
                    _github_search_item(
                        query,
                        source_tool=query,
                        source_topic_id=0,
                        source_url=str(reading.get("url", "")),
                        score=1,
                    )
                )
    return {
        "author-tracking": [],
        "comment-reference": [],
        "tool-lookup": [],
        "skill-workflow-evidence": [],
        "github-repo-research": _merge_github_repo_discovery(discovery["github-repo-research"]),
        "github-search": _merge_github_search_discovery(discovery["github-search"]),
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


def _add_github_discovery(discovery: dict[str, list[dict[str, Any]]], reading: dict[str, Any]) -> None:
    topic_id = _safe_int(reading.get("id")) or 0
    source_url = str(reading.get("url", "")).strip()
    focus = _github_focus_from_reading(reading)
    values: list[Any] = [
        reading.get("url", ""),
        reading.get("summary", ""),
        reading.get("first_post", ""),
        reading.get("follow_up_links", []),
        reading.get("github_repos", []),
        reading.get("tools", []),
    ]
    for reply in reading.get("high_value_replies", []) or []:
        if isinstance(reply, dict):
            values.extend([reply.get("text", ""), reply.get("links", []), reply.get("tools", [])])
    for repo in _github_repos_from_values(values):
        discovery["github-repo-research"].append(
            _github_repo_item(repo, topic_id, source_url, "", focus, score=2)
        )
    for tool in _extract_tool_names(reading):
        discovery["github-search"].append(
            _github_search_item(tool, source_tool=tool, source_topic_id=topic_id, source_url=source_url, score=1)
        )


def _linuxdo_topic_urls(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    urls: list[str] = []
    for value in values:
        urls.extend(re.findall(r"https://linux\.do/t/topic/\d+", str(value)))
    return _unique(urls)


def _github_repos_from_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        values = [values]
    repos: list[str] = []
    for value in values:
        if isinstance(value, list):
            repos.extend(_github_repos_from_values(value))
            continue
        text = str(value)
        for owner, repo in re.findall(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text):
            repos.append(f"{owner}/{repo}")
        without_urls = re.sub(r"https?://\S+", " ", text)
        for candidate in re.findall(r"(?<![A-Za-z0-9_.-/])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?![A-Za-z0-9_.-/])", without_urls):
            if not candidate.lower().startswith(("http/", "https/")):
                repos.append(candidate)
    return _normalize_repo_list(repos)


def _normalize_repo_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        values = [values]
    repos = []
    for value in values:
        repo = _normalize_repo_name(value)
        if repo:
            repos.append(repo)
    return _unique(repos)


def _normalize_repo_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text)
    if match:
        text = f"{match.group(1)}/{match.group(2)}"
    text = text.strip().strip("/")
    parts = text.split("/")
    if len(parts) < 2:
        return ""
    owner, repo = parts[0], parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        return ""
    return f"{owner.lower()}/{repo.lower()}"


def _github_repo_item(
    repo: str,
    source_topic_id: int,
    source_url: str,
    source_repo: str,
    focus: str,
    score: int,
) -> dict[str, Any]:
    return {
        "repo": repo,
        "url": f"https://github.com/{repo}",
        "source_topic_ids": [source_topic_id] if source_topic_id else [],
        "source_urls": [source_url] if source_url else [],
        "source_repos": [source_repo] if source_repo else [],
        "focus": focus,
        "score": score,
        "depth": 1,
    }


def _github_search_item(query: str, source_tool: str, source_topic_id: int, source_url: str, score: int) -> dict[str, Any]:
    return {
        "query": query,
        "source_tool": source_tool,
        "source_topic_ids": [source_topic_id] if source_topic_id else [],
        "source_urls": [source_url] if source_url else [],
        "score": score,
        "depth": 1,
    }


def _github_focus_from_reading(reading: dict[str, Any]) -> str:
    signals = _field_as_list(reading.get("positive_feedback", [])) + _field_as_list(reading.get("risk_notes", []))
    if signals:
        return "；".join(str(item) for item in signals if str(item).strip())
    return "确认 README、最近提交、issue 活跃度、安装成本、替代方案和是否值得试用"


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


def _merge_github_repo_discovery(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        repo = _normalize_repo_name(item.get("repo") or item.get("url"))
        if not repo:
            continue
        if repo not in merged:
            merged[repo] = {
                **item,
                "repo": repo,
                "url": f"https://github.com/{repo}",
                "source_topic_ids": [],
                "source_urls": [],
                "source_repos": [],
                "score": 0,
            }
        target = merged[repo]
        target["source_topic_ids"] = _merge_int_lists(target.get("source_topic_ids", []), item.get("source_topic_ids", []))
        target["source_urls"] = _unique(
            [str(url) for url in target.get("source_urls", []) + item.get("source_urls", []) if str(url).strip()]
        )
        target["source_repos"] = _normalize_repo_list(target.get("source_repos", []) + item.get("source_repos", []))
        focus = str(item.get("focus", "")).strip()
        if focus and focus not in str(target.get("focus", "")):
            target["focus"] = (str(target.get("focus", "")).strip() + "；" + focus).strip("；")
        target["score"] += int(item.get("score", 0) or 0)
    return list(merged.values())


def _merge_github_search_discovery(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        query = str(item.get("query", "")).strip()
        if not query:
            continue
        key = query.lower()
        if key not in merged:
            merged[key] = {
                **item,
                "query": query,
                "source_topic_ids": [],
                "source_urls": [],
                "score": 0,
            }
        target = merged[key]
        target["source_topic_ids"] = _merge_int_lists(target.get("source_topic_ids", []), item.get("source_topic_ids", []))
        target["source_urls"] = _unique(
            [str(url) for url in target.get("source_urls", []) + item.get("source_urls", []) if str(url).strip()]
        )
        target["score"] += int(item.get("score", 0) or 0)
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
        readings = data.get("readings") or data.get("github_readings") or data.get("items") or data.get("topics") or []
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
        elif name == "github-repo-research":
            discovery_queues[name] = _merge_github_repo_discovery(combined)
        elif name == "github-search":
            discovery_queues[name] = _merge_github_search_discovery(combined)
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
        elif name == "github-repo-research":
            merged[name] = _merge_github_repo_discovery(combined)
        elif name == "github-search":
            merged[name] = _merge_github_search_discovery(combined)
        else:
            merged[name] = _dedupe_discovery_items(combined)
    frontier["discovery_queues"] = merged
    return frontier


def select_github_research_batch(
    frontier: dict[str, Any],
    state: dict[str, Any],
    max_repos: int,
    max_searches: int,
) -> dict[str, list[dict[str, Any]]]:
    _validate_positive("max-repos", max_repos)
    _validate_positive("max-searches", max_searches)
    discovery = frontier.get("discovery_queues", {}) if isinstance(frontier, dict) else {}
    reviewed_repos = set(_normalize_repo_list(state.get("reviewed_github_repos", [])))
    reviewed_searches = {
        str(item).strip().lower()
        for item in state.get("reviewed_github_searches", [])
        if str(item).strip()
    }

    repos = []
    for item in _merge_github_repo_discovery(discovery.get("github-repo-research", [])):
        repo = _normalize_repo_name(item.get("repo") or item.get("url"))
        if not repo or repo in reviewed_repos:
            continue
        repos.append({**item, "repo": repo, "url": f"https://github.com/{repo}"})
        if len(repos) >= max_repos:
            break

    searches = []
    for item in _merge_github_search_discovery(discovery.get("github-search", [])):
        query = str(item.get("query", "")).strip()
        if not query or query.lower() in reviewed_searches:
            continue
        searches.append({**item, "query": query})
        if len(searches) >= max_searches:
            break
    return {"repositories": repos, "searches": searches}


def select_github_research_batch_from_discovery(
    discovery: dict[str, list[dict[str, Any]]],
    state: dict[str, Any],
    max_repos: int,
    max_searches: int,
) -> dict[str, list[dict[str, Any]]]:
    frontier = {"discovery_queues": discovery}
    return select_github_research_batch(frontier, state, max_repos, max_searches)


def build_linuxdo_backfill_query(github_items: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for item in github_items:
        repo = _normalize_repo_name(item.get("repo") or item.get("url"))
        if repo:
            values.append(repo)
        values.extend(str(tool).strip() for tool in _field_as_list(item.get("related_tools", [])) if str(tool).strip())
        source_query = str(item.get("source_query", "")).strip()
        if source_query:
            values.append(source_query)
    return " ".join(_unique(values))


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
        args.strategy,
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
        args.strategy,
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
    state["render_checked_topic_ids"] = state["render_checked_topic_ids"] + _render_checked_ids(result["items"])
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
    state["render_checked_topic_ids"] = state["render_checked_topic_ids"] + _render_checked_ids(session["items"])
    save_state(args.state, state)
    frontier_path = str(task.get("frontier_queue", "")).strip()
    if frontier_path:
        merge_discovery_into_frontier(Path(frontier_path), session["discovery_queues"])
    return 0


def run_github_plan(args: argparse.Namespace) -> int:
    _validate_positive("max-repos", args.max_repos)
    _validate_positive("max-searches", args.max_searches)
    state = load_state(args.state)
    frontier = load_frontier(args.queue)
    if args.strategy == "github-only" and args.query.strip():
        batch = {
            "repositories": [],
            "searches": [
                {
                    "query": args.query.strip(),
                    "source_tool": args.query.strip(),
                    "source_topic_ids": [],
                    "source_urls": [],
                    "score": 1,
                    "depth": 1,
                }
            ],
        }
    else:
        batch = select_github_research_batch(frontier, state, args.max_repos, args.max_searches)
    task = build_github_task(
        args.mode,
        args.query,
        args.queue,
        batch["repositories"],
        batch["searches"],
        args.max_repos,
        args.max_searches,
        research_strategy=args.strategy,
    )
    write_json(args.output / f"github_task_{args.mode}.json", task)
    save_state(args.state, state)
    return 0


def run_backfill_plan(args: argparse.Namespace) -> int:
    source_platform = str(args.source_platform).strip().lower()
    readings = load_readings(args.input)
    if source_platform == "linuxdo":
        _validate_positive("max-repos", args.max_repos)
        _validate_positive("max-searches", args.max_searches)
        discovery = extract_discovery_items(readings)
        merge_discovery_into_frontier(args.queue, discovery)
        state = load_state(args.state)
        batch = select_github_research_batch_from_discovery(discovery, state, args.max_repos, args.max_searches)
        task = build_github_task(
            args.mode,
            "",
            args.queue,
            batch["repositories"],
            batch["searches"],
            args.max_repos,
            args.max_searches,
            research_strategy="linuxdo-first",
        )
        task["backfill_source"] = "linuxdo"
        write_json(args.output / f"github_task_{args.mode}.json", task)
        save_state(args.state, state)
        return 0

    if source_platform == "github":
        _validate_positive("max-topics", args.max_topics)
        query = build_linuxdo_backfill_query(readings)
        topics = load_topics(args.topics)
        candidates = rank_topics(topics, mode=args.mode, query=query, limit=args.max_topics) if query else []
        task = build_browser_task(
            args.mode,
            query,
            candidates=candidates,
            skill_names=[],
            max_topics=args.max_topics,
            max_replies=8,
            research_strategy="github-first",
        )
        task["backfill_source"] = "github"
        write_json(args.output / f"browser_task_{args.mode}.json", task)
        return 0

    raise SystemExit(2)


def run_visual_review_plan(args: argparse.Namespace) -> int:
    readings = load_readings(args.input)
    state = load_state(args.state)
    task = build_visual_review_task(readings, state, args.max_topics)
    write_json(args.output / "visual_review_task.json", task)
    save_state(args.state, state)
    return 0


def run_github_result(args: argparse.Namespace) -> int:
    task = json.loads(args.task.read_text(encoding="utf-8"))
    github_readings = load_readings(args.readings)
    result = build_github_result(task, github_readings)
    mode = validate_mode(str(result["mode"]))
    write_json(args.output / f"github_result_{mode}.json", result)
    state = load_state(args.state)
    state["reviewed_github_repos"] = state["reviewed_github_repos"] + result["reviewed_github_repos"]
    state["reviewed_github_searches"] = state["reviewed_github_searches"] + result["reviewed_github_searches"]
    save_state(args.state, state)
    frontier_path = str(task.get("frontier_queue", "")).strip()
    if frontier_path:
        merge_discovery_into_frontier(Path(frontier_path), result["discovery_queues"])
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
    plan.add_argument("--strategy", choices=sorted(RESEARCH_STRATEGIES), default=DEFAULT_RESEARCH_STRATEGY)
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
    goal_plan.add_argument("--strategy", choices=sorted(RESEARCH_STRATEGIES), default=DEFAULT_RESEARCH_STRATEGY)
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

    github_plan = subparsers.add_parser("github-plan", help="从发现队列生成 GitHub 深挖任务包。")
    github_plan.add_argument("--mode", required=True, choices=sorted(MODES))
    github_plan.add_argument("--strategy", choices=sorted(RESEARCH_STRATEGIES), default="linuxdo-first")
    github_plan.add_argument("--query", default="")
    github_plan.add_argument("--queue", type=Path, default=Path("state/linuxdo_frontier_queue.json"))
    github_plan.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    github_plan.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
    github_plan.add_argument("--max-repos", type=int, default=8)
    github_plan.add_argument("--max-searches", type=int, default=5)
    github_plan.set_defaults(func=run_github_plan)

    github_result = subparsers.add_parser("github-result", help="保存 GitHub 深挖结果，并把相关仓库和搜索词回流发现队列。")
    github_result.add_argument("--task", type=Path, required=True)
    github_result.add_argument("--readings", type=Path, required=True)
    github_result.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    github_result.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
    github_result.set_defaults(func=run_github_result)

    backfill_plan = subparsers.add_parser("backfill-plan", help="从单平台结果生成另一平台补深挖任务包。")
    backfill_plan.add_argument("--source-platform", required=True, choices=["linuxdo", "github"])
    backfill_plan.add_argument("--mode", required=True, choices=sorted(MODES))
    backfill_plan.add_argument("--input", type=Path, required=True)
    backfill_plan.add_argument("--topics", type=Path, default=Path("output/linuxdo_skill_research/topic_details_top220.json"))
    backfill_plan.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    backfill_plan.add_argument("--queue", type=Path, default=Path("state/linuxdo_frontier_queue.json"))
    backfill_plan.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
    backfill_plan.add_argument("--max-repos", type=int, default=8)
    backfill_plan.add_argument("--max-searches", type=int, default=5)
    backfill_plan.add_argument("--max-topics", type=int, default=10)
    backfill_plan.set_defaults(func=run_backfill_plan)

    visual_review_plan = subparsers.add_parser("visual-review-plan", help="从阅读结果生成需要渲染页回看的任务包。")
    visual_review_plan.add_argument("--input", type=Path, required=True)
    visual_review_plan.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    visual_review_plan.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
    visual_review_plan.add_argument("--max-topics", type=int, default=10)
    visual_review_plan.set_defaults(func=run_visual_review_plan)

    return parser


def _github_instructions(mode: str, research_strategy: str) -> str:
    strategy_notes = {
        "linuxdo-only": "研究策略：通常不需要 GitHub；若生成此任务，只处理 Linux.do 已明确留下的补验证线索。",
        "linuxdo-first": "研究策略：Linux.do 为主，GitHub 只负责验证和延展已发现的项目线索。",
        "github-first": "研究策略：GitHub 为主；本轮先找项目证据，后续再用 Linux.do 补社区反馈。",
        "github-only": "研究策略：只使用 GitHub，不自动回到 Linux.do；如需要社区反馈，另行生成 backfill-plan。",
    }
    role_notes = {
        "github-only": "本任务可直接从用户 query 或指定仓库开始，不需要先有 Linux.do 线索。",
    }
    default_role_note = "GitHub 在本策略中作为项目、skill、插件、工具和工作流线索的验证与延展源。"
    return (
        "请使用 GitHub MCP 或 GitHub 官方页面深挖 next_batch 中的仓库和搜索词；"
        + strategy_notes[research_strategy]
        + role_notes.get(research_strategy, default_role_note)
        + "每个仓库至少检查 README/描述、最近提交或 release、issue/PR 活跃度、安装或使用成本、与现有工具的重叠、风险和替代方案。"
        + "搜索词应返回值得继续看的仓库候选，不要只按 stars 排序；优先实际可用、近期活跃、与 AI coding/workflow/skill/plugin/MCP 相关的项目。"
        + f"当前模式：{mode}。输出 github_readings JSON，保留推荐等级、confidence、related_repos 和 related_tools。"
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.mode = validate_mode(args.mode) if hasattr(args, "mode") else ""
    args.channel = validate_channel(args.channel) if hasattr(args, "channel") else ""
    args.strategy = validate_research_strategy(args.strategy) if hasattr(args, "strategy") else ""
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


def _render_checked_ids(items: list[dict[str, Any]]) -> list[int]:
    return [
        item_id
        for item_id in (_safe_int(item.get("id")) for item in items if item.get("visual_review_status") == "checked")
        if item_id is not None
    ]


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
