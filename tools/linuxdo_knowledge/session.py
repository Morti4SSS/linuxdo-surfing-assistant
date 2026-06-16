from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .bookmarks import extract_topic_id
from .config import KnowledgeConfig
from .obsidian import append_log, page_path_for_id, scaffold_vault, write_page
from .quality import classify_knowledge_object, normalize_resource_name, required_sections_for_page_type
from .state import (
    append_claim_event,
    append_evidence,
    append_jsonl,
    ensure_knowledge_state,
    load_hot_indexes,
    now_iso,
    paths_for,
    save_hot_index,
    upsert_topic_summary,
)


def ingest_session(
    config: KnowledgeConfig,
    task: dict[str, Any],
    readings: dict[str, Any] | list[dict[str, Any]],
    batch_id: str,
    observed_at: str | None = None,
    write_obsidian_log: bool = True,
    written_paths: list[Path] | None = None,
) -> dict[str, int]:
    observed = observed_at or now_iso()
    scaffold_vault(config)
    ensure_knowledge_state(config)
    indexes = load_hot_indexes(config)
    _normalize_hot_indexes(indexes)
    read_items = _readings_list(readings)
    read_topic_ids = {str(topic_id) for topic_id in (_topic_id(reading) for reading in read_items) if topic_id is not None}

    for reading in read_items:
        _ingest_reading(config, indexes, reading, observed, written_paths)
    for item in _skipped_task_items(task, read_topic_ids):
        _ingest_skipped_task_item(indexes, item, observed)

    save_hot_index(config, "topic_index", indexes["topic_index"])
    save_hot_index(config, "topic_update_state", indexes["topic_update_state"])
    save_hot_index(config, "resource_index", indexes["resource_index"])
    save_hot_index(config, "claim_index", indexes["claim_index"])
    save_hot_index(config, "evidence_index", indexes["evidence_index"])
    save_hot_index(config, "evidence_by_claim", indexes["evidence_by_claim"])
    save_hot_index(config, "evidence_by_resource", indexes["evidence_by_resource"])
    save_hot_index(config, "counter_evidence_queue", indexes["counter_evidence_queue"])
    _write_session_report(config, batch_id, observed, task, read_items, written_paths)
    append_jsonl(
        paths_for(config).session_log,
        {"kind": "knowledge_session", "batch_id": batch_id, "readings": len(read_items), "observed_at": observed},
    )
    if write_obsidian_log:
        append_log(config, f"- {observed}: 会话 {_session_suffix(batch_id)} 写入 {len(read_items)} 条阅读结果。")
    return {"readings": len(read_items)}


def _ingest_skipped_task_item(indexes: dict[str, Any], item: dict[str, Any], observed_at: str) -> None:
    topic_id = _topic_id(item) or extract_topic_id(_text(item.get("url")))
    if topic_id is None:
        return

    topic_key = str(topic_id)
    existing_topic = indexes["topic_index"].setdefault("topics", {}).get(topic_key, {})
    if not isinstance(existing_topic, dict):
        existing_topic = {}
    topic_item = {**existing_topic, "topic_id": topic_id, "last_seen_at": observed_at}
    if _text(item.get("title")):
        topic_item["title"] = _text(item.get("title"))
    if _text(item.get("url")):
        topic_item["url"] = _text(item.get("url"))
    topic_item.setdefault("status", "active")
    topic_item["skip_count"] = _int(topic_item.get("skip_count"), 0) + 1
    topic_item["skip_reason"] = _text(item.get("skip_reason")) or _text(item.get("action"))
    indexes["topic_index"].setdefault("topics", {})[topic_key] = topic_item

    existing_update = indexes["topic_update_state"].setdefault("topics", {}).get(topic_key, {})
    if not isinstance(existing_update, dict):
        existing_update = {}
    update_item = {**existing_update, "topic_id": topic_id, "last_seen_at": observed_at}
    if "reply_count" in item:
        update_item["reply_count"] = _int(item.get("reply_count"), 0)
    if "last_activity_at" in item:
        update_item["last_activity_at"] = _text(item.get("last_activity_at"))
    if "skip_reason" in item:
        update_item["skip_reason"] = _text(item.get("skip_reason"))
    indexes["topic_update_state"].setdefault("topics", {})[topic_key] = update_item


