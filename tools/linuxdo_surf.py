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
from tools.linuxdo_knowledge.context_pack import build_context_pack
from tools.linuxdo_knowledge.feedback import sync_feedback
from tools.linuxdo_knowledge.frontier import add_manual_frontier_item, consume_frontier_items
from tools.linuxdo_knowledge.legacy import migrate_legacy_readings
from tools.linuxdo_knowledge.knowledge_lint import write_knowledge_lint_report
from tools.linuxdo_knowledge.metadata_refresh import apply_topic_metadata_refresh, park_topic_metadata_refresh_blocked
from tools.linuxdo_knowledge.obsidian import scaffold_vault
from tools.linuxdo_knowledge.rewrite_needed import rewrite_needed_candidate_pages
from tools.linuxdo_knowledge.second_pass import organize_existing_readings
from tools.linuxdo_knowledge.session import ingest_session
from tools.linuxdo_knowledge.state import ensure_knowledge_state, maintain_state
from tools.linuxdo_knowledge.strategy import build_knowledge_task
from tools.linuxdo_knowledge.structure import repair_vault_structure


MODES = {"research", "goldmine", "skill-feedback", "discover"}
CONTROL_CHANNELS = {"codex-browser", "user-chrome", "mac-goal", "computer-use"}
RESEARCH_STRATEGIES = {"linuxdo-only", "github-only", "linuxdo-first", "github-first"}
DEFAULT_CONTROL_CHANNEL = "codex-browser"
DEFAULT_RESEARCH_STRATEGY = "linuxdo-only"
DISCOVERY_QUEUE_NAMES = (
    "author-tracking",
    "comment-reference",
    "tool-lookup",
    "skill-workflow-evidence",
    "github-repo-research",
    "github-search",
)
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
        return {key: list(value) for key, value in DEFAULT_STATE.items()}
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


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    read_ids = sorted({int(item) for item in state.get("read_topic_ids", []) if str(item).strip().isdigit()})
    synced_names = _unique([str(item).strip() for item in state.get("synced_skill_names", []) if str(item).strip()])
    reviewed_repos = _normalize_repo_list(state.get("reviewed_github_repos", []))
    reviewed_searches = _unique(
        [str(item).strip().lower() for item in state.get("reviewed_github_searches", []) if str(item).strip()]
    )
    render_checked_ids = sorted(
        {int(item) for item in state.get("render_checked_topic_ids", []) if str(item).strip().isdigit()}
    )
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
        "mac-goal": "这是未来 Mac /goal 长任务通道。执行前必须明确停止标准、预算和阶段汇报，不要在第一版里假装已经能后台持续冲浪。",
        "computer-use": "这是实验性 computer-use 通道。仅在普通浏览器能力不足时考虑，不用于常规帖子阅读。",
    }
    strategy_notes = {
        "linuxdo-only": "研究策略：只使用 Linux.do，不自动进入 GitHub；如发现项目线索，只记录为可补深挖候选。",
        "linuxdo-first": "研究策略：Linux.do 为主；只把值得验证的项目、skill、插件、工具、workflow、repo 交给 GitHub 深挖。",
        "github-first": "研究策略：GitHub 为主；搜索 Linux.do 来补社区反馈，不做全站泛搜。",
        "github-only": "研究策略：该策略通常不生成 Linux.do 阅读任务；如出现此任务，只记录需要人工确认的社区反馈缺口。",
    }
    failure_note = (
        "读帖异常规则：如果 JSON/DOM/文本抽取失败、页面疑似未登录、出现挑战页、加载不完整，"
        "或可见页面与抽取结果不一致，先检查当前可见页面状态；需要人工处理时立刻暂停，"
        "说明 URL、可见状态、失败方法和需要用户做什么。未经用户确认，不要把帖子判定为被拦住，"
        "也不要用旧摘录替代源网页复查。"
    )
    return (
        channel_notes[control_channel]
        + strategy_notes[research_strategy]
        + failure_note
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
        readings = data.get("readings") or data.get("topics") or data.get("github_readings") or data.get("items") or []
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
        args.strategy,
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
    state["render_checked_topic_ids"] = state["render_checked_topic_ids"] + _render_checked_ids(result["items"])
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
    candidates = rank_topics(
        topics,
        mode=args.mode,
        query=args.query,
        skill_names=skill_names,
        read_ids=set(state["read_topic_ids"]),
        limit=args.max_candidates,
    )
    next_batch = candidates[: args.max_topics]
    task = build_browser_task(
        args.mode,
        args.query,
        next_batch,
        skill_names,
        args.max_topics,
        args.max_replies,
        "mac-goal",
        args.strategy,
    )
    task["frontier_queue"] = str(args.queue)
    task["state"] = str(args.state)
    task["next_batch"] = task.pop("candidates")
    task["stop_conditions"] = ["next_batch 为空", "达到本轮深读预算", "连续批次没有发现高价值候选"]
    write_json(args.queue, {"items": candidates, "created_at": datetime.now().isoformat(timespec="seconds")})
    write_json(args.output / f"goal_task_{args.mode}.json", task)
    save_state(args.state, state)
    return 0


def run_session(args: argparse.Namespace) -> int:
    task = json.loads(args.task.read_text(encoding="utf-8"))
    readings = _filter_readings_to_task(load_readings(args.readings), task)
    result = build_mode_result(task, readings)
    mode = validate_mode(result["mode"])
    session = {
        **result,
        "stop_reason": args.stop_reason,
        "discovery_queues": _empty_discovery_queues(),
    }
    write_json(_next_session_path(args.output, mode), session)
    state = load_state(args.state)
    state["read_topic_ids"] = state["read_topic_ids"] + session["read_topic_ids"]
    state["render_checked_topic_ids"] = state["render_checked_topic_ids"] + _render_checked_ids(session["items"])
    save_state(args.state, state)
    return 0


def run_github_plan(args: argparse.Namespace) -> int:
    _validate_positive("max-repos", args.max_repos)
    _validate_positive("max-searches", args.max_searches)
    state = load_state(args.state)
    frontier = load_frontier(args.queue)
    repositories = _select_github_repos(frontier, state, args.max_repos)
    searches = _select_github_searches(frontier, state, args.max_searches)
    if args.strategy == "github-only" and args.query.strip():
        searches = [
            {
                "query": args.query.strip(),
                "source_tool": args.query.strip(),
                "source_topic_ids": [],
                "source_urls": [],
                "score": 1,
                "depth": 1,
            }
        ]
    task = build_github_task(
        args.mode,
        args.query,
        args.queue,
        repositories,
        searches,
        args.max_repos,
        args.max_searches,
        args.strategy,
    )
    write_json(args.output / f"github_task_{args.mode}.json", task)
    save_state(args.state, state)
    return 0


def run_github_result(args: argparse.Namespace) -> int:
    task = json.loads(args.task.read_text(encoding="utf-8"))
    readings = load_readings(args.readings)
    result = build_github_result(task, readings)
    mode = validate_mode(str(result["mode"]))
    write_json(args.output / f"github_result_{mode}.json", result)
    state = load_state(args.state)
    state["reviewed_github_repos"] = state["reviewed_github_repos"] + result["reviewed_github_repos"]
    state["reviewed_github_searches"] = state["reviewed_github_searches"] + result["reviewed_github_searches"]
    save_state(args.state, state)
    return 0


def run_backfill_plan(args: argparse.Namespace) -> int:
    source_platform = str(args.source_platform).strip().lower()
    readings = load_readings(args.input)
    if source_platform == "linuxdo":
        _validate_positive("max-repos", args.max_repos)
        _validate_positive("max-searches", args.max_searches)
        repositories = _repos_from_readings(readings)[: args.max_repos]
        searches = _searches_from_readings(readings)[: args.max_searches]
        task = build_github_task(
            args.mode,
            "",
            args.queue,
            repositories,
            searches,
            args.max_repos,
            args.max_searches,
            "linuxdo-first",
        )
        task["backfill_source"] = "linuxdo"
        write_json(args.output / f"github_task_{args.mode}.json", task)
        return 0
    if source_platform == "github":
        _validate_positive("max-topics", args.max_topics)
        query = _linuxdo_query_from_github_readings(readings)
        topics = load_topics(args.topics)
        candidates = rank_topics(topics, mode=args.mode, query=query, limit=args.max_topics) if query else []
        task = build_browser_task(args.mode, query, candidates, [], args.max_topics, 8, research_strategy="github-first")
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


def run_knowledge_init(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    scaffold_vault(config)
    ensure_knowledge_state(config)
    return 0


def run_bookmark_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ensure_knowledge_state(config)
    result = sync_bookmarks(config)
    write_json(args.output, result)
    return 0


def run_knowledge_plan(args: argparse.Namespace) -> int:
    _validate_positive("batch-size", args.batch_size)
    config = load_config(args.config)
    ensure_knowledge_state(config)
    task = build_knowledge_task(config, batch_size=args.batch_size)
    write_json(args.output, task)
    return 0


def run_knowledge_context_pack(args: argparse.Namespace) -> int:
    _validate_positive("limit", args.limit)
    config = load_config(args.config)
    ensure_knowledge_state(config)
    pack = build_context_pack(config, focus=args.focus, limit=args.limit)
    write_json(args.output, pack)
    return 0


def run_knowledge_session(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    task = json.loads(args.task.read_text(encoding="utf-8"))
    readings = json.loads(args.readings.read_text(encoding="utf-8"))
    written_paths: list[Path] = []
    result = ingest_session(config, task=task, readings=readings, batch_id=args.batch_id, written_paths=written_paths)
    write_json(args.output, result)
    if args.batch_manifest_output or args.audit_paths_output:
        if args.audit_paths_output:
            _write_audit_paths(config.obsidian_vault_path, args.audit_paths_output, written_paths)
        manifest_path = args.batch_manifest_output or _default_batch_manifest_output(args.output, args.batch_id)
        manifest = build_batch_manifest(
            config=config,
            batch_id=args.batch_id,
            task=task,
            readings=readings,
            task_path=args.task,
            readings_path=args.readings,
            session_output=args.output,
            result=result,
            written_paths=written_paths,
            manifest_output=manifest_path,
            audit_paths_output=args.audit_paths_output,
        )
        write_json(manifest_path, manifest)
    return 0


def run_knowledge_index_audit(args: argparse.Namespace) -> int:
    from tools.linuxdo_knowledge.index_audit import write_index_audit_report

    config = load_config(args.config)
    write_index_audit_report(config, args.output, readings_dir=args.readings_dir)
    return 0


def run_knowledge_rebuild_evidence(args: argparse.Namespace) -> int:
    from tools.linuxdo_knowledge.evidence_rebuild import rebuild_evidence_edges

    config = load_config(args.config)
    result = rebuild_evidence_edges(config)
    write_json(args.output, result)
    return 0


def run_knowledge_repair_audit_issues(args: argparse.Namespace) -> int:
    from tools.linuxdo_knowledge.audit_repair import repair_audit_issues

    config = load_config(args.config)
    result = repair_audit_issues(
        config,
        readings_dir=args.readings_dir,
        apply=args.apply,
        limit=args.limit,
    )
    write_json(args.output, result)
    return 0


def build_batch_manifest(
    *,
    config: Any,
    batch_id: str,
    task: dict[str, Any],
    readings: dict[str, Any] | list[dict[str, Any]],
    task_path: Path,
    readings_path: Path,
    session_output: Path,
    result: dict[str, Any],
    written_paths: list[Path],
    manifest_output: Path,
    audit_paths_output: Path | None,
) -> dict[str, Any]:
    task_items = _dict_items(task.get("items", []) if isinstance(task, dict) else [])
    read_items = _knowledge_readings_list(readings)
    metadata_mismatches = _metadata_only_level_mismatches(read_items)
    skips_without_reason = _skip_without_reason(task_items)
    redaction = _redaction_scan(task_items + read_items)
    relative_paths = _relative_vault_paths(config.obsidian_vault_path, written_paths)
    gate_status = _manifest_gate_status(metadata_mismatches, skips_without_reason, redaction)
    return {
        "schema_version": 1,
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": {"task": str(task_path), "readings": str(readings_path)},
        "outputs": {
            "session_result": str(session_output),
            "batch_manifest": str(manifest_output),
            "audit_paths_file": str(audit_paths_output) if audit_paths_output else "",
        },
        "counts": {
            "task_items": len(task_items),
            "readings": len(read_items),
            "written_vault_paths": len(relative_paths),
        },
        "selected_topic_ids": _topic_ids(task_items),
        "read_topic_ids": _topic_ids(read_items),
        "status_counts": _count_by_text(read_items, "status", default="read"),
        "reading_level_counts": _count_by_text(read_items, "reading_level", default="unknown"),
        "metadata_only_level_mismatch": metadata_mismatches,
        "skip_without_reason": skips_without_reason,
        "written_vault_paths": [{"path": path} for path in relative_paths],
        "redaction_scan": redaction,
        "gate_status": gate_status,
        "result": result,
    }


def _default_batch_manifest_output(output_path: Path, batch_id: str) -> Path:
    stem = output_path.stem
    if stem.startswith("knowledge_session_result"):
        return output_path.with_name("batch_manifest" + stem.removeprefix("knowledge_session_result") + output_path.suffix)
    safe_batch = re.sub(r"[^A-Za-z0-9_.-]+", "_", batch_id).strip("_") or "latest"
    return output_path.with_name(f"batch_manifest_{safe_batch}.json")


def _write_audit_paths(vault_path: Path, output_path: Path, written_paths: list[Path]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(_relative_vault_paths(vault_path, written_paths)) + "\n", encoding="utf-8")


def _relative_vault_paths(vault_path: Path, written_paths: list[Path]) -> list[str]:
    values: list[str] = []
    seen = set()
    for path in written_paths:
        try:
            relative = path.relative_to(vault_path).as_posix()
        except ValueError:
            continue
        if not relative.endswith(".md") or relative in seen:
            continue
        seen.add(relative)
        values.append(relative)
    return values


def _knowledge_readings_list(readings: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(readings, list):
        return [item for item in readings if isinstance(item, dict)]
    if not isinstance(readings, dict):
        return []
    value = readings.get("readings", readings.get("topics", []))
    return _dict_items(value)


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _topic_ids(items: list[dict[str, Any]]) -> list[int]:
    ids = {_topic_id(item) for item in items}
    return sorted(item for item in ids if item is not None)


def _topic_id(item: dict[str, Any]) -> int | None:
    value = _safe_int(item.get("topic_id")) or _safe_int(item.get("id"))
    if value is not None:
        return value
    url = str(item.get("url", ""))
    match = re.search(r"/t/(?:[^/]+/)?(\d+)", url)
    return int(match.group(1)) if match else None


def _count_by_text(items: list[dict[str, Any]], field: str, *, default: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(field, default)).strip() or default
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _metadata_only_level_mismatches(read_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in read_items:
        if str(item.get("status", "")).strip() != "metadata_only":
            continue
        reading_level = _safe_int(item.get("reading_level"))
        if reading_level != 0:
            issues.append(
                {
                    "topic_id": _topic_id(item),
                    "status": "metadata_only",
                    "reading_level": reading_level,
                    "title": str(item.get("title", "")).strip(),
                }
            )
    return issues


def _skip_without_reason(task_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in task_items:
        action = str(item.get("action", "")).strip()
        reason = str(item.get("skip_reason") or item.get("reason") or "").strip()
        if action in {"skip", "metadata_only"} and not reason:
            issues.append({"topic_id": _topic_id(item), "action": action, "title": str(item.get("title", "")).strip()})
    return issues


SECRET_HINT_RE = re.compile(r"(?i)(api[_-]?key|authorization|bearer\s+[a-z0-9._-]{12,}|password|token)")


def _redaction_scan(items: list[dict[str, Any]]) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for item in items:
        for field in ("summary", "minimal_context", "risk", "notes"):
            value = item.get(field)
            if isinstance(value, str) and SECRET_HINT_RE.search(value):
                hits.append({"topic_id": _topic_id(item), "field": field})
    return {"hits": hits, "status": "fail" if hits else "pass"}


def _manifest_gate_status(
    metadata_mismatches: list[dict[str, Any]],
    skips_without_reason: list[dict[str, Any]],
    redaction: dict[str, Any],
) -> str:
    if redaction.get("hits"):
        return "fail"
    if metadata_mismatches or skips_without_reason:
        return "warn"
    return "pass"


def run_feedback_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = sync_feedback(config)
    write_json(args.output, result)
    return 0


def run_knowledge_prepare(args: argparse.Namespace) -> int:
    _validate_positive("batch-size", args.batch_size)
    _validate_positive("limit", args.limit)
    config = load_config(args.config)
    ensure_knowledge_state(config)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    feedback_path = args.output_dir / "feedback_sync_latest.json"
    bookmark_path = args.output_dir / "bookmark_sync_latest.json"
    context_path = args.output_dir / "context_pack_latest.json"
    task_path = args.output_dir / "knowledge_task_latest.json"
    manifest_path = args.output_dir / "knowledge_prepare_latest.json"

    feedback_result = sync_feedback(config)
    write_json(feedback_path, feedback_result)

    bookmark_result = sync_bookmarks(config)
    write_json(bookmark_path, bookmark_result)

    context_pack = build_context_pack(config, focus=args.focus, limit=args.limit)
    write_json(context_path, context_pack)

    knowledge_task = build_knowledge_task(config, batch_size=args.batch_size)
    write_json(task_path, knowledge_task)

    manifest = {
        "feedback_sync": str(feedback_path),
        "bookmark_sync": str(bookmark_path),
        "context_pack": str(context_path),
        "knowledge_task": str(task_path),
        "history_policy": knowledge_task.get("history_policy", "load_hot_indexes_only"),
    }
    write_json(manifest_path, manifest)
    return 0


def run_knowledge_maintain(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = maintain_state(config)
    write_json(args.output, result)
    return 0


def run_knowledge_migrate_legacy(args: argparse.Namespace) -> int:
    _validate_positive("batch-size", args.batch_size)
    config = load_config(args.config)
    result = migrate_legacy_readings(
        config,
        input_path=args.input,
        batch_size=args.batch_size,
        resource_limit=args.resource_limit,
    )
    write_json(args.output, result)
    return 0


def run_knowledge_organize_existing(args: argparse.Namespace) -> int:
    _validate_positive("top-per-category", args.top_per_category)
    config = load_config(args.config)
    result = organize_existing_readings(
        config,
        input_path=args.input,
        top_per_category=args.top_per_category,
    )
    write_json(args.output, result)
    return 0


def run_knowledge_rewrite_needed(args: argparse.Namespace) -> int:
    _validate_positive("max-sources-per-page", args.max_sources_per_page)
    config = load_config(args.config)
    result = rewrite_needed_candidate_pages(
        config,
        input_path=args.input,
        max_sources_per_page=args.max_sources_per_page,
        include_source_extract=args.include_source_extract,
    )
    write_json(args.output, result)
    return 0


def run_knowledge_repair_structure(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = repair_vault_structure(config)
    write_json(args.output, result)
    return 0


def run_knowledge_audit(args: argparse.Namespace) -> int:
    from tools.linuxdo_knowledge.quality_audit import write_audit_report

    config = load_config(args.config)
    paths = None
    if args.paths_file:
        paths = [
            line.strip()
            for line in args.paths_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    path = write_audit_report(config.obsidian_vault_path, args.output, layer=args.layer, paths=paths)
    print(f"已写入质量审计报告：{path}")
    return 0


def run_metadata_refresh(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        items = []
    result = apply_topic_metadata_refresh(config, [item for item in items if isinstance(item, dict)])
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def run_knowledge_lint(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    path = write_knowledge_lint_report(config, args.output, limit=args.limit)
    print(f"已写入知识库 lint 报告：{path}")
    return 0


def run_metadata_refresh_blocked(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        items = []
    result = park_topic_metadata_refresh_blocked(config, [item for item in items if isinstance(item, dict)])
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def run_frontier_add(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = add_manual_frontier_item(config, url=args.url, reason=args.reason)
    write_json(args.output, result)
    return 0


def run_knowledge_consume_frontier(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    readings = json.loads(args.readings.read_text(encoding="utf-8"))
    output = args.output or config.project_root / "output" / "linuxdo_surf" / f"{args.batch_id}_frontier_consumed.json"
    consume_frontier_items(config, readings, batch_id=args.batch_id, output=output)
    return 0


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

    session = subparsers.add_parser("session", help="保存 /goal 长任务阅读会话，并更新已读状态。")
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

    github_result = subparsers.add_parser("github-result", help="保存 GitHub 深挖结果。")
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

    knowledge_init = subparsers.add_parser("knowledge-init", help="初始化 Linux.do 知识库状态文件。")
    knowledge_init.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_init.set_defaults(func=run_knowledge_init)

    bookmark_sync = subparsers.add_parser("bookmark-sync", help="同步 LinuxDo Scripts 书签到 frontier 队列。")
    bookmark_sync.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    bookmark_sync.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/bookmark_sync_result.json"))
    bookmark_sync.set_defaults(func=run_bookmark_sync)

    knowledge_plan = subparsers.add_parser("knowledge-plan", help="从轻量 frontier 生成知识库阅读任务。")
    knowledge_plan.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_plan.add_argument("--batch-size", type=int, default=20)
    knowledge_plan.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_task_latest.json"))
    knowledge_plan.set_defaults(func=run_knowledge_plan)

    knowledge_context_pack = subparsers.add_parser("knowledge-context-pack", help="从热索引生成下一次冲浪的轻量上下文包。")
    knowledge_context_pack.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_context_pack.add_argument("--focus", default="")
    knowledge_context_pack.add_argument("--limit", type=int, default=40)
    knowledge_context_pack.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/context_pack_latest.json"))
    knowledge_context_pack.set_defaults(func=run_knowledge_context_pack)

    knowledge_session = subparsers.add_parser("knowledge-session", help="写入一批冲浪结果到机器状态和 Obsidian。")
    knowledge_session.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_session.add_argument("--task", type=Path, required=True)
    knowledge_session.add_argument("--readings", type=Path, required=True)
    knowledge_session.add_argument("--batch-id", default="001")
    knowledge_session.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_session_result.json"))
    knowledge_session.add_argument("--batch-manifest-output", type=Path)
    knowledge_session.add_argument("--audit-paths-output", type=Path)
    knowledge_session.set_defaults(func=run_knowledge_session)

    knowledge_index_audit = subparsers.add_parser("knowledge-index-audit", help="审计知识库热索引、证据边和本批读取异常。")
    knowledge_index_audit.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_index_audit.add_argument("--readings-dir", type=Path, default=Path("output/linuxdo_surf"))
    knowledge_index_audit.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_index_audit_latest.json"))
    knowledge_index_audit.set_defaults(func=run_knowledge_index_audit)

    knowledge_rebuild_evidence = subparsers.add_parser("knowledge-rebuild-evidence", help="从历史 evidence shards 重建证据反查索引。")
    knowledge_rebuild_evidence.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_rebuild_evidence.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_rebuild_evidence_latest.json"))
    knowledge_rebuild_evidence.set_defaults(func=run_knowledge_rebuild_evidence)

    knowledge_repair_audit_issues = subparsers.add_parser("knowledge-repair-audit-issues", help="分批修正 index-audit 中可安全自动处理的问题。")
    knowledge_repair_audit_issues.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_repair_audit_issues.add_argument("--readings-dir", type=Path, default=Path("output/linuxdo_surf"))
    knowledge_repair_audit_issues.add_argument("--limit", type=int, default=500, help="本批最多修正多少项；0 表示不限制。")
    knowledge_repair_audit_issues.add_argument("--apply", action="store_true", help="实际写入；不传时只输出 dry-run 结果。")
    knowledge_repair_audit_issues.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_audit_repair_latest.json"))
    knowledge_repair_audit_issues.set_defaults(func=run_knowledge_repair_audit_issues)

    knowledge_consume_frontier = subparsers.add_parser(
        "knowledge-consume-frontier",
        help="按本批 readings 从知识库 frontier 队列移除已读 topic。",
    )
    knowledge_consume_frontier.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_consume_frontier.add_argument("--readings", type=Path, required=True)
    knowledge_consume_frontier.add_argument("--batch-id", default="001")
    knowledge_consume_frontier.add_argument("--output", type=Path)
    knowledge_consume_frontier.set_defaults(func=run_knowledge_consume_frontier)

    feedback_sync = subparsers.add_parser("feedback-sync", help="同步 Obsidian 人工反馈到机器状态。")
    feedback_sync.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    feedback_sync.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/feedback_sync_result.json"))
    feedback_sync.set_defaults(func=run_feedback_sync)

    knowledge_prepare = subparsers.add_parser("knowledge-prepare", help="同步反馈、书签、上下文包和本批阅读任务。")
    knowledge_prepare.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_prepare.add_argument("--batch-size", type=int, default=20)
    knowledge_prepare.add_argument("--focus", default="")
    knowledge_prepare.add_argument("--limit", type=int, default=40)
    knowledge_prepare.add_argument("--output-dir", type=Path, default=Path("output/linuxdo_surf"))
    knowledge_prepare.set_defaults(func=run_knowledge_prepare)

    knowledge_maintain = subparsers.add_parser("knowledge-maintain", help="轻量维护热索引和冷归档。")
    knowledge_maintain.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_maintain.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_maintain_result.json"))
    knowledge_maintain.set_defaults(func=run_knowledge_maintain)

    knowledge_audit = subparsers.add_parser("knowledge-audit", help="扫描 Obsidian vault 的人读质量问题。")
    knowledge_audit.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_audit.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/quality_audit_latest.json"))
    knowledge_audit.add_argument("--layer", choices=("human", "transitional", "ledger", "all"), default="human")
    knowledge_audit.add_argument("--paths-file", type=Path, help="只审文件内列出的 vault 相对路径，一行一个。")
    knowledge_audit.set_defaults(func=run_knowledge_audit)

    metadata_refresh = subparsers.add_parser("metadata-refresh", help="把轻量 topic metadata 写入 topic_update_state。")
    metadata_refresh.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    metadata_refresh.add_argument("--input", type=Path, required=True, help="包含 topic metadata list 的 JSON 文件。")
    metadata_refresh.add_argument("--output", type=Path, help="写入刷新结果 JSON。")
    metadata_refresh.set_defaults(func=run_metadata_refresh)

    knowledge_lint = subparsers.add_parser("knowledge-lint", help="生成 Karpathy-style ingest/query/lint 协议巡检报告。")
    knowledge_lint.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_lint.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_lint_latest.json"))
    knowledge_lint.add_argument("--limit", type=int, default=50)
    knowledge_lint.set_defaults(func=run_knowledge_lint)

    metadata_refresh_blocked = subparsers.add_parser("metadata-refresh-blocked", help="停放 live-access blocked 的 topic metadata refresh。")
    metadata_refresh_blocked.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    metadata_refresh_blocked.add_argument("--input", type=Path, required=True, help="包含 blocked topic list 的 JSON 文件。")
    metadata_refresh_blocked.add_argument("--output", type=Path, help="写入停放结果 JSON。")
    metadata_refresh_blocked.set_defaults(func=run_metadata_refresh_blocked)

    frontier_add = subparsers.add_parser("frontier-add", help="手动把一个 Linux.do topic 加入 frontier 队列。")
    frontier_add.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    frontier_add.add_argument("--url", required=True)
    frontier_add.add_argument("--reason", required=True)
    frontier_add.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/frontier_add_latest.json"))
    frontier_add.set_defaults(func=run_frontier_add)

    knowledge_migrate_legacy = subparsers.add_parser("knowledge-migrate-legacy", help="把旧 readings_all.json 迁移到新知识库结构。")
    knowledge_migrate_legacy.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_migrate_legacy.add_argument("--input", type=Path, default=Path("output/linuxdo_surf/readings_all.json"))
    knowledge_migrate_legacy.add_argument("--batch-size", type=int, default=20)
    knowledge_migrate_legacy.add_argument("--resource-limit", type=int, default=120)
    knowledge_migrate_legacy.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_migrate_legacy_result.json"))
    knowledge_migrate_legacy.set_defaults(func=run_knowledge_migrate_legacy)

    knowledge_organize_existing = subparsers.add_parser("knowledge-organize-existing", help="从累计阅读记录刷新 Obsidian 导览、分类、对比和复核页。")
    knowledge_organize_existing.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_organize_existing.add_argument("--input", type=Path, default=Path("output/linuxdo_surf/readings_all.json"))
    knowledge_organize_existing.add_argument("--top-per-category", type=int, default=18)
    knowledge_organize_existing.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_organize_existing_result.json"))
    knowledge_organize_existing.set_defaults(func=run_knowledge_organize_existing)

    knowledge_rewrite_needed = subparsers.add_parser("knowledge-rewrite-needed", help="用来源抽取重写待复核候选卡，并降级证据不足页面。")
    knowledge_rewrite_needed.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_rewrite_needed.add_argument("--input", type=Path, default=Path("output/linuxdo_surf/readings_all.json"))
    knowledge_rewrite_needed.add_argument("--max-sources-per-page", type=int, default=6)
    knowledge_rewrite_needed.add_argument("--include-source-extract", action="store_true", help="同时重写上次自动生成的 source_extract 页面；默认只处理待重写页面。")
    knowledge_rewrite_needed.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_rewrite_needed_result.json"))
    knowledge_rewrite_needed.set_defaults(func=run_knowledge_rewrite_needed)

    knowledge_repair_structure = subparsers.add_parser("knowledge-repair-structure", help="按对象类型重新归位 Obsidian 人读页面。")
    knowledge_repair_structure.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_repair_structure.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_repair_structure_result.json"))
    knowledge_repair_structure.set_defaults(func=run_knowledge_repair_structure)

    return parser


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


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_positive(name: str, value: int) -> None:
    if value <= 0:
        raise SystemExit(2)


def load_frontier(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"discovery_queues": _empty_discovery_queues(), "items": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"discovery_queues": _empty_discovery_queues(), "items": []}
    discovery = data.get("discovery_queues", {})
    if not isinstance(discovery, dict):
        discovery = {}
    data["discovery_queues"] = {
        name: value if isinstance(value := discovery.get(name, []), list) else []
        for name in DISCOVERY_QUEUE_NAMES
    }
    return data


def build_github_task(
    mode: str,
    query: str,
    frontier_path: Path,
    repositories: list[dict[str, Any]],
    searches: list[dict[str, Any]],
    max_repos: int,
    max_searches: int,
    research_strategy: str,
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
        "instructions": "请使用 GitHub MCP 或 GitHub 官方页面检查 README、最近提交、release、issues、安装成本、风险和替代方案。",
        "next_batch": {
            "repositories": repositories[:max_repos],
            "searches": searches[:max_searches],
        },
    }


def build_github_result(task: dict[str, Any], readings: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for reading in readings:
        repo = _normalize_repo_name(reading.get("repo") or reading.get("url"))
        if not repo:
            continue
        items.append(
            {
                "repo": repo,
                "url": str(reading.get("url") or f"https://github.com/{repo}"),
                "source_query": str(reading.get("source_query", "")).strip(),
                "summary": str(reading.get("summary", "")),
                "recommendation": str(reading.get("recommendation", "")),
                "confidence": str(reading.get("confidence", "")),
                "related_repos": _field_as_list(reading.get("related_repos", [])),
                "related_tools": _field_as_list(reading.get("related_tools", [])),
            }
        )
    searches = [
        str(item.get("query", "")).strip().lower()
        for item in (task.get("next_batch", {}) or {}).get("searches", [])
        if isinstance(item, dict) and str(item.get("query", "")).strip()
    ]
    return {
        "mode": str(task.get("mode", "")),
        "query": str(task.get("query", "")),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reviewed_github_repos": [item["repo"] for item in items],
        "reviewed_github_searches": _unique(searches),
        "items": items,
        "discovery_queues": _empty_discovery_queues(),
    }


def build_visual_review_task(readings: list[dict[str, Any]], state: dict[str, Any], max_topics: int) -> dict[str, Any]:
    _validate_positive("max-topics", max_topics)
    checked_ids = set(state.get("render_checked_topic_ids", []))
    candidates: list[dict[str, Any]] = []
    for reading in readings:
        topic_id = _safe_int(reading.get("id")) or 0
        if topic_id in checked_ids:
            continue
        if not _reading_needs_visual_review(reading):
            continue
        candidates.append(
            {
                "id": topic_id,
                "title": str(reading.get("title", "")),
                "url": str(reading.get("url", "")),
                "summary": str(reading.get("summary", "")),
                "render_required": True,
                "visual_reason": str(reading.get("visual_reason") or "render_required"),
                "visual_review_priority": str(reading.get("visual_review_priority") or "medium"),
                "visual_assets": _field_as_list(reading.get("visual_assets", [])),
            }
        )
    return {
        "task_type": "visual-review",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "budget": {"max_topics": max_topics},
        "instructions": "Use Codex browser to open rendered Linux.do pages and check screenshots, videos, UI/WebUI, tutorial steps, layout, and visual evidence.",
        "items": candidates[:max_topics],
    }


def _reading_needs_visual_review(reading: dict[str, Any]) -> bool:
    if bool(reading.get("render_checked", False)) or str(reading.get("visual_review_status", "")).lower() == "checked":
        return False
    if bool(reading.get("render_required", False)) or bool(reading.get("visual_evidence_needed", False)):
        return True
    text = " ".join(
        str(reading.get(field, ""))
        for field in ("title", "summary", "first_post", "visual_reason")
    ).lower()
    return any(word.lower() in text for word in ("截图", "图片", "视频", "ui", "webui", "教程", "安装", "配置", "如图"))


def _render_checked_ids(items: list[dict[str, Any]]) -> list[int]:
    ids = []
    for item in items:
        if item.get("render_checked") or str(item.get("visual_review_status", "")).lower() == "checked":
            parsed = _safe_int(item.get("id"))
            if parsed is not None:
                ids.append(parsed)
    return ids


def _next_session_path(output: Path, mode: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return output / f"session_{mode}_{stamp}.json"


def _empty_discovery_queues() -> dict[str, list[dict[str, Any]]]:
    return {name: [] for name in DISCOVERY_QUEUE_NAMES}


def _select_github_repos(frontier: dict[str, Any], state: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    reviewed = set(state.get("reviewed_github_repos", []))
    items = frontier.get("discovery_queues", {}).get("github-repo-research", [])
    result = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        repo = _normalize_repo_name(item.get("repo") or item.get("url"))
        if not repo or repo in reviewed:
            continue
        result.append({**item, "repo": repo, "url": f"https://github.com/{repo}"})
        if len(result) >= limit:
            break
    return result


def _select_github_searches(frontier: dict[str, Any], state: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    reviewed = set(state.get("reviewed_github_searches", []))
    items = frontier.get("discovery_queues", {}).get("github-search", [])
    result = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query", "")).strip()
        if not query or query.lower() in reviewed:
            continue
        result.append({**item, "query": query})
        if len(result) >= limit:
            break
    return result


def _repos_from_readings(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repos: list[str] = []
    for reading in readings:
        repos.extend(_github_repos_from_values([reading.get("url", ""), reading.get("summary", ""), reading.get("github_repos", [])]))
    return [{"repo": repo, "url": f"https://github.com/{repo}", "score": 1} for repo in _unique(repos)]


def _searches_from_readings(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queries = []
    for reading in readings:
        tools = reading.get("tools", [])
        if isinstance(tools, str):
            tools = [tools]
        queries.extend(str(tool).strip() for tool in tools if str(tool).strip())
    return [{"query": query, "source_tool": query, "score": 1} for query in _unique(queries)]


def _linuxdo_query_from_github_readings(readings: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for reading in readings:
        values.append(str(reading.get("repo", "")))
        values.append(str(reading.get("source_query", "")))
        values.extend(str(item) for item in _field_as_list(reading.get("related_tools", [])))
    return " ".join(_unique([value for value in values if value.strip()]))


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
    match = re.search(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text)
    if match:
        text = f"{match.group(1)}/{match.group(2)}"
    parts = text.strip("/").split("/")
    if len(parts) < 2:
        return ""
    owner, repo = parts[0], parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        return ""
    return f"{owner.lower()}/{repo.lower()}"


def _field_as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


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
