from __future__ import annotations

from typing import Any

from .bookmarks import extract_topic_id
from .config import KnowledgeConfig
from .obsidian import append_log, page_path_for_id, scaffold_vault, write_page
from .state import (
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
) -> dict[str, int]:
    observed = observed_at or now_iso()
    scaffold_vault(config)
    ensure_knowledge_state(config)
    indexes = load_hot_indexes(config)
    _normalize_hot_indexes(indexes)
    read_items = _readings_list(readings)
    read_topic_ids = {str(topic_id) for topic_id in (_topic_id(reading) for reading in read_items) if topic_id is not None}

    for reading in read_items:
        _ingest_reading(config, indexes, reading, observed)
    for item in _skipped_task_items(task, read_topic_ids):
        _ingest_skipped_task_item(indexes, item, observed)

    save_hot_index(config, "topic_index", indexes["topic_index"])
    save_hot_index(config, "topic_update_state", indexes["topic_update_state"])
    save_hot_index(config, "resource_index", indexes["resource_index"])
    save_hot_index(config, "claim_index", indexes["claim_index"])
    _write_session_report(config, batch_id, observed, task, read_items)
    append_jsonl(
        paths_for(config).session_log,
        {"kind": "knowledge_session", "batch_id": batch_id, "readings": len(read_items), "observed_at": observed},
    )
    append_log(config, f"- {observed}: batch {batch_id} 写入 {len(read_items)} 条阅读结果。")
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


def _ingest_reading(config: KnowledgeConfig, indexes: dict[str, Any], reading: dict[str, Any], observed_at: str) -> None:
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
        _upsert_resource(config, indexes["resource_index"], resource, reading, observed_at)
    for claim in _dict_list(reading.get("claims")):
        _upsert_claim(indexes["claim_index"], claim, observed_at)
    for evidence in _dict_list(reading.get("evidence")):
        append_evidence(
            config,
            {
                **evidence,
                "source_type": "linuxdo_topic",
                "source_url": _text(reading.get("url")),
                "topic_id": topic_id,
                "resource_ids": resource_ids,
                "claim_ids": claim_ids,
            },
            observed_at=observed_at,
        )

    _write_related_pages(config, reading, observed_at)