def _ingest_reading(
    config: KnowledgeConfig,
    indexes: dict[str, Any],
    reading: dict[str, Any],
    observed_at: str,
    written_paths: list[Path] | None = None,
) -> None:
    topic_id = _topic_id(reading)
    if topic_id is None:
        return

    topic_key = str(topic_id)
    resource_ids = [item["id"] for item in _dict_list(reading.get("resources")) if item.get("id")]
    claim_ids = [item["id"] for item in _dict_list(reading.get("claims")) if item.get("id")]

    existing_topic = indexes["topic_index"].setdefault("topics", {}).get(topic_key, {})
    if not isinstance(existing_topic, dict):
        existing_topic = {}
    topic_item = {**existing_topic, "topic_id": topic_id, "last_seen_at": observed_at}
    if _text(reading.get("title")):
        topic_item["title"] = _text(reading.get("title"))
    if _text(reading.get("url")):
        topic_item["url"] = _text(reading.get("url"))
    if "resources" in reading:
        topic_item["resource_ids"] = resource_ids
    else:
        topic_item.setdefault("resource_ids", [])
    if "claims" in reading:
        topic_item["claim_ids"] = claim_ids
    else:
        topic_item.setdefault("claim_ids", [])
    if "value_level" in reading:
        topic_item["value_level"] = _text(reading.get("value_level")) or "unknown"
    else:
        topic_item.setdefault("value_level", "unknown")
    if "tags" in reading:
        topic_item["tags"] = _string_list(reading.get("tags"))
    else:
        topic_item.setdefault("tags", [])
    if "status" in reading:
        topic_item["status"] = _text(reading.get("status")) or "active"
    else:
        topic_item.setdefault("status", "active")
    if "watchlist" in reading:
        topic_item["watchlist"] = bool(reading.get("watchlist", False))
    else:
        topic_item.setdefault("watchlist", False)
    indexes["topic_index"].setdefault("topics", {})[topic_key] = topic_item
    existing_update = indexes["topic_update_state"].setdefault("topics", {}).get(topic_key, {})
    if not isinstance(existing_update, dict):
        existing_update = {}
    update_item = {**existing_update, "topic_id": topic_id, "last_read_at": observed_at}
    if "reply_count" in reading:
        update_item["read_reply_count"] = _int(reading.get("reply_count"), 0)
    if "last_activity_at" in reading:
        update_item["last_activity_at"] = _text(reading.get("last_activity_at"))
    if "reading_level" in reading:
        update_item["last_reading_level"] = _int(reading.get("reading_level"), 1)
    else:
        update_item.setdefault("last_reading_level", 1)
    if "watchlist" in reading:
        update_item["watchlist"] = bool(reading.get("watchlist", False))
    if "has_unresolved_dispute" in reading:
        update_item["has_unresolved_dispute"] = bool(reading.get("has_unresolved_dispute", False))
    for field in ("highest_post_number", "highest_post_id", "read_ranges", "content_fingerprint"):
        if field in reading:
            update_item[field] = reading[field]
    indexes["topic_update_state"].setdefault("topics", {})[topic_key] = update_item
    upsert_topic_summary(
        config,
        topic_id,
        {
            "title": _text(reading.get("title")),
            "url": _text(reading.get("url")),
            "summary": _text(reading.get("summary")),
            "value_level": _text(reading.get("value_level")) or "unknown",
            "tags": _string_list(reading.get("tags")),
            "key_replies": reading.get("key_replies", []),
            "resources": _dict_list(reading.get("resources")),
            "claims": _dict_list(reading.get("claims")),
        },
    )

    for resource in _dict_list(reading.get("resources")):
        _upsert_resource(config, indexes["resource_index"], resource, reading, observed_at, written_paths)
    for claim in _dict_list(reading.get("claims")):
        _upsert_claim(config, indexes["claim_index"], claim, reading, observed_at, written_paths)

    evidence_items = [
        _normalized_evidence_item(evidence, reading, topic_id, index)
        for index, evidence in enumerate(_dict_list(reading.get("evidence")), start=1)
    ]
    for evidence in evidence_items:
        evidence_payload = {
            **evidence,
            "source_type": "linuxdo_topic",
            "source_url": _text(reading.get("url")),
            "topic_id": topic_id,
            "resource_ids": resource_ids,
            "claim_ids": claim_ids,
        }
        append_evidence(config, evidence_payload, observed_at=observed_at)
        _upsert_evidence_edges(indexes, evidence_payload, observed_at)

    _write_source_page(config, reading, evidence_items, observed_at, written_paths)
    _write_evidence_pages(config, reading, evidence_items, observed_at, written_paths)
    _write_related_pages(config, reading, observed_at, written_paths)


