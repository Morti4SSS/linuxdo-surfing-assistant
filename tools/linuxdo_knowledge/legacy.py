from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .obsidian import (
    FEEDBACK_HEADING,
    FEEDBACK_HEADING_PATTERN,
    append_log,
    page_path_for,
    page_path_for_id,
    safe_filename,
    scaffold_vault,
    write_page,
)
from .quality import classify_knowledge_object, normalize_resource_name as normalize_quality_resource_name
from .session import ingest_session
from .state import ensure_knowledge_state, load_hot_indexes, now_iso, save_hot_index


GENERIC_RESOURCE_NAMES = {
    "agent",
    "agents",
    "ai",
    "api",
    "chatgpt",
    "cli",
    "codex",
    "cursor",
    "gemini",
    "github",
    "gpt",
    "llm",
    "mcp",
    "model",
    "models",
    "openai",
    "plugin",
    "plugins",
    "prompt",
    "prompts",
    "repo",
    "repository",
    "skill",
    "skills",
    "tool",
    "tools",
    "ui",
    "web",
    "webui",
    "api 中转",
    "公益站",
    "中转站",
    "人工智能",
    "软件开发",
}

LOW_VALUE_TAGS = {"low", "暂时跳过", "unreadable"}
HIGH_VALUE_TAGS = {"high", "马上试"}
MEDIUM_VALUE_TAGS = {"medium", "收藏观察", "谨慎"}

BROAD_CANDIDATE_PAGES = {
    "API 中转": "API 中转是服务/网关/渠道集合，不是单一资源。后续应拆成具体 Service 或工具卡。",
    "公益站": "公益站是服务集合和状态线索，不是单一资源。后续应拆成具体站点、管理工具或风险 claim。",
    "中转站": "中转站是服务集合和渠道类型，不是单一资源。后续应拆成具体服务、网关或管理工具。",
}

ALIAS_CANDIDATE_REDIRECTS = {
    "Vibe-Coding": "Vibecoding",
    "ccswitch": "CC-Switch",
}


def migrate_legacy_readings(
    config: KnowledgeConfig,
    input_path: Path,
    batch_size: int = 20,
    resource_limit: int = 120,
    migrated_at: str | None = None,
) -> dict[str, int]:
    if batch_size <= 0 or resource_limit < 0:
        raise ValueError("batch_size must be positive and resource_limit must be non-negative")

    migrated = migrated_at or now_iso()
    raw_readings = _load_legacy_readings(input_path)
    scaffold_vault(config)
    ensure_knowledge_state(config)

    selected_resources = _select_resource_candidates(raw_readings, limit=resource_limit)
    curated_resource_ids = _curated_resource_ids(config, selected_resources)
    normalized = [
        _normalize_legacy_reading(reading, selected_resources, curated_resource_ids)
        for reading in raw_readings
    ]

    batch_count = 0
    for batch_number, start in enumerate(range(0, len(normalized), batch_size), start=1):
        batch = normalized[start : start + batch_size]
        ingest_session(
            config,
            task={"items": []},
            readings={"readings": batch},
            batch_id=f"archive-{batch_number:03d}",
            observed_at=migrated,
            write_obsidian_log=False,
        )
        batch_count += 1

    _write_legacy_resource_pages(config, raw_readings, selected_resources, migrated)
    _cleanup_legacy_candidate_pages(config, migrated)
    _write_legacy_review_page(config, raw_readings, selected_resources, batch_count, migrated)
    append_log(
        config,
        f"- {migrated}: 整理 readings_all {len(raw_readings)} 条，候选资源 {len(selected_resources)} 个。",
    )
    return {
        "readings": len(raw_readings),
        "legacy_batches": batch_count,
        "resource_candidates": len(selected_resources),
    }


def _load_legacy_readings(input_path: Path) -> list[dict[str, Any]]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        readings = data.get("readings") or data.get("topics") or data.get("items") or []
        if isinstance(readings, list):
            return [item for item in readings if isinstance(item, dict)]
    return []


