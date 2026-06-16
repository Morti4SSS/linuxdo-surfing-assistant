from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .state import load_hot_indexes, now_iso


STALE_STATUSES = {"needs_retest", "needs_verification", "stale"}
SOURCE_GAP_STATUSES = {"needs_source_review", "insufficient_source_extract", "open_question"}


def lint_knowledge_protocol(config: KnowledgeConfig, *, limit: int = 50) -> dict[str, Any]:
    indexes = load_hot_indexes(config)
    claims = _container(indexes.get("claim_index"), "claims")
    resources = _container(indexes.get("resource_index"), "resources")
    evidence_by_claim = _container(indexes.get("evidence_by_claim"), "claims")
    evidence_by_resource = _container(indexes.get("evidence_by_resource"), "resources")
    topic_updates = _container(indexes.get("topic_update_state"), "topics")

    all_issues = {
        "contradictions": _contradiction_items(claims, evidence_by_claim, limit=None),
        "stale_claims": _stale_claim_items(claims, limit=None),
        "orphan_claims": _orphan_claim_items(claims, evidence_by_claim, limit=None),
        "orphan_resources": _orphan_resource_items(resources, evidence_by_resource, limit=None),
        "source_gaps": _source_gap_items(claims, resources, topic_updates, limit=None),
        "missing_cross_links": [],
        "parked": _parked_items(topic_updates, limit=None),
    }
    issues = {name: items[:limit] for name, items in all_issues.items()}
    next_actions = _next_actions(issues, limit)
    parked_count = len(all_issues["parked"])
    actionable_count = sum(len(items) for name, items in all_issues.items() if name != "parked")
    return {
        "kind": "knowledge_lint",
        "schema_version": 1,
        "generated_at": now_iso(),
        "limit": limit,
        "issue_counts": {name: len(items) for name, items in all_issues.items()},
        "summary": {
            "actionable_count": actionable_count,
            "parked_count": parked_count,
            "next_action_count": len(next_actions),
        },
        "issues": issues,
        "next_actions": next_actions,
    }


def write_knowledge_lint_report(config: KnowledgeConfig, output_path: Path, *, limit: int = 50) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(lint_knowledge_protocol(config, limit=limit), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _container(index: Any, key: str) -> dict[str, Any]:
    if not isinstance(index, dict):
        return {}
    value = index.get(key, {})
    return value if isinstance(value, dict) else {}


def _contradiction_items(claims: dict[str, Any], evidence_by_claim: dict[str, Any], limit: int | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for claim_id, claim in sorted(claims.items()):
        edges = evidence_by_claim.get(claim_id, {})
        if not isinstance(edges, dict):
            continue
        supporting = _edge_ids(edges, "supporting_evidence_ids", "support_evidence_ids")
        counter = _edge_ids(edges, "counter_evidence_ids", "opposing_evidence_ids", "opposes_evidence_ids")
        if supporting and counter:
            items.append(
                {
                    "code": "contradiction",
                    "target_type": "claim",
                    "target_id": claim_id,
                    "status": _text(claim.get("status")),
                    "supporting_count": len(supporting),
                    "counter_count": len(counter),
                    "actionable": True,
                }
            )
    return items if limit is None else items[:limit]


def _stale_claim_items(claims: dict[str, Any], limit: int | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for claim_id, claim in sorted(claims.items()):
        if not isinstance(claim, dict):
            continue
        status = _text(claim.get("status")).lower()
        staleness = _text(claim.get("staleness_risk")).lower()
        if status in STALE_STATUSES or staleness == "high":
            items.append(
                {
                    "code": "stale_claim",
                    "target_type": "claim",
                    "target_id": claim_id,
                    "status": status,
                    "staleness_risk": staleness,
                    "actionable": True,
                }
            )
    return items if limit is None else items[:limit]


def _orphan_claim_items(claims: dict[str, Any], evidence_by_claim: dict[str, Any], limit: int | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for claim_id, claim in sorted(claims.items()):
        if not isinstance(claim, dict):
            continue
        edges = evidence_by_claim.get(claim_id, {})
        if not isinstance(edges, dict) or not _has_any_edge(edges):
            items.append(
                {
                    "code": "orphan_claim",
                    "target_type": "claim",
                    "target_id": claim_id,
                    "status": _text(claim.get("status")),
                    "actionable": True,
                }
            )
    return items if limit is None else items[:limit]


def _orphan_resource_items(resources: dict[str, Any], evidence_by_resource: dict[str, Any], limit: int | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for resource_id, resource in sorted(resources.items()):
        if not isinstance(resource, dict):
            continue
        edges = evidence_by_resource.get(resource_id, {})
        if not isinstance(edges, dict) or not _has_any_edge(edges):
            items.append(
                {
                    "code": "orphan_resource",
                    "target_type": "resource",
                    "target_id": resource_id,
                    "status": _text(resource.get("status")),
                    "actionable": True,
                }
            )
    return items if limit is None else items[:limit]


def _source_gap_items(
    claims: dict[str, Any],
    resources: dict[str, Any],
    topic_updates: dict[str, Any],
    limit: int | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for claim_id, claim in sorted(claims.items()):
        if isinstance(claim, dict) and _text(claim.get("evidence_status")).lower() in SOURCE_GAP_STATUSES:
            items.append({"code": "source_gap", "target_type": "claim", "target_id": claim_id, "actionable": True})
    for resource_id, resource in sorted(resources.items()):
        if isinstance(resource, dict) and _text(resource.get("evidence_status")).lower() in SOURCE_GAP_STATUSES:
            items.append({"code": "source_gap", "target_type": "resource", "target_id": resource_id, "actionable": True})
    return items if limit is None else items[:limit]


def _parked_items(topic_updates: dict[str, Any], limit: int | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for topic_id, update in sorted(topic_updates.items()):
        if isinstance(update, dict) and update.get("metadata_refresh_blocked"):
            items.append(
                {
                    "code": "live_access_blocked",
                    "target_type": "topic",
                    "target_id": _safe_int(topic_id) or topic_id,
                    "reason": _text(update.get("metadata_refresh_blocked_reason")),
                    "parked": True,
                    "actionable": False,
                }
            )
    return items if limit is None else items[:limit]


def _next_actions(issues: dict[str, list[dict[str, Any]]], limit: int) -> list[dict[str, Any]]:
    action_by_issue = {
        "contradictions": "review_contradiction",
        "stale_claims": "retest_claim",
        "orphan_claims": "attach_source_evidence",
        "orphan_resources": "attach_source_evidence",
        "source_gaps": "review_source_gap",
        "missing_cross_links": "add_cross_link",
    }
    actions: list[dict[str, Any]] = []
    for issue_name in ("contradictions", "stale_claims", "orphan_claims", "orphan_resources", "source_gaps", "missing_cross_links"):
        for item in issues.get(issue_name, []):
            if item.get("parked") or not item.get("actionable", True):
                continue
            actions.append(
                {
                    "target_type": item.get("target_type"),
                    "target_id": item.get("target_id"),
                    "action": action_by_issue[issue_name],
                }
            )
            if len(actions) >= limit:
                return actions
    return actions


def _edge_ids(edges: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = edges.get(key, [])
        if isinstance(value, list):
            values.extend(str(item) for item in value if str(item).strip())
    return values


def _has_any_edge(edges: dict[str, Any]) -> bool:
    return any(_edge_ids(edges, key) for key in edges)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
