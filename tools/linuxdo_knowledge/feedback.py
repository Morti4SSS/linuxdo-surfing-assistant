from __future__ import annotations

import hashlib
from copy import deepcopy
import re
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .state import JSON_DEFAULTS, load_json, now_iso, paths_for, save_hot_index


FEEDBACK_HEADING = "## 我的反馈"
HUMAN_SECTION_HEADINGS = ("我的反馈", "我的判断", "拒绝原因", "采用理由", "观察")
FEEDBACK_SCAN_DIRECTORIES = (
    "10_Catalog/resources",
    "10_Catalog/services",
    "10_Catalog/collections",
    "10_Catalog/candidates",
    "10_Catalog/comparisons",
    "10_Catalog/workflows",
    "20_Knowledge/concepts",
    "20_Knowledge/components",
    "20_Knowledge/claims",
    "30_Feedback",
    "90_Inbox/review-queue",
)


def sync_feedback(config: KnowledgeConfig, synced_at: str | None = None) -> dict[str, int]:
    synced = synced_at or now_iso()
    indexes = _load_feedback_indexes(config)
    _normalize_feedback_indexes(indexes)
    sync_state = indexes["feedback_sync_state"]
    known_files = sync_state.setdefault("files", {})
    changed = 0

    for path in _markdown_files(config.obsidian_vault_path):
        stat = path.stat()
        file_key = str(path)
        previous = known_files.get(file_key, {})
        if (
            isinstance(previous, dict)
            and float(previous.get("mtime", -1)) >= stat.st_mtime
            and int(previous.get("size", -1)) == stat.st_size
        ):
            continue

        parsed = parse_markdown_page(path)
        if parsed.get("id"):
            _record_feedback(indexes["user_feedback"], parsed, path, synced)
            _record_status(indexes["resource_index"], indexes["claim_index"], parsed, path)
        known_files[file_key] = {
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "content_hash": parsed.get("content_hash", ""),
            "feedback_hash": parsed.get("feedback_hash", ""),
            "last_synced_at": synced,
        }
        changed += 1

    sync_state["last_sync_at"] = synced
    save_hot_index(config, "feedback_sync_state", sync_state)
    save_hot_index(config, "user_feedback", indexes["user_feedback"])
    save_hot_index(config, "resource_index", indexes["resource_index"])
    save_hot_index(config, "claim_index", indexes["claim_index"])
    return {"changed_files": changed}


def parse_markdown_page(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    feedback = _extract_feedback(text)
    return {
        "path": str(path),
        "title": title_match.group(1).strip() if title_match else path.stem,
        "feedback": feedback,
        "content_hash": _sha256(text),
        "feedback_hash": _sha256(feedback),
        **frontmatter,
    }


def _markdown_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for relative_dir in FEEDBACK_SCAN_DIRECTORIES:
        directory = root / relative_dir
        if directory.exists():
            files.extend(path for path in directory.rglob("*.md") if path.is_file())
    return sorted(files)


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    parsed: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip().strip("\"'")
    return parsed


def _extract_feedback(text: str) -> str:
    sections = _extract_human_sections(text)
    if not sections:
        return ""
    if "我的反馈" in sections:
        return sections["我的反馈"]
    return "\n\n".join(f"## {heading}\n{body}" for heading, body in sections.items() if body).strip()


def _extract_human_sections(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    pattern = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)
    matches = list(pattern.finditer(text))
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        if heading not in HUMAN_SECTION_HEADINGS:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            result[heading] = body
    return result


def _record_feedback(feedback_state: dict[str, Any], parsed: dict[str, Any], path: Path, synced_at: str) -> None:
    items = feedback_state.setdefault("items", [])
    if not isinstance(items, list):
        items = []
        feedback_state["items"] = items
    item_id = str(parsed.get("id", ""))
    payload = {
        "id": item_id,
        "type": str(parsed.get("type", "")),
        "title": str(parsed.get("title", "")),
        "path": str(path),
        "feedback": str(parsed.get("feedback", "")),
        "feedback_hash": str(parsed.get("feedback_hash", "")),
        "status": str(parsed.get("status", "")),
        "synced_at": synced_at,
    }
    if "watchlist" in parsed:
        payload["watchlist"] = _parse_bool(parsed.get("watchlist"))
    existing = next((item for item in items if isinstance(item, dict) and item.get("id") == item_id), None)
    if existing is None:
        items.append(payload)
    else:
        existing.update(payload)


def _record_status(
    resource_index: dict[str, Any],
    claim_index: dict[str, Any],
    parsed: dict[str, Any],
    path: Path,
) -> None:
    item_id = str(parsed.get("id", ""))
    status = str(parsed.get("status", ""))
    payload = {"last_feedback_path": str(path)}
    if status:
        payload["status"] = status
    if "watchlist" in parsed:
        payload["watchlist"] = _parse_bool(parsed.get("watchlist"))
    if item_id.startswith(("resource:", "candidate:")):
        resource_index.setdefault("resources", {}).setdefault(item_id, {}).update(payload)
    if item_id.startswith("claim:"):
        claim_index.setdefault("claims", {}).setdefault(item_id, {}).update(payload)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "是"}


def _normalize_feedback_indexes(indexes: dict[str, Any]) -> None:
    defaults = {
        "feedback_sync_state": {"last_sync_at": None, "files": {}},
        "user_feedback": {"items": []},
        "resource_index": {"resources": {}},
        "claim_index": {"claims": {}},
    }
    for name, default in defaults.items():
        if not isinstance(indexes.get(name), dict):
            indexes[name] = dict(default)
    if not isinstance(indexes["feedback_sync_state"].get("files"), dict):
        indexes["feedback_sync_state"]["files"] = {}
    if not isinstance(indexes["user_feedback"].get("items"), list):
        indexes["user_feedback"]["items"] = []
    if not isinstance(indexes["resource_index"].get("resources"), dict):
        indexes["resource_index"]["resources"] = {}
    if not isinstance(indexes["claim_index"].get("claims"), dict):
        indexes["claim_index"]["claims"] = {}


def _load_feedback_indexes(config: KnowledgeConfig) -> dict[str, Any]:
    paths = paths_for(config)
    indexes: dict[str, Any] = {}
    for name in ("feedback_sync_state", "user_feedback", "resource_index", "claim_index"):
        try:
            indexes[name] = load_json(getattr(paths, name), deepcopy(JSON_DEFAULTS[name]))
        except ValueError:
            indexes[name] = deepcopy(JSON_DEFAULTS[name])
    return indexes