def _upsert_resource(
    config: KnowledgeConfig,
    resource_index: dict[str, Any],
    resource: dict[str, Any],
    reading: dict[str, Any],
    observed_at: str,
    written_paths: list[Path] | None = None,
) -> None:
    resource_id = _text(resource.get("id"))
    if not resource_id:
        return

    existing = resource_index.setdefault("resources", {}).get(resource_id, {})
    if not isinstance(existing, dict):
        existing = {}
    merged = _merge_non_empty(
        existing,
        _resource_hot_index_item(resource, reading, observed_at),
    )
    merged.setdefault("status", "candidate")
    merged.setdefault("evidence_status", "open_question")
    merged.setdefault("staleness_risk", "medium")
    merged.setdefault("watchlist", False)
    resource_index.setdefault("resources", {})[resource_id] = merged
    name = _text(resource.get("name")) or resource_id
    page_type = _page_type_for_resource(resource, merged, name)
    if _should_preserve_existing_page(config, page_type, resource_id, name):
        return
    if page_type == "service":
        source_links = _source_links(reading)
        source_ref = _source_ref(reading)
        sections = [
            ("一句话判断", _field_text(resource, "summary", default="这是一个待补证据的服务线索，暂不作为推荐结论。")),
            ("它是什么", _field_text(resource, "description", "problem", default="需要补充服务边界，避免把大类概念当成单一服务。")),
            ("适合什么", _field_text(resource, "use_cases", default="需要更多使用场景证据。")),
            ("不适合什么", _field_text(resource, "limits", "not_for", default="需要补充反方、限制或不适用场景。")),
            ("稳定性", _field_text(resource, "stability", "stability_notes", default="需要持续观察可用性、版本兼容和服务端变化。")),
            ("隐私/安全风险", _field_text(resource, "privacy_risk", "security_risk", "security", default="需要复核密钥、账号、请求内容和本地存储等安全边界。")),
            ("价格/额度变化风险", _field_text(resource, "pricing_risk", "quota_risk", "pricing", default="需要复核价格、额度、限流和免费策略是否变化。")),
            ("当前结论", _field_text(resource, "current_judgment", "capture_reason", default="先作为线索观察，采用前必须回到来源和项目页复核。")),
            ("关键证据", _field_text(resource, "key_evidence", default=f"- {source_ref}")),
            ("反方与风险", _field_text(resource, "risks", "missing_evidence", default="反方和风险证据不足。")),
            ("相关竞品", _field_text(resource, "alternatives", "comparison", default="暂未整理到功能相近竞品。")),
            ("待验证", _field_text(resource, "next_verification", default="再次遇到相关讨论或 GitHub 验证自然触及时再更新。")),
            ("来源", source_links),
        ]
    elif page_type == "workflow":
        source_links = _source_links(reading)
        source_ref = _source_ref(reading)
        sections = [
            ("一句话判断", _field_text(resource, "summary", default="这是一个待补证据的工作流线索，暂不作为推荐结论。")),
            ("它是什么", _field_text(resource, "description", "problem", default="需要补充工作流边界、入口和产出。")),
            ("适合什么", _field_text(resource, "use_cases", default="需要更多使用场景证据。")),
            ("不适合什么", _field_text(resource, "limits", "not_for", default="需要补充反方、限制或不适用场景。")),
            ("当前结论", _field_text(resource, "current_judgment", "capture_reason", default="先作为线索观察，采用前必须回到来源和项目页复核。")),
            ("核心步骤", _field_text(resource, "steps", "method", default="来源未提供足够可复用步骤。")),
            ("关键证据", _field_text(resource, "key_evidence", default=f"- {source_ref}")),
            ("反方与风险", _field_text(resource, "risks", "missing_evidence", default="反方和风险证据不足。")),
            ("相关对比", _field_text(resource, "comparison", "alternatives", default="暂未整理到明确对比对象。")),
            ("待验证", _field_text(resource, "next_verification", default="再次遇到相关讨论或 GitHub 验证自然触及时再更新。")),
            ("来源", source_links),
        ]
    elif page_type == "collection":
        source_links = _source_links(reading)
        source_ref = _source_ref(reading)
        sections = [
            ("一句话判断", _field_text(resource, "summary", default="这是一个待补证据的集合线索，暂不作为推荐结论。")),
            ("收录范围", _field_text(resource, "scope", "items", "use_cases", default="只收录当前来源明确提到、且后续值得复核的对象。")),
            ("不收录什么", _field_text(resource, "exclusions", "limits", "not_for", default="不收录只有泛泛提及、无法定位来源或风险不可控的对象。")),
            ("阅读顺序", _field_text(resource, "reading_order", "method", default="先读代表页面，再按维护状态、风险和真实反馈筛选。")),
            ("代表页面", _field_text(resource, "representative_pages", "resources", default=f"- {source_ref}")),
            ("风险", _field_text(resource, "risks", "missing_evidence", default="集合页只说明线索范围，不代表每个条目都值得采用。")),
            ("来源", source_links),
        ]
    elif page_type == "concept":
        source_links = _source_links(reading)
        source_ref = _source_ref(reading)
        sections = [
            ("一句话判断", _field_text(resource, "summary", default="这是一个待补证据的概念线索，暂不作为推荐结论。")),
            ("概念边界", _field_text(resource, "boundary", "description", "problem", default="需要补充概念边界，避免把概念写成具体工具推荐。")),
            ("常见误读", _field_text(resource, "misconceptions", "common_misreadings", "risks", default="需要补充常见误读和容易混淆的对象。")),
            ("适合沉淀什么", _field_text(resource, "use_cases", "fit_for", default="适合沉淀判断框架、对象边界和跨页面路由规则。")),
            ("不适合沉淀什么", _field_text(resource, "limits", "not_for", default="不适合直接写成采用建议；具体选择要回到资源卡或对比页。")),
            ("关键证据", _field_text(resource, "key_evidence", default=f"- {source_ref}")),
            ("相关页面", _field_text(resource, "related_pages", "related_resources", "alternatives", "comparison", default="暂未整理到明确相关页面。")),
            ("待验证", _field_text(resource, "next_verification", default="再次遇到改变概念边界、常见误区或应用规则的新证据时再更新。")),
            ("来源", source_links),
        ]
    elif page_type == "component":
        source_links = _source_links(reading)
        source_ref = _source_ref(reading)
        sections = [
            ("一句话判断", _field_text(resource, "summary", default="这是一个待补证据的工作流组件线索，暂不作为推荐结论。")),
            ("触发条件", _field_text(resource, "trigger_conditions", "triggers", "use_cases", default="需要补充什么时候应该启用这个组件。")),
            ("停止条件", _field_text(resource, "stop_conditions", "limits", "not_for", default="需要补充什么时候应该停止或跳过这个组件。")),
            ("适合什么", _field_text(resource, "use_cases", "fit_for", default="适合作为明确阶段的可插拔能力，而不是默认替代完整工作流。")),
            ("不适合什么", _field_text(resource, "limits", "not_for", default="不适合在缺少输入、输出和验收边界时默认使用。")),
            ("关键证据", _field_text(resource, "key_evidence", default=f"- {source_ref}")),
            ("相关对比", _field_text(resource, "comparison", "alternatives", "related_pages", default="暂未整理到明确对比对象。")),
            ("待验证", _field_text(resource, "next_verification", default="再次遇到相关讨论或 GitHub 验证自然触及时再更新。")),
            ("来源", source_links),
        ]
    elif page_type in {"resource", "candidate"}:
        source_links = _source_links(reading)
        source_ref = _source_ref(reading)
        sections = [
            ("一句话判断", _field_text(resource, "summary", default="这是一个待补证据的候选资源，暂不作为推荐结论。")),
            ("它是什么", _field_text(resource, "description", "problem", default="需要补充对象边界，避免把大类概念当成单一资源。")),
            ("适合什么", _field_text(resource, "use_cases", default="需要更多使用场景证据。")),
            ("不适合什么", _field_text(resource, "limits", "not_for", default="需要补充反方、限制或不适用场景。")),
            ("当前结论", _field_text(resource, "current_judgment", "capture_reason", default="先作为线索观察，采用前必须回到来源和项目页复核。")),
            ("关键证据", _field_text(resource, "key_evidence", default=f"- {source_ref}")),
            ("反方与风险", _field_text(resource, "risks", "missing_evidence", default="反方和风险证据不足。")),
            ("相关竞品", _field_text(resource, "alternatives", "comparison", default="暂未整理到功能相近竞品。")),
            ("待验证", _field_text(resource, "next_verification", default="再次遇到相关讨论或 GitHub 验证自然触及时再更新。")),
            ("来源", source_links),
        ]
    else:
        sections = [
            ("Agent 摘要", _text(resource.get("summary")) or _text(reading.get("summary"))),
            ("解决什么问题", _text(resource.get("problem"))),
            ("适用场景", _text(resource.get("use_cases"))),
            ("社区评价", _text(resource.get("community_view"))),
            ("相关对比", _text(resource.get("comparison"))),
            ("来源", _source_links(reading)),
        ]
    _write_item_page(config, page_type, merged, observed_at, sections, written_paths)


