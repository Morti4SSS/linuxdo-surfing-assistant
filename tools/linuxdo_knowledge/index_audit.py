from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .state import JSON_DEFAULTS, ensure_knowledge_state, now_iso


def audit_knowledge_indexes(config: KnowledgeConfig, readings_dir: Path | None = None) -> dict[str, Any]:
    paths = ensure_knowledge_state(config)
    indexes, load_issues = _load_indexes(paths)
    topics = _container(indexes.get("topic_index"), "topics")
    topic_updates = _container(indexes.get("topic_update_state"), "topics")
    resources = _container(indexes.get("resource_index"), "resources")
    claims = _container(indexes.get("claim_index"), "claims")
    evidence_index = _container(indexes.get("evidence_index"), "evidence")
    feedback_items = _feedback_items(indexes.get("user_feedback"))
    evidence_items, evidence_issues = _scan_evidence_shards(paths.evidence_shards, claims, resources)
    metadata_mismatches = _scan_metadata_only_level_mismatches(readings_dir)

    duplicate_ids = _duplicate_evidence_ids(evidence_items)
    legacy_status = _legacy_status_items(resources, claims)
    empty_categories = _empty_category_items(resources)
    metadata_pending = _metadata_refresh_pending_items(topics, topic_updates)
    metadata_blocked = _metadata_refresh_blocked_items(topics, topic_updates)
    topic_update_missing = _topic_update_missing_items(topics, topic_updates)

    issues = {
        "load": load_issues,
        "duplicate_evidence_ids": duplicate_ids,
        "duplicate_evidence_ids_unreviewed": _unreviewed_duplicate_evidence_ids(duplicate_ids, evidence_index),
        "legacy_status": legacy_status,
        "empty_category": empty_categories,
        "topic_update_missing": topic_update_missing,
        "metadata_refresh_pending": metadata_pending,
        "metadata_refresh_blocked": metadata_blocked,
        "metadata_only_level_mismatch": metadata_mismatches,
        "broken_evidence_refs": evidence_issues,
    }
    return {
        "kind": "knowledge_index_audit",
        "schema_version": 1,
        "generated_at": now_iso(),
        "counts": {
            "topic_count": len(topics),
            "resource_count": len(resources),
            "claim_count": len(claims),
            "evidence_count": len(evidence_items),
        },
        "issue_counts": {name: len(value) for name, value in issues.items()},
        "issues": issues,
        "feedback": _feedback_summary(feedback_items),
    }