def _normalize_legacy_reading(
    reading: dict[str, Any],
    selected_resources: dict[str, dict[str, Any]],
    curated_resource_ids: set[str],
) -> dict[str, Any]:
    topic_id = _topic_id(reading)
    value_level = _value_level(reading.get("value_tag"))
    resource_items = _resources_for_reading(reading, selected_resources, curated_resource_ids)
    evidence = _legacy_evidence(reading, topic_id, resource_items)
    return {
        "topic_id": topic_id,
        "title": _text(reading.get("title")) or f"topic-{topic_id}",
        "url": _text(reading.get("url")) or f"https://linux.do/t/topic/{topic_id}",
        "author": _text(reading.get("author")),
        "summary": _text(reading.get("summary")),
        "value_level": value_level,
        "tags": _legacy_tags(reading),
        "status": "deprioritized" if _is_low_value(reading) else "active",
        "watchlist": _is_high_value(reading),
        "reply_count": _int(reading.get("visible_post_count"), 0),
        "reading_level": _reading_level(reading),
        "read_ranges": _read_ranges(reading),
        "highest_post_number": _highest_post_number(reading),
        "content_fingerprint": _fingerprint(reading),
        "key_replies": _key_replies(reading),
        "resources": resource_items,
        "evidence": [evidence] if evidence["summary"] else [],
    }


def _legacy_evidence(
    reading: dict[str, Any],
    topic_id: int,
    resources: list[dict[str, Any]],
) -> dict[str, Any]:
    positives = _string_list(reading.get("positive_feedback"))
    negatives = _string_list(reading.get("negative_feedback"))
    risks = _string_list(reading.get("risk_notes"))
    comparisons = _string_list(reading.get("comparison_notes"))
    context_lines: list[str] = []
    context_lines.extend(f"正向反馈：{item}" for item in positives[:2])
    context_lines.extend(f"负向反馈：{item}" for item in negatives[:2])
    context_lines.extend(f"对比线索：{item}" for item in comparisons[:2])
    context_lines.extend(_reply_context_lines(reading)[:3])
    return {
        "id": f"evidence:linuxdo:{topic_id}:source-note",
        "name": f"linuxdo-{topic_id}-source-note",
        "summary": _text(reading.get("summary")),
        "minimal_context": context_lines,
        "risk": risks[:4],
        "stance": _stance_for(reading),
        "confidence": _text(reading.get("confidence_after_render")) or _text(reading.get("confidence")) or "medium",
        "evidence_kind": "community_signal",
        "resource_refs": [resource["id"] for resource in resources],
    }


def _select_resource_candidates(readings: list[dict[str, Any]], limit: int) -> dict[str, dict[str, Any]]:
    if limit == 0:
        return {}

    scores: Counter[str] = Counter()
    mentions: dict[str, dict[str, Any]] = {}
    for reading in readings:
        if _is_low_value(reading):
            continue
        seen_in_topic: set[str] = set()
        for item in _resource_mentions(reading):
            key = item["key"]
            if key in seen_in_topic:
                continue
            seen_in_topic.add(key)
            scores[key] += _value_weight(reading)
            existing = mentions.setdefault(key, item)
            existing.setdefault("topic_ids", []).append(_topic_id(reading))
            existing.setdefault("source_urls", []).append(_text(reading.get("url")))

    selected_keys = [
        key
        for key, _score in sorted(scores.items(), key=lambda item: (-item[1], mentions[item[0]]["name"].lower()))
        if scores[key] >= 2
    ][:limit]
    return {
        key: {
            **mentions[key],
            "score": scores[key],
            "id": f"resource:{_resource_slug(mentions[key]['name'])}",
        }
        for key in selected_keys
    }