def _upsert_claim(
    config: KnowledgeConfig,
    claim_index: dict[str, Any],
    claim: dict[str, Any],
    reading: dict[str, Any],
    observed_at: str,
    written_paths: list[Path] | None = None,
) -> None:
    claim_id = _text(claim.get("id"))
    if not claim_id:
        return
    existing = claim_index.setdefault("claims", {}).get(claim_id, {})
    if not isinstance(existing, dict):
        existing = {}
    merged = _merge_non_empty(
        existing,
        _claim_hot_index_item(claim, observed_at),
    )
    merged.setdefault("status", "active")
    merged.setdefault("evidence_status", "open_question")
    merged.setdefault("staleness_risk", "medium")
    claim_index.setdefault("claims", {})[claim_id] = merged
    _append_claim_change_event(config, claim_id, existing, merged, reading, observed_at)
    claim_page = {**claim, **merged}
    _write_item_page(
        config,
        "claim",
        claim_page,
        observed_at,
        [
            ("当前判断", _clean_human_text(claim_page.get("text")) or _clean_human_text(claim_page.get("summary"))),
            ("支持证据", _markdown_value(claim_page.get("supports"))),
            ("反方观点", _markdown_value(claim_page.get("opposes") or claim_page.get("counter_arguments"))),
            ("未知和待验证", _markdown_value(claim_page.get("unknowns") or claim_page.get("next_verification"))),
            ("来源", f"- {_text(reading.get('url'))}"),
        ],
        written_paths,
    )


def _write_source_page(
    config: KnowledgeConfig,
    reading: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    observed_at: str,
    written_paths: list[Path] | None = None,
) -> None:
    topic_id = _topic_id(reading)
    if topic_id is None:
        return

    related_links = [f"- [[{_evidence_page_name(evidence, topic_id, index)}]]" for index, evidence in enumerate(evidence_items, start=1)]
    related_links.extend(f"- {item}" for item in _string_list(reading.get("related_pages")))
    status_lines = _compact_lines(
        [
            ("value_level", _text(reading.get("value_level"))),
            ("status", _text(reading.get("status"))),
            ("read_level", _text(reading.get("reading_level"))),
            ("reply_count", _text(reading.get("reply_count"))),
            ("last_activity_at", _text(reading.get("last_activity_at"))),
        ]
    )
    path = write_page(
        page_path_for_id(config, "linuxdo_source", f"source:linuxdo:{topic_id}", f"linuxdo-topic-{topic_id}"),
        {
            "id": f"source:linuxdo:{topic_id}",
            "type": "source",
            "source_type": "linuxdo_topic",
            "url": _text(reading.get("url")),
            "title": _text(reading.get("title")),
            "author": _text(reading.get("author")),
            "captured_at": observed_at[:10],
            "last_seen_at": observed_at[:10],
            "read_level": _int(reading.get("reading_level"), 1),
            "state_key": f"topic:{topic_id}",
            "related_evidence": [item["id"] for item in evidence_items if item.get("id")],
        },
        f"linuxdo-topic-{topic_id}",
        [
            ("来源摘要", _clean_human_text(_text(reading.get("summary"))) or "只记录来源元信息，暂未形成可升级证据。"),
            ("读取状态", status_lines),
            ("相关页", "\n".join(related_links)),
        ],
        include_feedback=False,
    )
    _record_written_path(written_paths, path)


def _write_evidence_pages(
    config: KnowledgeConfig,
    reading: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    observed_at: str,
    written_paths: list[Path] | None = None,
) -> None:
    topic_id = _topic_id(reading)
    if topic_id is None:
        return

    for index, evidence in enumerate(evidence_items, start=1):
        name = _evidence_page_name(evidence, topic_id, index)
        title = _clean_title(_text(evidence.get("name")) or _text(evidence.get("title")) or f"Linux.do {topic_id} evidence {index}")
        path = write_page(
            page_path_for_id(config, "linuxdo_evidence", _text(evidence.get("id")), name),
            {
                "id": _text(evidence.get("id")),
                "type": "evidence",
                "source_id": _text(evidence.get("source_id")) or f"source:linuxdo:{topic_id}",
                "source": f"[[linuxdo-topic-{topic_id}]]",
                "stance": _text(evidence.get("stance")) or "qualifies",
                "confidence": _text(evidence.get("confidence")) or _text(reading.get("confidence")) or "medium",
                "evidence_kind": _text(evidence.get("evidence_kind")) or "community_signal",
                "claim_refs": _string_list(evidence.get("claim_refs")),
                "resource_refs": _string_list(evidence.get("resource_refs")),
                "captured_at": observed_at[:10],
            },
            title,
            [
                ("证据摘要", _clean_human_text(_text(evidence.get("summary")))),
                ("最小上下文", _markdown_value(evidence.get("minimal_context"))),
                ("风险", _markdown_value(evidence.get("risk"))),
                ("相关来源", f"- [[linuxdo-topic-{topic_id}]]\n- {_text(reading.get('url'))}"),
            ],
            include_feedback=False,
        )
        _record_written_path(written_paths, path)