def write_index_audit_report(config: KnowledgeConfig, output_path: Path, readings_dir: Path | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(audit_knowledge_indexes(config, readings_dir=readings_dir), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def audit_hot_indexes(config: KnowledgeConfig) -> dict[str, Any]:
    return audit_knowledge_indexes(config)


def _load_indexes(paths: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    indexes: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []
    for name, default in JSON_DEFAULTS.items():
        path = getattr(paths, name)
        try:
            indexes[name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
        except json.JSONDecodeError as error:
            indexes[name] = default
            issues.append({"path": path.name, "code": "invalid_json", "message": str(error)})
    return indexes, issues


def _container(index: Any, key: str) -> dict[str, Any]:
    if not isinstance(index, dict):
        return {}
    value = index.get(key, {})
    return value if isinstance(value, dict) else {}


def _feedback_items(index: Any) -> list[dict[str, Any]]:
    if not isinstance(index, dict):
        return []
    items = index.get("items", [])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _feedback_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    nonempty = sum(1 for item in items if _text(item.get("feedback")))
    return {"nonempty_count": nonempty, "empty_count": len(items) - nonempty}


def _scan_evidence_shards(
    evidence_shards: Path,
    claims: dict[str, Any],
    resources: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_items: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    if not evidence_shards.exists():
        return evidence_items, issues

    for path in sorted(evidence_shards.glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                issues.append({"path": f"{path.name}:{line_number}", "code": "invalid_evidence_json", "message": str(error)})
                continue
            if not isinstance(item, dict):
                continue
            evidence_items.append(item)
            missing_claims = [claim_id for claim_id in _string_list(item.get("claim_ids") or item.get("claim_refs")) if claim_id not in claims]
            missing_resources = [
                resource_id
                for resource_id in _string_list(item.get("resource_ids") or item.get("resource_refs"))
                if resource_id not in resources
            ]
            if missing_claims or missing_resources:
                issues.append(
                    {
                        "path": f"{path.name}:{line_number}",
                        "code": "broken_evidence_refs",
                        "evidence_id": _text(item.get("id")),
                        "missing_claim_ids": missing_claims,
                        "missing_resource_ids": missing_resources,
                    }
                )
    return evidence_items, issues


def _duplicate_evidence_ids(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in evidence_items:
        evidence_id = _text(item.get("id"))
        if evidence_id:
            counts[evidence_id] = counts.get(evidence_id, 0) + 1
    return [
        {"code": "duplicate_evidence_id", "evidence_id": evidence_id, "count": count}
        for evidence_id, count in sorted(counts.items())
        if count > 1
    ]


def _unreviewed_duplicate_evidence_ids(
    duplicate_ids: list[dict[str, Any]], evidence_index: dict[str, Any]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in duplicate_ids:
        evidence = evidence_index.get(str(item.get("evidence_id")))
        if isinstance(evidence, dict) and _safe_int(evidence.get("payload_variant_count")) == 1:
            continue
        if not _payload_variant_reviewed(evidence):
            issues.append({**item, "code": "duplicate_evidence_id_unreviewed"})
    return issues


def _payload_variant_reviewed(item: Any) -> bool:
    return isinstance(item, dict) and bool(_text(item.get("payload_variant_review_decision")))


def _legacy_status_items(resources: dict[str, Any], claims: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item_type, items in (("resource", resources), ("claim", claims)):
        for item_id, item in sorted(items.items()):
            if isinstance(item, dict) and item.get("evidence_status") == "legacy_summary":
                issues.append({"code": "legacy_status", "item_type": item_type, "id": item_id})
    return issues


def _empty_category_items(resources: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"code": "empty_category", "id": resource_id}
        for resource_id, item in sorted(resources.items())
        if isinstance(item, dict) and not _text(item.get("category"))
    ]


def _topic_update_missing_items(topics: dict[str, Any], topic_updates: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for topic_id in sorted(topics):
        update = topic_updates.get(topic_id, {})
        if not isinstance(update, dict):
            update = {}
        if update.get("metadata_refresh_needed") or update.get("metadata_refresh_blocked"):
            continue
        has_reply_count = "reply_count" in update or "read_reply_count" in update
        if not has_reply_count or not _text(update.get("last_activity_at")):
            issues.append({"code": "topic_update_missing", "topic_id": _safe_int(topic_id) or topic_id})
    return issues


def _metadata_refresh_pending_items(topics: dict[str, Any], topic_updates: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for topic_id in sorted(topics):
        update = topic_updates.get(topic_id, {})
        if isinstance(update, dict) and update.get("metadata_refresh_needed"):
            issues.append(
                {
                    "code": "metadata_refresh_pending",
                    "topic_id": _safe_int(topic_id) or topic_id,
                    "reason": _text(update.get("metadata_refresh_reason")),
                }
            )
    return issues


def _metadata_refresh_blocked_items(topics: dict[str, Any], topic_updates: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for topic_id in sorted(topics):
        update = topic_updates.get(topic_id, {})
        if isinstance(update, dict) and update.get("metadata_refresh_blocked"):
            issues.append(
                {
                    "code": "metadata_refresh_blocked",
                    "topic_id": _safe_int(topic_id) or topic_id,
                    "reason": _text(update.get("metadata_refresh_blocked_reason")),
                    "status": _text(update.get("metadata_refresh_blocked_status")),
                }
            )
    return issues


def _scan_metadata_only_level_mismatches(readings_dir: Path | None) -> list[dict[str, Any]]:
    if readings_dir is None or not readings_dir.exists():
        return []
    issues: list[dict[str, Any]] = []
    for path in sorted(readings_dir.glob("knowledge_readings*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for reading in _readings_list(payload):
            if _text(reading.get("status")) != "metadata_only":
                continue
            reading_level = _safe_int(reading.get("reading_level"))
            if reading_level != 0:
                issues.append(
                    {
                        "code": "metadata_only_level_mismatch",
                        "path": path.name,
                        "topic_id": _safe_int(reading.get("topic_id") or reading.get("id")),
                        "reading_level": reading_level,
                    }
                )
    return issues


def _readings_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    value = payload.get("readings", payload.get("topics", []))
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
