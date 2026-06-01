from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.linuxdo_knowledge.config import load_config
from tools.linuxdo_knowledge.bookmarks import sync_bookmarks
from tools.linuxdo_knowledge.state import ensure_knowledge_state


MODES = {"research", "goldmine", "skill-feedback", "discover"}
CONTROL_CHANNELS = {"codex-browser", "user-chrome", "mac-goal", "computer-use"}
DEFAULT_CONTROL_CHANNEL = "codex-browser"
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


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    read_ids = sorted({int(item) for item in state.get("read_topic_ids", []) if str(item).strip().isdigit()})
    synced_names = _unique([str(item).strip() for item in state.get("synced_skill_names", []) if str(item).strip()])
    return {"read_topic_ids": read_ids, "synced_skill_names": synced_names}


def _browser_instructions(mode: str, control_channel: str) -> str:
    channel_notes = {
        "codex-browser": "请使用 Codex 内置浏览器打开候选 Linux.do 帖子。首次需要登录时请让用户完成登录，后续复用已保存登录态。",
        "user-chrome": "请使用用户本机 Chrome 中已经打开或按标签组整理的 Linux.do 帖子，理解标签组和页面之间的关系；不要把这个通道当作全站搜索。",
        "mac-goal": "这是未来 Mac /goal 长任务通道。执行前必须明确停止标准、预算和阶段汇报，不要在第一版里假装已经能后台持续冲浪。",
        "computer-use": "这是实验性 computer-use 通道。仅在普通浏览器能力不足时考虑，不用于常规帖子阅读。",
    }
    return (
        channel_notes[control_channel]
        + "读取首帖和高价值回复，区分事实、观点、争议和行动建议。"
        + f"当前模式：{mode}。不要生成固定日报，只输出本轮任务结果。"
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


def run_knowledge_init(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ensure_knowledge_state(config)
    return 0


def run_bookmark_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ensure_knowledge_state(config)
    result = sync_bookmarks(config)
    write_json(args.output, result)
    return 0


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

    knowledge_init = subparsers.add_parser("knowledge-init", help="初始化 Linux.do 知识库状态文件。")
    knowledge_init.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_init.set_defaults(func=run_knowledge_init)

    bookmark_sync = subparsers.add_parser("bookmark-sync", help="同步 LinuxDo Scripts 书签到 frontier 队列。")
    bookmark_sync.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    bookmark_sync.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/bookmark_sync_result.json"))
    bookmark_sync.set_defaults(func=run_bookmark_sync)

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


def _validate_positive(name: str, value: int) -> None:
    if value <= 0:
        raise SystemExit(2)


def _filter_readings_to_task(readings: list[dict[str, Any]], task: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_ids = {
        parsed
        for parsed in (_safe_int(item.get("id")) for item in task.get("candidates", []) if isinstance(item, dict))
        if parsed is not None
    }
    if not candidate_ids:
        return readings
    return [reading for reading in readings if _safe_int(reading.get("id")) in candidate_ids]


if __name__ == "__main__":
    raise SystemExit(main())