def _write_related_pages(
    config: KnowledgeConfig,
    reading: dict[str, Any],
    observed_at: str,
    written_paths: list[Path] | None = None,
) -> None:
    for item in _dict_list(reading.get("comparisons")):
        _write_item_page(
            config,
            "comparison",
            item,
            observed_at,
            [
                ("当前结论", _clean_human_text(item.get("summary"))),
                ("比较范围", _field_text(item, "scope", default="只比较当前来源中被明确提到的选项，不代表通用排名。")),
                ("入口选项", _markdown_value(_string_list(item.get("popular_choices")) + _string_list(item.get("potential_choices")))),
                ("各派意见", _markdown_value(item.get("disputes"))),
                ("评价维度", _markdown_value(item.get("dimensions"))),
                ("适合选择", _field_text(item, "suitable_for", "use_cases", default="需要更多场景证据后再给出选择建议。")),
                ("不适合选择", _field_text(item, "not_suitable_for", "limits", default="缺少反方场景时，不应写成单向推荐。")),
                ("为什么", _field_text(item, "why", "summary", default="当前只记录社区线索，采用前需要回到来源和项目页复核。")),
                ("待验证", _field_text(item, "next_verification", default="复核维护状态、真实使用反馈和替代方案。")),
                ("相关资源", _markdown_value(item.get("resources"))),
                ("证据与来源", f"- {_text(reading.get('url'))}"),
            ],
            written_paths,
        )
    for item in _dict_list(reading.get("workflows")):
        _write_item_page(
            config,
            "workflow",
            item,
            observed_at,
            [
                ("一句话判断", _field_text(item, "summary", default="这是一个待补证据的工作流线索，暂不作为推荐结论。")),
                ("它是什么", _field_text(item, "description", "problem", default="需要补充工作流边界、入口和产出。")),
                ("适合什么", _field_text(item, "use_cases", default="需要更多使用场景证据。")),
                ("不适合什么", _field_text(item, "limits", "not_for", default="需要补充反方、限制或不适用场景。")),
                ("当前结论", _field_text(item, "current_judgment", "capture_reason", default="先作为线索观察，采用前必须回到来源和项目页复核。")),
                ("核心步骤", _field_text(item, "steps", "method", default="来源未提供足够可复用步骤。")),
                ("关键证据", _field_text(item, "key_evidence", default=f"- {_source_ref(reading)}")),
                ("反方与风险", _field_text(item, "risks", "missing_evidence", default="反方和风险证据不足。")),
                ("相关对比", _field_text(item, "comparison", "alternatives", default=_markdown_value(item.get("resources")) or "暂未整理到明确对比对象。")),
                ("待验证", _field_text(item, "next_verification", default="再次遇到相关讨论或 GitHub 验证自然触及时再更新。")),
                ("来源", f"- {_text(reading.get('url'))}"),
            ],
            written_paths,
        )
    for item in _dict_list(reading.get("knowledge_drafts")):
        _write_item_page(
            config,
            "draft",
            item,
            observed_at,
            [
                ("核心观点", _clean_human_text(item.get("summary"))),
                ("方法", _markdown_value(item.get("method"))),
                ("适用场景", _markdown_value(item.get("use_cases"))),
                ("限制与反例", _markdown_value(item.get("limits"))),
                ("来源", f"- {_text(reading.get('url'))}"),
            ],
            written_paths,
        )
    for item in _dict_list(reading.get("categories")):
        _write_item_page(
            config,
            "category",
            item,
            observed_at,
            [
                ("资源索引", _markdown_value(item.get("items"))),
                ("来源", f"- {_text(reading.get('url'))}"),
            ],
            written_paths,
        )


def _write_item_page(
    config: KnowledgeConfig,
    page_type: str,
    item: dict[str, Any],
    observed_at: str,
    sections: list[tuple[str, str]],
    written_paths: list[Path] | None = None,
) -> None:
    item_id = _text(item.get("id"))
    if not item_id:
        return

    name = _clean_title(_text(item.get("name")) or item_id)
    path = write_page(
        page_path_for_id(config, page_type, item_id, name),
        {
            "id": item_id,
            "type": _frontmatter_type_for_page_type(page_type),
            "status": _text(item.get("status")) or _default_status_for_page_type(page_type),
            "tags": _tags_for_page_type(page_type),
            "last_verified": observed_at[:10],
            "evidence_status": _text(item.get("evidence_status")) or "open_question",
            "staleness_risk": _text(item.get("staleness_risk")) or "medium",
            "watchlist": bool(item.get("watchlist", False)),
        },
        name,
        sections,
    )
    _record_written_path(written_paths, path)


def _write_session_report(
    config: KnowledgeConfig,
    batch_id: str,
    observed_at: str,
    task: dict[str, Any],
    readings: list[dict[str, Any]],
    written_paths: list[Path] | None = None,
) -> None:
    task_items = task.get("items", []) if isinstance(task, dict) else []
    session_suffix = _session_suffix(batch_id)
    path = config.obsidian_vault_path / "90_Inbox" / "sessions" / f"{observed_at[:10]}-session-{session_suffix}.md"
    findings = "\n".join(
        f"- {_clean_title(_text(reading.get('title')))}: {_clean_human_text(_text(reading.get('summary')))}" for reading in readings
    )
    skipped = "\n".join(
        f"- {_clean_title(_text(item.get('title')))}: {_clean_human_text(_text(item.get('skip_reason')))}"
        for item in _dict_list(task_items)
        if item.get("skip_reason")
    )
    path = write_page(
        path,
        {
            "id": f"session:{observed_at[:10]}-session-{session_suffix}",
            "type": "session",
            "status": "active",
            "tags": ["session"],
            "last_verified": observed_at[:10],
        },
        f"{observed_at[:10]} 阅读记录 {session_suffix}",
        [
            ("本次范围", f"{len(_dict_list(task_items))} 个候选，{len(readings)} 个阅读结果。"),
            ("新发现", findings),
            ("候选资源", _session_resource_list(readings)),
            ("资源更新", ""),
            ("对比/争议", _session_named_list(readings, "comparisons")),
            ("只记录为证据的内容", ""),
            ("跳过与原因", skipped),
            ("下一批建议", ""),
        ],
    )
    _record_written_path(written_paths, path)


def _resource_hot_index_item(resource: dict[str, Any], reading: dict[str, Any], observed_at: str) -> dict[str, Any]:
    resource_id = _text(resource.get("id"))
    item = {
        "id": resource_id,
        "name": _text(resource.get("name")) or resource_id,
        "url": _text(resource.get("url")),
        "github_url": _text(resource.get("github_url")),
        "category": _text(resource.get("category")),
        "last_seen_at": observed_at,
        "source_url": _text(reading.get("url")),
    }
    for field in ("status", "evidence_status", "staleness_risk"):
        if field in resource:
            item[field] = _text(resource.get(field))
    if "watchlist" in resource:
        item["watchlist"] = bool(resource.get("watchlist", False))
    return item