def _upsert_resource(
    config: KnowledgeConfig,
    resource_index: dict[str, Any],
    resource: dict[str, Any],
    reading: dict[str, Any],
    observed_at: str,
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
    page_type = "resource" if merged.get("status") == "active" else "candidate"
    if page_type == "candidate":
        sections = [
            ("为什么被抓到", _text(resource.get("capture_reason")) or _text(reading.get("summary"))),
            ("初步判断", _text(resource.get("summary")) or _text(reading.get("summary"))),
            ("缺失证据", _text(resource.get("missing_evidence")) or "需要更多实测、维护状态或对比证据。"),
            ("下一步验证", _text(resource.get("next_verification")) or "再次遇到相关讨论或 GitHub 验证自然触及时再更新。"),
            ("来源证据", f"- {_text(reading.get('url'))}"),
        ]
    else:
        sections = [
            ("Agent 摘要", _text(resource.get("summary")) or _text(reading.get("summary"))),
            ("解决什么问题", _text(resource.get("problem"))),
            ("适用场景", _text(resource.get("use_cases"))),
            ("社区评价", _text(resource.get("community_view"))),
            ("相关对比", _text(resource.get("comparison"))),
            ("来源证据", f"- {_text(reading.get('url'))}"),
        ]
    _write_item_page(config, page_type, merged, observed_at, sections)


def _upsert_claim(claim_index: dict[str, Any], claim: dict[str, Any], observed_at: str) -> None:
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


def _write_related_pages(config: KnowledgeConfig, reading: dict[str, Any], observed_at: str) -> None:
    for item in _dict_list(reading.get("comparisons")):
        _write_item_page(
            config,
            "comparison",
            item,
            observed_at,
            [
                ("当前结论", _text(item.get("summary"))),
                ("评价维度", _markdown_value(item.get("dimensions"))),
                ("热门选择", _markdown_value(item.get("popular_choices"))),
                ("潜力选择", _markdown_value(item.get("potential_choices"))),
                ("分歧与争议", _markdown_value(item.get("disputes"))),
                ("适用场景", _markdown_value(item.get("use_cases"))),
                ("相关资源", _markdown_value(item.get("resources"))),
                ("来源证据", f"- {_text(reading.get('url'))}"),
            ],
        )
    for item in _dict_list(reading.get("workflows")):
        _write_item_page(
            config,
            "workflow",
            item,
            observed_at,
            [
                ("Agent 摘要", _text(item.get("summary"))),
                ("相关资源", _markdown_value(item.get("resources"))),
                ("来源证据", f"- {_text(reading.get('url'))}"),
            ],
        )
    for item in _dict_list(reading.get("knowledge_drafts")):
        _write_item_page(
            config,
            "draft",
            item,
            observed_at,
            [
                ("核心观点", _text(item.get("summary"))),
                ("方法", _markdown_value(item.get("method"))),
                ("适用场景", _markdown_value(item.get("use_cases"))),
                ("限制与反例", _markdown_value(item.get("limits"))),
                ("来源证据", f"- {_text(reading.get('url'))}"),
            ],
        )
    for item in _dict_list(reading.get("categories")):
        _write_item_page(
            config,
            "category",
            item,
            observed_at,
            [
                ("资源索引", _markdown_value(item.get("items"))),
                ("来源证据", f"- {_text(reading.get('url'))}"),
            ],
        )


def _write_item_page(
    config: KnowledgeConfig,
    page_type: str,
    item: dict[str, Any],
    observed_at: str,
    sections: list[tuple[str, str]],
) -> None:
    item_id = _text(item.get("id"))
    if not item_id:
        return

    name = _text(item.get("name")) or item_id
    write_page(
        page_path_for_id(config, page_type, item_id, name),
        {
            "id": item_id,
            "type": page_type,
            "status": _text(item.get("status")) or _default_status_for_page_type(page_type),
            "tags": [f"catalog/{page_type}" if page_type != "draft" else "wiki/draft"],
            "last_verified": observed_at[:10],
            "evidence_status": _text(item.get("evidence_status")) or "open_question",
            "staleness_risk": _text(item.get("staleness_risk")) or "medium",
            "watchlist": bool(item.get("watchlist", False)),
        },
        name,
        sections,
    )


def _write_session_report(
    config: KnowledgeConfig,
    batch_id: str,
    observed_at: str,
    task: dict[str, Any],
    readings: list[dict[str, Any]],
) -> None:
    task_items = task.get("items", []) if isinstance(task, dict) else []
    path = config.obsidian_vault_path / "inbox" / "sessions" / f"{observed_at[:10]}-batch-{batch_id}.md"
    findings = "\n".join(
        f"- {_text(reading.get('title'))}: {_text(reading.get('summary'))}" for reading in readings
    )
    skipped = "\n".join(
        f"- {_text(item.get('title'))}: {_text(item.get('skip_reason'))}"
        for item in _dict_list(task_items)
        if item.get("skip_reason")
    )
    write_page(
        path,
        {
            "id": f"session:{observed_at[:10]}-batch-{batch_id}",
            "type": "session",
            "status": "active",
            "tags": ["session"],
            "last_verified": observed_at[:10],
        },
        f"{observed_at[:10]} Batch {batch_id}",
        [
            ("本批范围", f"{len(_dict_list(task_items))} 个候选，{len(readings)} 个阅读结果。"),
            ("新发现", findings),
            ("候选资源", _session_resource_list(readings)),
            ("资源更新", ""),
            ("对比/争议", _session_named_list(readings, "comparisons")),
            ("只记录为证据的内容", ""),
            ("跳过与原因", skipped),
            ("下一批建议", ""),
        ],
    )


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
    for field in ("status", "evidence_status", "staleness_risk"):
        if field in claim:
            item[field] = _text(claim.get(field))
    return item


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


def _markdown_value(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    return _text(value)


def _session_resource_list(readings: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for reading in readings:
        for resource in _dict_list(reading.get("resources")):
            label = _text(resource.get("name")) or _text(resource.get("id"))
            if label:
                lines.append(f"- {label}")
    return "\n".join(lines)


def _session_named_list(readings: list[dict[str, Any]], key: str) -> str:
    lines: list[str] = []
    for reading in readings:
        for item in _dict_list(reading.get(key)):
            label = _text(item.get("name")) or _text(item.get("id"))
            if label:
                lines.append(f"- {label}: {_text(item.get('summary'))}")
    return "\n".join(lines)


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
    defaults = {
        "topic_index": ("topics",),
        "topic_update_state": ("topics",),
        "resource_index": ("resources",),
        "claim_index": ("claims",),
    }
    for index_name, keys in defaults.items():
        if not isinstance(indexes.get(index_name), dict):
            indexes[index_name] = {}
        for key in keys:
            if not isinstance(indexes[index_name].get(key), dict):
                indexes[index_name][key] = {}


def _default_status_for_page_type(page_type: str) -> str:
    if page_type == "draft":
        return "draft"
    if page_type == "candidate":
        return "candidate"
    return "active"