def _resource_mentions(reading: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for repo in _string_list(reading.get("github_repos")):
        repo_name = _normalize_repo(repo)
        if repo_name:
            result.append(
                {
                    "key": f"github:{repo_name.lower()}",
                    "name": repo_name,
                    "kind": "github_repo",
                    "category": "github_repo",
                    "github_url": f"https://github.com/{repo_name}",
                }
            )
    for tool in _string_list(reading.get("tools")):
        name = _normalize_resource_name(tool)
        if name:
            result.append(
                {
                    "key": f"tool:{name.lower()}",
                    "name": name,
                    "kind": "tool",
                    "category": _resource_category(name),
                    "github_url": "",
                }
            )
    return result


def _resources_for_reading(
    reading: dict[str, Any],
    selected_resources: dict[str, dict[str, Any]],
    curated_resource_ids: set[str],
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mention in _resource_mentions(reading):
        selected = selected_resources.get(mention["key"])
        if not selected or selected["id"] in seen:
            continue
        if selected["id"] in curated_resource_ids:
            continue
        seen.add(selected["id"])
        resources.append(
            {
                "id": selected["id"],
                "name": selected["name"],
                "status": "needs_rewrite",
                "category": selected.get("category", ""),
                "github_url": selected.get("github_url", ""),
                "capture_reason": "既有阅读记录中多次出现，整理为待重写候选资源。",
                "summary": _text(reading.get("summary")),
                "evidence_status": "needs_source_review",
                "staleness_risk": "medium",
                "watchlist": _is_high_value(reading),
            }
        )
        if len(resources) >= 6:
            break
    return resources


def _curated_resource_ids(config: KnowledgeConfig, selected_resources: dict[str, dict[str, Any]]) -> set[str]:
    curated_ids: set[str] = set()
    for selected in selected_resources.values():
        page_type = _page_type_for_resource_name(selected["name"])
        path = _existing_or_default_page(config, selected["name"], selected["id"], page_type)
        if _is_curated_candidate_page(path):
            curated_ids.add(selected["id"])
    return curated_ids


def _write_legacy_resource_pages(
    config: KnowledgeConfig,
    readings: list[dict[str, Any]],
    selected_resources: dict[str, dict[str, Any]],
    migrated_at: str,
) -> None:
    indexes = load_hot_indexes(config)
    resource_index = indexes["resource_index"].setdefault("resources", {})
    for selected in selected_resources.values():
        related = _readings_for_resource(readings, selected["key"])
        page_type = _page_type_for_resource_name(selected["name"])
        path = page_path_for_id(config, page_type, selected["id"], selected["name"])
        curated = _is_curated_candidate_page(path)
        source_lines = [
            f"- {_markdown_link(_clean_link_label(_text(reading.get('title'))), _text(reading.get('url')))}"
            for reading in related[:8]
            if _text(reading.get("url"))
        ]
        resource_index.setdefault(selected["id"], {}).update(
            {
                "id": selected["id"],
                "name": selected["name"],
                "category": selected.get("category", ""),
                "github_url": selected.get("github_url", ""),
                "status": _frontmatter_value(path, "status") if curated else "needs_rewrite",
                "evidence_status": _frontmatter_value(path, "evidence_status") if curated else "needs_source_review",
                "staleness_risk": "medium",
                "last_seen_at": migrated_at,
                "source_count": len(related),
            }
        )
        _upsert_legacy_resource_page(
            config,
            selected,
            len(related),
            source_lines,
            migrated_at,
        )
    save_hot_index(config, "resource_index", indexes["resource_index"])


def _upsert_legacy_resource_page(
    config: KnowledgeConfig,
    selected: dict[str, Any],
    source_count: int,
    source_lines: list[str],
    migrated_at: str,
) -> None:
    page_type = _page_type_for_resource_name(selected["name"])
    path = page_path_for_id(config, page_type, selected["id"], selected["name"])
    if _is_curated_candidate_page(path):
        return
    write_page(
        path,
        {
            "id": selected["id"],
            "type": page_type,
            "status": "needs_rewrite",
            "tags": _tags_for_page_type(page_type),
            "last_verified": migrated_at[:10],
            "evidence_status": "needs_source_review",
            "staleness_risk": "medium",
            "watchlist": selected.get("score", 0) >= 10,
            "source_count": source_count,
        },
        selected["name"],
        [
            ("一句话判断", "这是从既有阅读记录中抽出的待重写候选，只说明讨论中多次出现，不代表推荐。"),
            ("它是什么", f"类别线索：{selected.get('category', '') or selected.get('kind', '') or '待补'}。对象边界需要后续复核。"),
            ("适合什么", "适合作为后续冲浪和人工筛选入口；不适合作为直接采用依据。"),
            ("不适合什么", "不适合在没有 GitHub、实测、反方和维护状态证据时直接进入稳定知识结论。"),
            ("当前结论", "标记为 `needs_rewrite`。后续只在新增证据改变判断、补足反方或准备采用时重写。"),
            (
                "关键证据",
                f"讨论信号 {selected.get('score', 0)}，关联来源 {source_count} 个；只表示出现频次和讨论热度，不代表推荐分。\n\n"
                "- 既有摘要不直接升级为知识；需要回到来源、关键回复和项目页补证据。",
            ),
            ("反方与风险", "既有阅读记录粒度不足，反方、失败案例、权限风险、维护状态和替代方案可能缺失。"),
            ("相关竞品", "暂未整理到功能相近竞品；后续应通过对比页承载。"),
            ("待验证", "回到来源、项目页、issue/release 和最新回复，只补必要证据，不主动全量重读所有来源。"),
            ("来源", "\n".join(source_lines) or "- 来源待补"),
        ],
    )


def _cleanup_legacy_candidate_pages(config: KnowledgeConfig, migrated_at: str) -> None:
    indexes = load_hot_indexes(config)
    resources = indexes["resource_index"].setdefault("resources", {})

    for name, description in BROAD_CANDIDATE_PAGES.items():
        path = _existing_or_default_page(config, name, f"resource:{_resource_slug(name)}", "collection")
        if not path.exists():
            continue
        item_id = _frontmatter_id(path) or f"resource:{_resource_slug(name)}"
        resources.setdefault(item_id, {}).update(
            {
                "id": item_id,
                "name": name,
                "status": "needs_rewrite",
                "evidence_status": "collection_placeholder",
                "staleness_risk": "high",
                "last_seen_at": migrated_at,
            }
        )
        write_page(
            path,
            {
                "id": item_id,
                "type": "collection",
                "status": "needs_rewrite",
                "tags": ["knowledge/collection", "knowledge/api-relay", "source/linuxdo"],
                "last_verified": migrated_at[:10],
                "evidence_status": "collection_placeholder",
                "staleness_risk": "high",
                "watchlist": False,
            },
            name,
            [
                ("一句话判断", "这是集合入口，不是单一资源卡；不能直接作为采用建议。"),
                ("它是什么", description),
                ("适合什么", "适合暂时承接零散线索，后续遇到具体服务、工具、教程或风险时再拆分。"),
                ("不适合什么", "不适合把宣传帖、推荐帖、管理工具、API 使用经验和风险结论混写在同一张资源卡。"),
                ("当前结论", "标记为 `needs_rewrite`。后续应拆成 Service / Collection / Claim，而不是继续堆摘要。"),
                ("关键证据", "- 既有摘要不直接升级为知识；只保留为后续复核线索。"),
                ("反方与风险", "这类信息变化快，存在失效、隐私、安全、价格、模型缩水和服务稳定性风险。"),
                ("相关竞品", "具体竞品应在拆分后的 Service 或 Comparison 页中处理。"),
                ("待验证", "准备采用具体服务前，回到原帖、服务状态和最新回复复核。"),
                ("来源", "- 来源分散在 `_system/sources/linuxdo/`，后续按具体对象补证据。"),
            ],
        )

    for alias, target in ALIAS_CANDIDATE_REDIRECTS.items():
        path = config.obsidian_vault_path / "10_Catalog" / "candidates" / f"{safe_filename(alias)}.md"
        if not path.exists():
            continue
        item_id = _frontmatter_id(path) or f"resource:{_resource_slug(alias)}"
        target_link = _candidate_link(config, target, f"resource:{_resource_slug(target)}")
        resources.setdefault(item_id, {}).update(
            {
                "id": item_id,
                "name": alias,
                "status": "duplicate",
                "evidence_status": "alias_redirect",
                "canonical": target,
                "last_seen_at": migrated_at,
            }
        )
        write_page(
            path,
            {
                "id": item_id,
                "type": "candidate",
                "status": "duplicate",
                "tags": ["source/linuxdo"],
                "last_verified": migrated_at[:10],
                "evidence_status": "alias_redirect",
                "staleness_risk": "medium",
                "watchlist": False,
                "canonical": target,
            },
            alias,
            [
                ("一句话判断", f"这个名字已经合并到 {target_link}，不要在本页继续整理证据。"),
                ("它是什么", "这是历史别名页，用来保留旧链接和你的反馈。"),
                ("适合什么", "适合做跳转和迁移提醒。"),
                ("不适合什么", "不适合继续追加来源摘要、对比意见或采用判断。"),
                ("当前结论", f"后续统一整理到 {target_link}。"),
                ("关键证据", "- 别名归一是为了避免同一个对象被拆成多张卡。"),
                ("反方与风险", "如果你认为这不是同一个对象，在 `## 我的反馈` 写明原因，下一轮同步会看到。"),
                ("相关竞品", target_link),
                ("待验证", "确认所有新证据都写入 canonical 页面。"),
                ("来源", "- 本页只作为别名保留。"),
            ],
        )

    save_hot_index(config, "resource_index", indexes["resource_index"])


def _frontmatter_id(path: Path) -> str:
    return _frontmatter_value(path, "id")


def _frontmatter_value(path: Path, key_name: str) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    if end == -1:
        return ""
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == key_name:
            return value.strip().strip("\"'")
    return ""


def _is_curated_candidate_page(path: Path) -> bool:
    status = _frontmatter_value(path, "status")
    evidence_status = _frontmatter_value(path, "evidence_status")
    return status in {"watching", "active", "needs_verification"} or evidence_status == "community_evidence"


def _candidate_link(config: KnowledgeConfig, name: str, item_id: str = "") -> str:
    stem = _page_stem_by_id(config.obsidian_vault_path, item_id) if item_id else ""
    if not stem:
        stem = safe_filename(name)
    return f"[[{stem}|{name}]]"


def _page_stem_by_id(directory: Path, item_id: str) -> str:
    if not directory.exists():
        return ""
    for path in sorted(directory.rglob("*.md")):
        if _frontmatter_id(path) == item_id:
            return path.stem
    return ""


def _page_type_for_resource_name(name: str) -> str:
    object_type = classify_knowledge_object(name)
    if object_type in {"resource", "service", "collection", "workflow", "concept", "component"}:
        return object_type
    return "candidate"


def _tags_for_page_type(page_type: str) -> list[str]:
    if page_type == "service":
        return ["knowledge/api-relay", "source/linuxdo"]
    if page_type == "collection":
        return ["knowledge/collection", "source/linuxdo"]
    if page_type == "workflow":
        return ["knowledge/workflow", "source/linuxdo"]
    if page_type == "concept":
        return ["knowledge/concept", "source/linuxdo"]
    if page_type == "component":
        return ["knowledge/component", "source/linuxdo"]
    if page_type == "resource":
        return ["knowledge/resource", "source/linuxdo"]
    return ["knowledge/candidate", "source/linuxdo"]


def _existing_or_default_page(config: KnowledgeConfig, name: str, item_id: str, page_type: str) -> Path:
    existing = page_path_for_id(config, page_type, item_id, name)
    if existing.exists():
        return existing
    old_candidate = config.obsidian_vault_path / "10_Catalog" / "candidates" / f"{safe_filename(name)}.md"
    return old_candidate if old_candidate.exists() else existing


def _replace_or_append_section(path: Path, heading: str, body: str, aliases: tuple[str, ...] = ()) -> None:
    text = path.read_text(encoding="utf-8")
    section = f"## {heading}\n\n{body.rstrip()}\n\n"
    headings = "|".join(re.escape(item) for item in (heading, *aliases))
    pattern = re.compile(rf"^##\s+({headings})\s*\n.*?(?=^##\s+|\Z)", flags=re.MULTILINE | re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(lambda _match: section, text)
    else:
        feedback_match = FEEDBACK_HEADING_PATTERN.search(text)
        if feedback_match:
            text = text[: feedback_match.start()] + section + text[feedback_match.start() :]
        else:
            text = text.rstrip() + "\n\n" + section
    path.write_text(text, encoding="utf-8")


def _write_legacy_review_page(
    config: KnowledgeConfig,
    readings: list[dict[str, Any]],
    selected_resources: dict[str, dict[str, Any]],
    batch_count: int,
    migrated_at: str,
) -> None:
    top_resources = sorted(selected_resources.values(), key=lambda item: (-int(item.get("score", 0)), item["name"].lower()))
    high_readings = [reading for reading in readings if _is_high_value(reading)]
    write_page(
        page_path_for(config, "review", "资料整理复核"),
        {
            "id": "review:source-triage",
            "type": "review",
            "status": "open",
            "tags": ["knowledge/linuxdo"],
            "last_verified": migrated_at[:10],
        },
        "资料整理复核",
        [
            ("整理结果", f"- 来源记录：{len(readings)} 条\n- 候选资源卡：{len(selected_resources)} 张\n- 底层来源/证据：在 `_system/sources/linuxdo/` 和 `_system/evidence/linuxdo/`。"),
            ("先看这些资源", _resource_review_lines(config, top_resources[:40])),
            ("高价值来源", _reading_review_lines(high_readings[:40])),
            ("不需要优先人工看的部分", "`_system/` 是底账，主要给 agent 增量检索和证据追溯用；人通常先看本页、`10_Catalog/` 和 `20_Knowledge/claims/`。"),
        ],
    )


def _resource_review_lines(config: KnowledgeConfig, resources: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {_candidate_link(config, resource['name'], _text(resource.get('id')))}：讨论信号 {resource.get('score', 0)}，来源 {len(resource.get('source_urls', []))} 条"
        for resource in resources
    )


def _reading_review_lines(readings: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {_markdown_link(_clean_link_label(_text(reading.get('title'))), _text(reading.get('url')))}：需要回原文复核后再升级为知识。"
        for reading in readings
    )


def _readings_for_resource(readings: list[dict[str, Any]], resource_key: str) -> list[dict[str, Any]]:
    result = []
    for reading in readings:
        keys = {item["key"] for item in _resource_mentions(reading)}
        if resource_key in keys:
            result.append(reading)
    return sorted(result, key=lambda item: -_value_weight(item))


def _legacy_tags(reading: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            _text(reading.get("title")),
            _text(reading.get("summary")),
            " ".join(_string_list(reading.get("tools"))),
        ]
    ).lower()
    tags: list[str] = []
    for tag, words in {
        "workflow": ("workflow", "工作流", "vibe", "vibecoding"),
        "skill": ("skill", "superpowers", "trellis", "agents.md", "claude.md"),
        "plugin": ("plugin", "插件"),
        "mcp": ("mcp",),
        "agent": ("agent", "subagent", "代理"),
        "api": ("api", "中转"),
        "github": ("github", "repo"),
    }.items():
        if any(word in text for word in words):
            tags.append(tag)
    return tags or ["legacy"]


def _reading_level(reading: dict[str, Any]) -> int:
    if _is_low_value(reading):
        return 1
    if _is_high_value(reading):
        return 2
    if reading.get("render_required") or reading.get("visual_evidence_needed"):
        return 2
    return 1


def _read_ranges(reading: dict[str, Any]) -> list[dict[str, int]]:
    highest = _highest_post_number(reading)
    return [{"from": 1, "to": highest}] if highest else []


def _highest_post_number(reading: dict[str, Any]) -> int:
    numbers = []
    for key in ("historical_replies", "recent_replies", "high_value_replies"):
        for reply in reading.get(key, []) if isinstance(reading.get(key), list) else []:
            if isinstance(reply, dict):
                parsed = _int(reply.get("post_number"), 0)
                if parsed:
                    numbers.append(parsed)
    visible = _int(reading.get("visible_post_count"), 0)
    if visible:
        numbers.append(visible)
    return max(numbers) if numbers else 0


def _key_replies(reading: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for reply in reading.get("high_value_replies", []) if isinstance(reading.get("high_value_replies"), list) else []:
        if not isinstance(reply, dict):
            continue
        result.append(
            {
                "post_number": _int(reply.get("post_number"), 0),
                "author": _text(reply.get("author")),
                "summary": _clip(_text(reply.get("text")), 240),
            }
        )
        if len(result) >= 5:
            break
    return result


def _reply_context_lines(reading: dict[str, Any]) -> list[str]:
    lines = []
    for reply in _key_replies(reading)[:3]:
        author = reply.get("author") or "unknown"
        post_number = reply.get("post_number") or "?"
        lines.append(f"高信号回复 #{post_number} @{author}: {reply.get('summary')}")
    return lines


def _stance_for(reading: dict[str, Any]) -> str:
    if _string_list(reading.get("negative_feedback")) and not _string_list(reading.get("positive_feedback")):
        return "reports_failure"
    if _string_list(reading.get("positive_feedback")) and not _string_list(reading.get("negative_feedback")):
        return "reports_success"
    if _string_list(reading.get("comparison_notes")):
        return "mentions_alternative"
    return "qualifies"


def _value_level(value: Any) -> str:
    text = _text(value)
    if text in HIGH_VALUE_TAGS:
        return "high"
    if text in MEDIUM_VALUE_TAGS:
        return "medium"
    if text in LOW_VALUE_TAGS:
        return "low"
    return text or "unknown"


def _value_weight(reading: dict[str, Any]) -> int:
    value = _text(reading.get("value_tag"))
    if value in HIGH_VALUE_TAGS:
        return 3
    if value in MEDIUM_VALUE_TAGS:
        return 2
    return 1


def _is_high_value(reading: dict[str, Any]) -> bool:
    return _text(reading.get("value_tag")) in HIGH_VALUE_TAGS


def _is_low_value(reading: dict[str, Any]) -> bool:
    return _text(reading.get("value_tag")) in LOW_VALUE_TAGS or _text(reading.get("read_status")) == "unreadable"


def _normalize_resource_name(value: Any) -> str:
    name = re.sub(r"\s+", " ", _text(value)).strip("`'\" ")
    if not name:
        return ""
    _key, display = normalize_quality_resource_name(name)
    if display.lower() in GENERIC_RESOURCE_NAMES:
        return ""
    if classify_knowledge_object(display) == "collection":
        return ""
    if len(display) < 3:
        return ""
    if re.fullmatch(r"[a-zA-Z]{1,2}", display):
        return ""
    return display


def _normalize_repo(value: Any) -> str:
    text = _text(value).strip("/")
    match = re.search(r"github\.com/([^/\s]+/[^/\s#?]+)", text)
    if match:
        text = match.group(1)
    if re.fullmatch(r"[^/\s]+/[^/\s]+", text):
        return text.lower()
    return ""


def _resource_category(name: str) -> str:
    lower = name.lower()
    if "mcp" in lower:
        return "mcp"
    if "skill" in lower or "agents.md" in lower or "claude.md" in lower:
        return "skill"
    if "api" in lower or "中转" in lower:
        return "api"
    if "workflow" in lower or "spec" in lower:
        return "workflow"
    return "tool"


def _resource_slug(name: str) -> str:
    return safe_filename(name).lower()


def _fingerprint(reading: dict[str, Any]) -> str:
    material = json.dumps(
        {
            "title": reading.get("title", ""),
            "summary": reading.get("summary", ""),
            "high_value_replies": reading.get("high_value_replies", []),
            "positive_feedback": reading.get("positive_feedback", []),
            "negative_feedback": reading.get("negative_feedback", []),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _topic_id(reading: dict[str, Any]) -> int:
    return _int(reading.get("topic_id"), 0) or _int(reading.get("id"), 0)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    clipped = text[:limit].rstrip()
    sentence_end = max(clipped.rfind("。"), clipped.rfind("；"), clipped.rfind(";"))
    if sentence_end >= max(30, limit // 2):
        clipped = clipped[: sentence_end + 1]
    return clipped.rstrip(" ，。；;") + "。"


def _clean_link_label(text: str) -> str:
    cleaned = " ".join(text.split())
    replacements = {
        "风佬巨作": "社区项目线索",
        "zcf": "相关项目",
        "高相关": "",
        "……": "（标题省略）",
        "…": "（标题省略）",
        "...": "（标题省略）",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return cleaned.strip() or "未命名来源"


def _markdown_link(label: str, url: str) -> str:
    escaped = label.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    return f"[{escaped}]({url})"