def _claim_hot_index_item(claim: dict[str, Any], observed_at: str) -> dict[str, Any]:
    claim_id = _text(claim.get("id"))
    item = {
        "id": claim_id,
        "text": _text(claim.get("text")) or claim_id,
        "last_seen_at": observed_at,
    }
    for field in (
        "status",
        "evidence_status",
        "staleness_risk",
        "resolved_at",
        "fix_version",
        "verified_at",
        "supports",
        "opposes",
        "counter_arguments",
        "unknowns",
        "next_verification",
    ):
        if field in claim:
            value = claim.get(field)
            item[field] = _text(value) if isinstance(value, (str, int, float, bool)) or value is None else value
    return item


COUNTER_EVIDENCE_STANCES = {"negative_feedback", "reports_failure", "opposes", "corrects"}
RISK_REVIEW_STANCES = {"disputes", "risk_boundary", "warns", "risk_signal", "needs_review"}
SUPPORTING_EVIDENCE_STANCES = {"supports", "supporting_signal", "reports_success", "qualifies"}
CLAIM_EVENT_FIELDS = ("status", "evidence_status", "resolved_at", "fix_version", "verified_at")


def _append_claim_change_event(
    config: KnowledgeConfig,
    claim_id: str,
    existing: dict[str, Any],
    merged: dict[str, Any],
    reading: dict[str, Any],
    observed_at: str,
) -> None:
    changed_fields = [
        field
        for field in CLAIM_EVENT_FIELDS
        if _text(existing.get(field)) != _text(merged.get(field)) and _text(merged.get(field))
    ]
    if not changed_fields:
        return

    append_claim_event(
        config,
        {
            "kind": "claim_event",
            "event_type": "claim_changed" if existing else "claim_created",
            "claim_id": claim_id,
            "topic_id": _topic_id(reading),
            "source_url": _text(reading.get("url")),
            "changed_fields": changed_fields,
            "before": {field: existing.get(field) for field in changed_fields},
            "after": {field: merged.get(field) for field in changed_fields},
        },
        observed_at=observed_at,
    )


def _upsert_evidence_edges(indexes: dict[str, Any], evidence: dict[str, Any], observed_at: str) -> None:
    evidence_id = _text(evidence.get("id"))
    if not evidence_id:
        return

    evidence_index = indexes.setdefault("evidence_index", {}).setdefault("evidence", {})
    existing = evidence_index.get(evidence_id, {})
    if not isinstance(existing, dict):
        existing = {}

    claim_ids = _unique_texts(evidence.get("claim_refs")) or _unique_texts(evidence.get("claim_ids"))
    resource_ids = _unique_texts(evidence.get("resource_refs")) or _unique_texts(evidence.get("resource_ids"))
    stance = _text(evidence.get("stance")) or "qualifies"
    relation = _evidence_relation(stance)
    payload_hash = _stable_payload_hash(evidence)
    payload_hashes = _append_unique(_string_list(existing.get("payload_hashes")), payload_hash)
    edge = {
        "id": evidence_id,
        "source_id": _text(evidence.get("source_id")),
        "source_type": _text(evidence.get("source_type")),
        "source_url": _text(evidence.get("source_url")),
        "topic_id": evidence.get("topic_id"),
        "summary": _text(evidence.get("summary")),
        "confidence": _text(evidence.get("confidence")),
        "stance": stance,
        "evidence_kind": _text(evidence.get("evidence_kind") or evidence.get("kind")),
        "claim_ids": claim_ids,
        "resource_ids": resource_ids,
        "relation": relation,
        "minimal_context": evidence.get("minimal_context", ""),
        "risk": evidence.get("risk", ""),
        "redaction_level": _text(evidence.get("redaction_level")) or "safe_summary",
        "seen_count": _int(existing.get("seen_count"), 0) + 1,
        "payload_hashes": payload_hashes,
        "payload_variant_count": len(payload_hashes),
        "first_seen_at": existing.get("first_seen_at") or observed_at,
        "last_seen_at": observed_at,
    }
    evidence_index[evidence_id] = edge

    for claim_id in claim_ids:
        claim_edge = _upsert_evidence_bucket(
            indexes.setdefault("evidence_by_claim", {}).setdefault("claims", {}),
            claim_id,
            "claim_id",
            evidence_id,
            relation,
            observed_at,
        )
        if relation in {"counter", "risk_review"}:
            _upsert_counter_evidence_queue(indexes, claim_edge["claim_id"], edge, relation, observed_at)

    for resource_id in resource_ids:
        _upsert_evidence_bucket(
            indexes.setdefault("evidence_by_resource", {}).setdefault("resources", {}),
            resource_id,
            "resource_id",
            evidence_id,
            relation,
            observed_at,
        )


def _upsert_evidence_bucket(
    buckets: dict[str, Any],
    key: str,
    key_field: str,
    evidence_id: str,
    relation: str,
    observed_at: str,
) -> dict[str, Any]:
    bucket = buckets.get(key, {})
    if not isinstance(bucket, dict):
        bucket = {}
    bucket[key_field] = key
    bucket["evidence_ids"] = _append_unique(_string_list(bucket.get("evidence_ids")), evidence_id)
    bucket["supporting_evidence_ids"] = _append_unique(
        _string_list(bucket.get("supporting_evidence_ids")),
        evidence_id,
    ) if relation == "supporting" else _string_list(bucket.get("supporting_evidence_ids"))
    bucket["counter_evidence_ids"] = _append_unique(
        _string_list(bucket.get("counter_evidence_ids")),
        evidence_id,
    ) if relation == "counter" else _string_list(bucket.get("counter_evidence_ids"))
    bucket["risk_review_evidence_ids"] = _append_unique(
        _string_list(bucket.get("risk_review_evidence_ids")),
        evidence_id,
    ) if relation == "risk_review" else _string_list(bucket.get("risk_review_evidence_ids"))
    bucket["first_seen_at"] = bucket.get("first_seen_at") or observed_at
    bucket["last_seen_at"] = observed_at
    buckets[key] = bucket
    return bucket


