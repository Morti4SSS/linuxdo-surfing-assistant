from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig


@dataclass(frozen=True)
class KnowledgePaths:
    root: Path
    topic_index: Path
    topic_update_state: Path
    resource_index: Path
    claim_index: Path
    evidence_index: Path
    evidence_by_claim: Path
    evidence_by_resource: Path
    counter_evidence_queue: Path
    feedback_sync_state: Path
    user_feedback: Path
    frontier_queue: Path
    bookmark_source_index: Path
    session_log: Path
    claim_events: Path
    topic_summaries: Path
    evidence_shards: Path
    archive: Path


JSON_DEFAULTS = {
    "topic_index": {"topics": {}},
    "topic_update_state": {"topics": {}},
    "resource_index": {"resources": {}},
    "claim_index": {"claims": {}},
    "evidence_index": {"evidence": {}},
    "evidence_by_claim": {"claims": {}},
    "evidence_by_resource": {"resources": {}},
    "counter_evidence_queue": {"items": []},
    "feedback_sync_state": {"last_sync_at": None, "files": {}},
    "user_feedback": {"items": []},
    "frontier_queue": {"items": []},
    "bookmark_source_index": {"bookmarks": {}},
}

HOT_INDEX_NAMES = tuple(JSON_DEFAULTS.keys())
SHARD_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])")


def paths_for(config: KnowledgeConfig) -> KnowledgePaths:
    root = config.state_root
    return KnowledgePaths(
        root=root,
        topic_index=root / "topic_index.json",
        topic_update_state=root / "topic_update_state.json",
        resource_index=root / "resource_index.json",
        claim_index=root / "claim_index.json",
        evidence_index=root / "evidence_index.json",
        evidence_by_claim=root / "evidence_by_claim.json",
        evidence_by_resource=root / "evidence_by_resource.json",
        counter_evidence_queue=root / "counter_evidence_queue.json",
        feedback_sync_state=root / "feedback_sync_state.json",
        user_feedback=root / "user_feedback.json",
        frontier_queue=root / "frontier_queue.json",
        bookmark_source_index=root / "bookmark_source_index.json",
        session_log=root / "session_log.jsonl",
        claim_events=root / "claim_events.jsonl",
        topic_summaries=root / "topic_summaries",
        evidence_shards=root / "evidence_shards",
        archive=root / "archive",
    )


def ensure_knowledge_state(config: KnowledgeConfig) -> KnowledgePaths:
    paths = paths_for(config)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.topic_summaries.mkdir(parents=True, exist_ok=True)
    paths.evidence_shards.mkdir(parents=True, exist_ok=True)
    paths.archive.mkdir(parents=True, exist_ok=True)

    for field_name, default in JSON_DEFAULTS.items():
        path = getattr(paths, field_name)
        if not path.exists():
            write_json(path, default)

    if not paths.session_log.exists():
        paths.session_log.write_text("", encoding="utf-8")
    if not paths.claim_events.exists():
        paths.claim_events.write_text("", encoding="utf-8")

    return paths


def load_hot_indexes(config: KnowledgeConfig) -> dict[str, Any]:
    paths = ensure_knowledge_state(config)
    return {
        name: load_json(getattr(paths, name), JSON_DEFAULTS[name])
        for name in HOT_INDEX_NAMES
    }


def save_hot_index(config: KnowledgeConfig, name: str, data: Any) -> Path:
    if name not in JSON_DEFAULTS:
        known_names = ", ".join(HOT_INDEX_NAMES)
        raise ValueError(f"unknown hot index {name!r}; expected one of: {known_names}")

    paths = ensure_knowledge_state(config)
    path = getattr(paths, name)
    write_json(path, data)
    return path


def topic_summary_path(config: KnowledgeConfig, topic_id: int | str) -> Path:
    paths = paths_for(config)
    return paths.topic_summaries / f"{int(topic_id)}.json"


def upsert_topic_summary(config: KnowledgeConfig, topic_id: int | str, summary: dict[str, Any]) -> Path:
    ensure_knowledge_state(config)
    path = topic_summary_path(config, topic_id)
    existing = load_json(path, {})
    if not isinstance(existing, dict):
        existing = {}

    data = {**existing, **summary}
    data["topic_id"] = int(topic_id)
    data["updated_at"] = now_iso()
    write_json(path, data)
    return path


def append_evidence(config: KnowledgeConfig, evidence: dict[str, Any], observed_at: str | None = None) -> Path:
    paths = ensure_knowledge_state(config)
    observed = observed_at or now_iso()
    shard_month = evidence_shard_month(observed)
    path = paths.evidence_shards / f"{shard_month}.jsonl"
    append_jsonl(path, {**evidence, "observed_at": observed})
    return path


def append_claim_event(config: KnowledgeConfig, event: dict[str, Any], observed_at: str | None = None) -> Path:
    paths = ensure_knowledge_state(config)
    observed = observed_at or now_iso()
    append_jsonl(paths.claim_events, {**event, "observed_at": observed})
    return paths.claim_events


def maintain_state(config: KnowledgeConfig, maintained_at: str | None = None) -> dict[str, int]:
    from .obsidian import page_path_for, scaffold_vault, write_page

    maintained = maintained_at or now_iso()
    scaffold_vault(config)
    indexes = load_hot_indexes(config)
    topic_index = indexes.get("topic_index", {})
    topics = topic_index.get("topics", {}) if isinstance(topic_index, dict) else {}
    if not isinstance(topics, dict):
        topics = {}
        topic_index = {"topics": topics}

    changed = 0
    archive_path = ensure_knowledge_state(config).archive / f"maintenance-{maintained[:10]}.jsonl"
    for topic_id, topic in topics.items():
        if not isinstance(topic, dict):
            continue
        if topic.get("status") == "active" and _int_or_zero(topic.get("skip_count")) >= 3:
            topic["status"] = "deprioritized"
            topic["deprioritized_at"] = maintained
            append_jsonl(
                archive_path,
                {
                    "kind": "topic_deprioritized",
                    "topic_id": topic_id,
                    "title": topic.get("title", ""),
                    "reason": topic.get("skip_reason", ""),
                    "maintained_at": maintained,
                },
            )
            write_page(
                page_path_for(config, "archive", str(topic.get("title") or topic_id)),
                {
                    "id": f"archive:topic-{topic_id}",
                    "type": "archive",
                    "status": "archived",
                    "tags": ["catalog/archive"],
                    "last_verified": maintained[:10],
                    "evidence_status": "stale",
                    "staleness_risk": "high",
                    "watchlist": False,
                },
                str(topic.get("title") or topic_id),
                [
                    ("归档原因", str(topic.get("skip_reason", ""))),
                    ("来源证据", str(topic.get("url", ""))),
                ],
            )
            changed += 1

    indexes["topic_index"] = topic_index
    save_hot_index(config, "topic_index", topic_index)
    return {"deprioritized_topics": changed}


def evidence_shard_month(observed_at: str) -> str:
    match = SHARD_MONTH_RE.match(observed_at)
    if not match:
        raise ValueError(f"observed_at must start with ISO-like YYYY-MM month, got {observed_at!r}")
    return observed_at[:7]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, item: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
