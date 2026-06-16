from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .session import _upsert_evidence_edges
from .state import ensure_knowledge_state, load_hot_indexes, now_iso, save_hot_index


def rebuild_evidence_edges(config: KnowledgeConfig, rebuilt_at: str | None = None) -> dict[str, Any]:
    paths = ensure_knowledge_state(config)
    rebuilt = rebuilt_at or now_iso()
    indexes = load_hot_indexes(config)
    evidence_reviews = _existing_evidence_reviews(indexes.get("evidence_index", {}))
    counter_reviews = _existing_counter_reviews(indexes.get("counter_evidence_queue", {}))
    indexes["evidence_index"] = {"evidence": {}}
    indexes["evidence_by_claim"] = {"claims": {}}
    indexes["evidence_by_resource"] = {"resources": {}}
    indexes["counter_evidence_queue"] = {"items": []}

    evidence_lines = 0
    invalid_lines = 0
    ids_seen: dict[str, int] = {}
    shard_files = sorted(paths.evidence_shards.glob("*.jsonl"))
    for shard in shard_files:
        for item in _iter_jsonl_dicts(shard):
            if item is None:
                invalid_lines += 1
                continue
            evidence_lines += 1
            evidence_id = _text(item.get("id"))
            if evidence_id:
                ids_seen[evidence_id] = ids_seen.get(evidence_id, 0) + 1
            observed_at = _text(item.get("observed_at")) or rebuilt
            _upsert_evidence_edges(indexes, item, observed_at)

    _restore_evidence_reviews(indexes["evidence_index"], evidence_reviews)
    _restore_counter_reviews(indexes["counter_evidence_queue"], counter_reviews)

    for name in ("evidence_index", "evidence_by_claim", "evidence_by_resource", "counter_evidence_queue"):
        save_hot_index(config, name, indexes[name])

    duplicate_ids = sum(1 for count in ids_seen.values() if count > 1)
    counter_items = indexes["counter_evidence_queue"]["items"]
    counter_open_items = [
        item
        for item in counter_items
        if isinstance(item, dict) and str(item.get("status") or "open").strip().lower() == "open"
    ]
    return {
        "kind": "evidence_rebuild",
        "rebuilt_at": rebuilt,
        "shard_files": len(shard_files),
        "evidence_lines": evidence_lines,
        "unique_evidence_ids": len(ids_seen),
        "duplicate_evidence_ids": duplicate_ids,
        "invalid_lines": invalid_lines,
        "counter_queue_items": len(counter_items),
        "counter_queue_open_items": len(counter_open_items),
        "counter_queue_reviewed_items": len(counter_items) - len(counter_open_items),
    }


def _iter_jsonl_dicts(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            yield None
            continue
        yield item if isinstance(item, dict) else None


def _existing_evidence_reviews(index: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(index, dict):
        return {}
    evidence = index.get("evidence", {})
    if not isinstance(evidence, dict):
        return {}
    reviews: dict[str, dict[str, Any]] = {}
    fields = {
        "payload_variant_review_decision",
        "payload_variant_review_reason",
        "payload_variant_review_status",
        "payload_variant_reviewed_at",
        "payload_variant_followup",
    }
    for evidence_id, item in evidence.items():
        if not isinstance(item, dict):
            continue
        review = {field: item[field] for field in fields if field in item}
        if review:
            reviews[str(evidence_id)] = review
    return reviews


def _restore_evidence_reviews(index: dict[str, Any], reviews: dict[str, dict[str, Any]]) -> None:
    evidence = index.get("evidence", {})
    if not isinstance(evidence, dict):
        return
    for evidence_id, review in reviews.items():
        item = evidence.get(evidence_id)
        if isinstance(item, dict):
            item.update(review)


def _existing_counter_reviews(index: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(index, dict):
        return {}
    items = index.get("items", [])
    if not isinstance(items, list):
        return {}
    fields = {
        "status",
        "review_status",
        "review_decision",
        "review_action",
        "review_reason",
        "reviewed_at",
    }
    reviews: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not _text(item.get("id")):
            continue
        review = {field: item[field] for field in fields if field in item}
        if review and review.get("status") != "open":
            reviews[str(item["id"])] = review
    return reviews


def _restore_counter_reviews(index: dict[str, Any], reviews: dict[str, dict[str, Any]]) -> None:
    items = index.get("items", [])
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        review = reviews.get(str(item.get("id")))
        if review:
            item.update(review)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()