def _upsert_counter_evidence_queue(
    indexes: dict[str, Any],
    claim_id: str,
    evidence: dict[str, Any],
    relation: str,
    observed_at: str,
) -> None:
    queue = indexes.setdefault("counter_evidence_queue", {}).setdefault("items", [])
    if not isinstance(queue, list):
        queue = []
        indexes["counter_evidence_queue"]["items"] = queue
    item_id = f"counter:{claim_id}:{evidence['id']}"
    existing = next((item for item in queue if isinstance(item, dict) and item.get("id") == item_id), None)
    item = existing if isinstance(existing, dict) else {"id": item_id, "created_at": observed_at, "status": "open"}
    item.update(
        {
            "claim_id": claim_id,
            "evidence_id": evidence["id"],
            "resource_ids": evidence.get("resource_ids", []),
            "topic_id": evidence.get("topic_id"),
            "source_url": evidence.get("source_url", ""),
            "stance": evidence.get("stance", ""),
            "confidence": evidence.get("confidence", ""),
            "summary": evidence.get("summary", ""),
            "queue_kind": "counter_evidence" if relation == "counter" else "risk_review",
            "last_seen_at": observed_at,
        }
    )
    if existing is None:
        queue.append(item)


def _evidence_relation(stance: str) -> str:
    normalized = stance.strip().lower()
    if normalized in COUNTER_EVIDENCE_STANCES:
        return "counter"
    if normalized in RISK_REVIEW_STANCES:
        return "risk_review"
    if normalized in SUPPORTING_EVIDENCE_STANCES:
        return "supporting"
    return "related"


