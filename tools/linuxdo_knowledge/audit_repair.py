from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .state import load_hot_indexes, now_iso, save_hot_index


def repair_audit_issues(
    config: KnowledgeConfig,
    readings_dir: Path,
    *,
    apply: bool = False,
    limit: int | None = None,
    repaired_at: str | None = None,
) -> dict[str, Any]:
    repaired = repaired_at or now_iso()
    indexes = load_hot_indexes(config)
    working = indexes if apply else copy.deepcopy(indexes)
    budget = _RepairBudget(limit)

    result = {
        "kind": "knowledge_audit_repair",
        "applied": apply,
        "repaired_at": repaired,
        "limit": limit,
        "legacy_status_repaired": _repair_legacy_status(working, budget),
        "empty_category_filled": _repair_empty_categories(working, budget),
        "topic_updates_marked_for_refresh": _mark_topic_updates_for_refresh(working, budget, repaired),
        "metadata_only_levels_fixed": _repair_metadata_only_levels(readings_dir, budget, apply),
    }
    result["total_changes"] = (
        result["legacy_status_repaired"]
        + result["empty_category_filled"]
        + result["topic_updates_marked_for_refresh"]
        + result["metadata_only_levels_fixed"]
    )

    if apply:
        save_hot_index(config, "resource_index", working["resource_index"])
        save_hot_index(config, "claim_index", working["claim_index"])
        save_hot_index(config, "topic_update_state", working["topic_update_state"])
    return result


class _RepairBudget:
    def __init__(self, limit: int | None):
        self.remaining = None if limit is None or limit <= 0 else limit

    def take(self) -> bool:
        if self.remaining is None:
            return True
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


def _repair_legacy_status(indexes: dict[str, Any], budget: _RepairBudget) -> int:
    changed = 0
    for index_name, container_name in (("resource_index", "resources"), ("claim_index", "claims")):
        items = indexes.get(index_name, {}).get(container_name, {})
        if not isinstance(items, dict):
            continue
        for item in items.values():
            if not isinstance(item, dict) or item.get("evidence_status") != "legacy_summary":
                continue
            if not budget.take():
                return changed
            item["evidence_status"] = "needs_source_review"
            changed += 1
    return changed


def _repair_empty_categories(indexes: dict[str, Any], budget: _RepairBudget) -> int:
    resources = indexes.get("resource_index", {}).get("resources", {})
    if not isinstance(resources, dict):
        return 0
    changed = 0
    for resource_id, item in resources.items():
        if not isinstance(item, dict) or _text(item.get("category")):
            continue
        if not budget.take():
            return changed
        item["category"] = _category_for_resource(resource_id, item)
        changed += 1
    return changed


def _mark_topic_updates_for_refresh(indexes: dict[str, Any], budget: _RepairBudget, repaired_at: str) -> int:
    topics = indexes.get("topic_index", {}).get("topics", {})
    topic_updates = indexes.setdefault("topic_update_state", {}).setdefault("topics", {})
    if not isinstance(topics, dict) or not isinstance(topic_updates, dict):
        return 0
    changed = 0
    for topic_id, topic in sorted(topics.items()):
        update = topic_updates.get(topic_id, {})
        if not isinstance(update, dict):
            update = {}
        if update.get("metadata_refresh_needed"):
            continue
        has_reply_count = "reply_count" in update or "read_reply_count" in update
        if has_reply_count and _text(update.get("last_activity_at")):
            continue
        if not budget.take():
            return changed
        update["topic_id"] = _safe_int(topic_id) or _safe_int(topic.get("topic_id")) or topic_id
        update["metadata_refresh_needed"] = True
        update["metadata_refresh_reason"] = "missing_reply_count_or_last_activity_at"
        update["metadata_refresh_marked_at"] = repaired_at
        topic_updates[topic_id] = update
        changed += 1
    return changed


def _repair_metadata_only_levels(readings_dir: Path, budget: _RepairBudget, apply: bool) -> int:
    if not readings_dir.exists():
        return 0
    changed = 0
    for path in sorted(readings_dir.glob("knowledge_readings*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        readings = _readings_list(payload)
        file_changed = False
        for reading in readings:
            if _text(reading.get("status")) != "metadata_only":
                continue
            if _safe_int(reading.get("reading_level")) == 0:
                continue
            if not budget.take():
                if apply and file_changed:
                    _write_payload(path, payload)
                return changed
            reading["reading_level"] = 0
            file_changed = True
            changed += 1
        if apply and file_changed:
            _write_payload(path, payload)
    return changed


def _write_payload(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _readings_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    value = payload.get("readings", payload.get("topics", []))
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _category_for_resource(resource_id: str, item: dict[str, Any]) -> str:
    explicit = _text(item.get("type") or item.get("object_type"))
    if explicit in {"collection", "component", "concept", "workflow", "service", "candidate", "resource"}:
        return explicit
    prefix = resource_id.split(":", 1)[0]
    if prefix in {"collection", "component", "concept", "workflow", "service", "candidate"}:
        return prefix
    return "uncategorized"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