def _stable_payload_hash(evidence: dict[str, Any]) -> str:
    payload = {key: value for key, value in evidence.items() if key != "observed_at"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalized_evidence_item(
    evidence: dict[str, Any],
    reading: dict[str, Any],
    topic_id: int,
    index: int,
) -> dict[str, Any]:
    item = dict(evidence)
    item.setdefault("id", f"evidence:linuxdo:{topic_id}:{index}")
    item.setdefault("source_id", f"source:linuxdo:{topic_id}")
    item.setdefault("summary", _text(reading.get("summary")))
    item.setdefault("confidence", _text(reading.get("confidence")) or "medium")
    item.setdefault("evidence_kind", "community_signal")
    return item


def _evidence_page_name(evidence: dict[str, Any], topic_id: int, index: int) -> str:
    name = _text(evidence.get("name")) or _text(evidence.get("title"))
    if name:
        return name
    evidence_id = _text(evidence.get("id")).split(":")[-1]
    suffix = evidence_id if evidence_id and evidence_id != str(index) else f"evidence-{index}"
    return f"linuxdo-{topic_id}-{suffix}"


def _readings_list(readings: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(readings, list):
        return [item for item in readings if isinstance(item, dict)]
    if not isinstance(readings, dict):
        return []
    value = readings.get("readings", readings.get("topics", []))
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _skipped_task_items(task: dict[str, Any], read_topic_ids: set[str]) -> list[dict[str, Any]]:
    task_items = task.get("items", []) if isinstance(task, dict) else []
    skipped: list[dict[str, Any]] = []
    for item in _dict_list(task_items):
        if item.get("action") not in ("skip", "metadata_only"):
            continue
        topic_id = _topic_id(item) or extract_topic_id(_text(item.get("url")))
        if topic_id is not None and str(topic_id) in read_topic_ids:
            continue
        skipped.append(item)
    return skipped


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _unique_texts(value: Any) -> list[str]:
    result: list[str] = []
    seen = set()
    for item in _string_list(value):
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _append_unique(values: list[str], value: str) -> list[str]:
    if value not in values:
        values.append(value)
    return values


def _record_written_path(written_paths: list[Path] | None, path: Path | None) -> None:
    if written_paths is None or path is None:
        return
    if path not in written_paths:
        written_paths.append(path)


def _markdown_value(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {_clean_human_text(item)}" for item in value)
    return _clean_human_text(value)


def _field_text(item: dict[str, Any], *keys: str, default: str, limit: int = 220) -> str:
    for key in keys:
        value = item.get(key)
        if value in ("", None, []):
            continue
        if isinstance(value, list):
            return _markdown_value(value)
        return _clip_human_text(value, limit)
    return default


def _clip_human_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", _clean_human_text(value)).strip()
    if len(text) <= limit:
        return text
    clipped = text[:limit].rstrip()
    sentence_end = max(clipped.rfind("。"), clipped.rfind("；"), clipped.rfind(";"))
    if sentence_end >= max(30, limit // 2):
        clipped = clipped[: sentence_end + 1]
    return clipped.rstrip(" ，。；;") + "。"


def _source_ref(reading: dict[str, Any]) -> str:
    topic_id = _topic_id(reading)
    if topic_id is not None:
        return f"[[linuxdo-topic-{topic_id}]]"
    return _text(reading.get("url")) or "来源待补"


def _source_links(reading: dict[str, Any]) -> str:
    lines = [f"- {_source_ref(reading)}"]
    url = _text(reading.get("url"))
    if url and url != lines[0].removeprefix("- "):
        lines.append(f"- {url}")
    return "\n".join(lines)


def _should_preserve_existing_page(config: KnowledgeConfig, page_type: str, item_id: str, name: str) -> bool:
    path = page_path_for_id(config, page_type, item_id, name)
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    missing_required = [section for section in required_sections_for_page_type(page_type) if f"## {section}" not in text]
    if missing_required:
        return False
    status = _frontmatter_value(path, "status")
    evidence_status = _frontmatter_value(path, "evidence_status")
    return status in {"watching", "active", "needs_verification"} or evidence_status == "community_evidence"


def _frontmatter_value(path, key_name: str) -> str:
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


def _compact_lines(items: list[tuple[str, str]]) -> str:
    return "\n".join(f"- {key}: {value}" for key, value in items if value)


def _session_resource_list(readings: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for reading in readings:
        for resource in _dict_list(reading.get("resources")):
            label = _clean_title(_text(resource.get("name")) or _text(resource.get("id")))
            if label:
                lines.append(f"- {label}")
    return "\n".join(lines)


def _session_named_list(readings: list[dict[str, Any]], key: str) -> str:
    lines: list[str] = []
    for reading in readings:
        for item in _dict_list(reading.get(key)):
            label = _clean_title(_text(item.get("name")) or _text(item.get("id")))
            if label:
                lines.append(f"- {label}: {_clean_human_text(item.get('summary'))}")
    return "\n".join(lines)


def _clean_title(value: Any) -> str:
    return _clean_human_text(value).strip(" -_") or "未命名"


def _session_suffix(batch_id: str) -> str:
    suffix = _text(batch_id)
    suffix = re.sub(r"(?i)\blegacy[-_\s]*", "archive-", suffix)
    suffix = re.sub(r"(?i)\bbatch[-_\s]*", "", suffix)
    suffix = _clean_human_text(suffix).strip(" -_")
    return suffix or "001"


def _clean_human_text(value: Any) -> str:
    text = " ".join(_text(value).split())
    replacements = {
        "候选资源，当前记录显示它被多次提及": "待观察资源线索，当前证据只够说明它被讨论过",
        "是否值得采用要看来源证据、维护状态和反方反馈": "采用前需要复核来源、维护状态和反方反馈",
        "暂无足够可复用证据": "当前没有能支撑判断的可复用来源",
        "来源证据": "来源",
        "高相关。": "",
        "高相关：": "",
        "高相关": "",
        "中等相关。": "",
        "中等相关：": "",
        "中等相关": "",
        "累计权重": "讨论信号",
        "证据权重": "讨论信号",
        "legacy_summary": "needs_source_review",
        "风佬巨作": "社区项目线索",
        "zcf": "相关项目",
        "v5.0": "对应版本",
        "旧帖": "已读来源",
        "旧记录": "累计资料",
        "旧冲浪": "累计冲浪",
        "本批": "这组资料",
        "Batch": "阅读记录",
        "batch": "session",
        "……": " ",
        "…": " ",
        "...": " ",
        "（已截断）": "",
        "(已截断)": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"第\s*[0-9]+\s*批", "累计资料", text)
    text = re.sub(r"\s*(?:\.\.\.|…)+\s*$", "", text)
    return text.strip(" ，。；;")


def _topic_id(reading: dict[str, Any]) -> int | None:
    return _int(reading.get("topic_id"), None) or _int(reading.get("id"), None)


def _int(value: Any, default: int | None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _merge_non_empty(existing: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in update.items():
        if value not in ("", None):
            merged[key] = value
    return merged


def _normalize_hot_indexes(indexes: dict[str, Any]) -> None:
    dict_defaults = {
        "topic_index": ("topics",),
        "topic_update_state": ("topics",),
        "resource_index": ("resources",),
        "claim_index": ("claims",),
        "evidence_index": ("evidence",),
        "evidence_by_claim": ("claims",),
        "evidence_by_resource": ("resources",),
    }
    for index_name, keys in dict_defaults.items():
        if not isinstance(indexes.get(index_name), dict):
            indexes[index_name] = {}
        for key in keys:
            if not isinstance(indexes[index_name].get(key), dict):
                indexes[index_name][key] = {}
    if not isinstance(indexes.get("counter_evidence_queue"), dict):
        indexes["counter_evidence_queue"] = {}
    if not isinstance(indexes["counter_evidence_queue"].get("items"), list):
        indexes["counter_evidence_queue"]["items"] = []


def _default_status_for_page_type(page_type: str) -> str:
    if page_type == "draft":
        return "draft"
    if page_type == "candidate":
        return "candidate"
    if page_type == "claim":
        return "active"
    return "active"


def _page_type_for_resource(resource: dict[str, Any], merged: dict[str, Any], name: str) -> str:
    explicit_type = _text(resource.get("type") or resource.get("object_type") or merged.get("type"))
    if explicit_type in {"resource", "service", "collection", "workflow", "concept", "component", "candidate"}:
        return explicit_type

    status = _text(merged.get("status"))
    evidence_status = _text(merged.get("evidence_status"))
    if status in {"needs_source_review"} or evidence_status in {"insufficient_source_extract", "open_question"}:
        return "candidate"

    category = _text(resource.get("category") or merged.get("category"))
    if category in {"service", "api-relay", "api_relay", "api", "gateway"}:
        return "service"
    if category in {"collection", "map"}:
        return "collection"
    if category in {"workflow", "skill-workflow"}:
        return "workflow"
    if category in {"concept", "method"}:
        return "concept"
    if category in {"component", "skill-component"}:
        return "component"

    _slug, display = normalize_resource_name(name)
    return classify_knowledge_object(display)


def _frontmatter_type_for_page_type(page_type: str) -> str:
    if page_type in {"service", "collection", "component"}:
        return page_type
    return page_type


def _tags_for_page_type(page_type: str) -> list[str]:
    if page_type == "draft":
        return ["knowledge/draft"]
    if page_type == "claim":
        return ["knowledge/claim"]
    if page_type == "service":
        return ["knowledge/api-relay", "source/linuxdo"]
    if page_type == "collection":
        return ["knowledge/collection", "source/linuxdo"]
    if page_type == "workflow":
        return ["knowledge/workflow", "source/linuxdo"]
    if page_type == "component":
        return ["knowledge/component", "source/linuxdo"]
    if page_type in {"concept", "practice", "note"}:
        return [f"knowledge/{page_type}", "source/linuxdo"]
    if page_type == "resource":
        return ["knowledge/resource", "source/linuxdo"]
    if page_type == "candidate":
        return ["knowledge/candidate", "source/linuxdo"]
    return ["knowledge/linuxdo"]
